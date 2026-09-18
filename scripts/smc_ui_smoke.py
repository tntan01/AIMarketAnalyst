"""Local UI smoke for the canonical SMC layer — Scanner → Detail → Chart.

Run:  python -X utf8 scripts/smc_ui_smoke.py

Pass ``--out-dir PATH`` to send every capture of the run (PNG, PDF, JSON) to an
explicit directory instead of the tracked ``reports/scanner/smc_ui_smoke/`` — a
verification lap that must not touch the repository's report artifacts uses it.

Task 127.  It walks the three screens with fixtures that cover every SMC state
(waiting, confirmed, invalid, no-zone, data-unavailable, historical, missing) and
records what was actually rendered:

* Scanner  — the table model's display value and the "Vị trí" tooltip, which is
  where the main screen shows the SMC verdict (the table keeps its 11 columns);
* Detail   — ``ScannerDetailScreen._diag_smc_html`` rendered into a real
  ``QTextEdit`` and grabbed to PNG;
* Chart    — the real ``assets/chart/index.html`` page loaded in a real
  ``QWebEngineView`` with the payload ``core.chart_payload`` built, printed to
  PDF and grabbed to PNG.

No configuration is added, no operational data is read and nothing is written
outside ``reports/scanner/smc_ui_smoke/`` — or outside the directory given with
``--out-dir``.  The script never sends an order.

Platform note: this script defaults to ``QT_QPA_PLATFORM=offscreen``, but the
offscreen Qt platform in this environment exposes no font families, so the
detail PNGs come out with tofu boxes.  Run it as

    QT_QPA_PLATFORM=windows python -X utf8 scripts/smc_ui_smoke.py

to capture legible images (Qt then uses the real Windows font database); the
externally set platform wins because this module only uses ``setdefault``.

Every fixture is the one the test suite already drives: the live controller for
the Scanner row, ``AnalysisPipeline.execute`` for the canonical states.  The
script fails loudly (non-zero exit) if a layer disagrees with the canonical
selection or if a render raises.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--no-sandbox --disable-gpu --disable-software-rasterizer",
)

from PyQt6.QtCore import QCoreApplication, Qt, QTimer, QUrl  # noqa: E402
from PyQt6.QtWidgets import QApplication, QTextEdit  # noqa: E402

QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

from collections import Counter  # noqa: E402

from core.chart_payload import build_full_chart_payload  # noqa: E402
from ui.chart_bridge import decorate_chart_payload  # noqa: E402
from ui.components.chart_view import chart_bootstrap_html  # noqa: E402
from ui.rich_text import set_rich_html  # noqa: E402
from ui.scanner_presentation import present_smc_row  # noqa: E402
from ui.theme import chart_palette, palette_for  # noqa: E402

# The smoke captures every surface in both application themes and checks the
# captured pixels, so the artifact proves a user could read the panel instead of
# only proving the text existed in the HTML (task 127/128 P1).
SMOKE_THEMES = ("light", "dark")
# A capture must be at least this much "ink" (pixels contrasting with the
# surface) to count as readable content rather than an empty surface.
MIN_INK_RATIO = 0.005

OUT_DIR = PROJECT_ROOT / "reports" / "scanner" / "smc_ui_smoke"
CHART_HTML = PROJECT_ROOT / "assets" / "chart" / "index.html"

_T113 = importlib.import_module("tests.test_smc_consumer_contract_task113")
_T117 = importlib.import_module("tests.test_smc_persistence_task117_120")
_TV4 = importlib.import_module("tests.test_scanner_detail_v4_diagnostics")


# ---------------------------------------------------------------------------
# Fixtures — one per SMC state the UI must tell apart
# ---------------------------------------------------------------------------


def _synthetic_row(
    analysis_result: dict[str, Any],
    side: str,
    symbol: str,
    *,
    chart_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A row whose SMC payload is hand-built but whose chart data is real.

    The candles come from the live fixture so a state with no SMC layer still
    captures a real chart surface — the smoke must show that the chart draws the
    market and withholds the SMC band, not that it fails to render at all.
    """

    payload = dict(analysis_result)
    if chart_payload is not None:
        payload.setdefault("chart_payload", chart_payload)
    return {
        "symbol": symbol,
        "selected_side": side,
        "candidate_status": "WAITING_CONFIRMATION",
        "analysis_result": payload,
    }


def _states() -> list[dict[str, Any]]:
    """Every state, with the fixture that really produces it."""

    states: list[dict[str, Any]] = []
    candles = (_TV4._blocked_row().get("analysis_result") or {}).get("chart_payload") or {}

    scanner_row = _TV4._blocked_row()
    # The live fixture is placed at the observation instant, so this scan can
    # legitimately end without publishing a verdict (the technical chain reports
    # the data unavailable at that instant).  The expectation follows what the
    # row actually carries — the UI must show THAT, never something else.
    live_verdict = (scanner_row.get("analysis_result") or {}).get("smc_selection")
    states.append(
        {
            "name": "waiting_scanner_row",
            "note": "Dòng Scanner thật do controller dựng (chờ xác nhận).",
            "row": scanner_row,
            "expect": "canonical" if live_verdict else "missing",
        }
    )

    for name, analysis in (
        ("confirmed", _T117._confirmed_analysis()),
        ("invalidated", _T117._invalidated_analysis()),
    ):
        result, _pipeline, symbol = analysis
        side = "buy"
        states.append(
            {
                "name": name,
                "note": f"Route Analyze thật, cửa sổ M15 {'giữ gần vùng' if name == 'confirmed' else 'chạy xa vùng'}.",
                "row": _synthetic_row(result, side, symbol),
                "expect": "canonical",
            }
        )

    for name, case_name, side in (
        ("no_zone", "no_zone", "sell"),
        ("data_unavailable", "ob_confirmed_sell", "buy"),
    ):
        result, _pipeline = _T113._analyze(_T113._case(case_name))
        states.append(
            {
                "name": name,
                "note": f"Ca consumer contract {case_name!r}.",
                "row": _synthetic_row(result, side, str(_T113._case(case_name)["symbol"])),
                "expect": "canonical",
            }
        )

    states.append(
        {
            "name": "historical",
            "note": "Payload lưu trước khi có kết quả canonical (chỉ có selected_zone cũ).",
            "row": _synthetic_row(
                {
                    "smc_consumer": {
                        "sides": {
                            "buy": {
                                "selected_zone": {"original_low": 1.0, "original_high": 2.0},
                                "selected_zone_quality_score": 82,
                            },
                            "sell": {},
                        }
                    }
                },
                "buy",
                "LEGACY",
                chart_payload=candles,
            ),
            "expect": "historical",
        }
    )
    states.append(
        {
            "name": "missing",
            "note": "Row không mang thông tin SMC nào.",
            "row": _synthetic_row({}, "buy", "EMPTY", chart_payload=candles),
            "expect": "missing",
        }
    )
    return states


# ---------------------------------------------------------------------------
# Screens
# ---------------------------------------------------------------------------


def _scanner_observation(row: dict[str, Any]) -> dict[str, Any]:
    """What the Scanner table shows for this row (columns stay as they are)."""

    from ui.screens.scanner_screen import ScannerTableModel
    from ui.scanner_presentation import sort_scanner_rows_for_display

    model = ScannerTableModel()
    model.set_rows(sort_scanner_rows_for_display([row]))
    displayed = model.rows[0] if model.rows else {}
    return {
        "columns": [key for key, _label in ScannerTableModel.COLUMNS],
        "price_vs_zone": displayed.get("price_vs_zone"),
        "zone_origin_class": displayed.get("zone_origin_class"),
        "tooltip": ScannerTableModel._price_vs_zone_tooltip(row),
    }


def _apply_theme(widget: QTextEdit, theme: str) -> None:
    """Put the widget on the REAL application surface for *theme*.

    The panel HTML is compiled for a theme, so the surface it is drawn on has to
    be that theme's surface too — otherwise dark-theme text lands on a white
    widget and the capture is unreadable (the defect this fixes).
    """

    from ui.theme_manager import ThemeManager

    try:
        ThemeManager().apply(widget, theme=theme)
        return
    except Exception:  # pragma: no cover - fall back to the semantic colours
        palette = palette_for(theme)
        widget.setStyleSheet(
            "QTextEdit{"
            f"background:{palette.background};color:{palette.text};"
            "border:none;}"
        )


def _luminance(rgb: list[int]) -> float:
    return (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255.0


def _capture_stats(pixmap: object, theme: str) -> dict[str, Any]:
    """Check one captured surface: is it this theme, and does it carry content?

    Sampling every 5th pixel is enough for both questions and keeps the smoke
    fast.  ``theme_ok`` says the captured surface belongs to the declared theme
    (dark surface for dark, light for light); ``ink_ok`` says text/graphics are
    actually drawn on it.
    """

    image = pixmap.toImage()
    width, height = image.width(), image.height()
    counts: Counter = Counter()
    total = 0
    step = 5
    for y in range(0, height, step):
        for x in range(0, width, step):
            color = image.pixelColor(x, y)
            counts[(color.red(), color.green(), color.blue())] += 1
            total += 1
    if total == 0:
        return {"theme_ok": False, "ink_ok": False, "theme": theme}

    background, background_count = counts.most_common(1)[0]
    background_luminance = _luminance(list(background))
    ink = sum(
        count
        for rgb, count in counts.items()
        if abs(_luminance(list(rgb)) - background_luminance) > 0.2
    )
    ink_ratio = ink / total
    theme_ok = (
        background_luminance < 0.4 if theme == "dark" else background_luminance > 0.6
    )
    return {
        "theme": theme,
        "background_rgb": list(background),
        "background_luminance": round(background_luminance, 4),
        "background_ratio": round(background_count / total, 4),
        "ink_ratio": round(ink_ratio, 4),
        "theme_ok": bool(theme_ok),
        "ink_ok": bool(ink_ratio >= MIN_INK_RATIO),
    }


def _detail_panel(
    row: dict[str, Any],
    app: QApplication,
    theme: str,
) -> tuple[str, QTextEdit]:
    from ui.screens.scanner_detail_screen import ScannerDetailScreen

    light = theme == "light"
    screen = ScannerDetailScreen.__new__(ScannerDetailScreen)
    screen.row = row
    screen._is_light_theme = lambda: light

    widget = QTextEdit()
    widget.resize(760, 1000)
    _apply_theme(widget, theme)
    html = set_rich_html(widget, screen._diag_smc_html(light=light), theme=theme)
    widget.show()
    app.processEvents()
    return html, widget


def _chart_payload(row: dict[str, Any], theme: str) -> dict[str, Any]:
    palette = palette_for(theme)
    payload = build_full_chart_payload(
        str(row.get("symbol") or ""),
        row.get("analysis_result") or {},
        active_timeframe="H1",
        # The chart reads the SMC layer from the ROW, so a stored document's
        # compatibility verdict reaches the chart too (task 128 P0).
        smc_source=row,
    )
    payload["theme"] = palette.name
    payload["palette"] = chart_palette(palette)
    return decorate_chart_payload(payload)


def _render_chart(
    app: QApplication,
    payload: dict[str, Any],
    name: str,
    theme: str,
    *,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    from PyQt6.QtWebEngineWidgets import QWebEngineView

    # ``OUT_DIR`` is read at call time (never bound as a default) so a caller can
    # redirect it — and so the Lô D test probe that monkeypatches
    # ``smoke.OUT_DIR`` still lands in its own temporary directory.
    target_dir = out_dir or OUT_DIR
    html = chart_bootstrap_html(CHART_HTML.read_text(encoding="utf-8"), palette_for(theme))
    script = (
        "if(window.setChartData){window.setChartData("
        + json.dumps(payload, default=str)
        + ");}"
    )
    view = QWebEngineView()
    view.resize(1100, 640)
    view.show()

    out: dict[str, Any] = {"name": name, "theme": theme, "pdf": None}
    chart_dir = CHART_HTML.parent
    state = {"loaded": False}

    def on_load(ok: bool) -> None:
        state["loaded"] = ok
        if not ok:
            app.quit()
            return
        view.page().runJavaScript(script)
        # Let the chart paint the new data before capturing.
        QTimer.singleShot(1500, capture)

    def capture() -> None:
        stem = f"chart_{name}_{theme}"
        pixmap = view.grab()
        png_path = target_dir / f"{stem}.png"
        out["png"] = str(png_path) if pixmap.save(str(png_path)) else None
        out["capture"] = _capture_stats(pixmap, theme)
        # printToPdf is asynchronous: the file only exists once Chromium reports
        # it finished, so the caption is read AFTER that signal (the previous
        # version quit first and left no PDF behind).
        view.page().printToPdf(str(target_dir / f"{stem}.pdf"))

    def on_pdf_finished(path: str, success: bool) -> None:
        out["pdf"] = path
        out["pdf_saved"] = bool(success and Path(path).is_file())
        # The caption the page received, read back from the live DOM.
        view.page().runJavaScript(
            "document.getElementById('smc-caption').textContent", finish
        )

    def finish(caption: object) -> None:
        out["caption"] = caption
        app.quit()

    view.loadFinished.connect(on_load)
    view.page().pdfPrintingFinished.connect(on_pdf_finished)
    view.setHtml(html, QUrl.fromLocalFile(str(chart_dir.resolve()) + "/"))

    QTimer.singleShot(60000, app.quit)
    app.exec()
    out["loaded"] = state["loaded"]
    view.deleteLater()
    return out


# ---------------------------------------------------------------------------
# Walk-through
# ---------------------------------------------------------------------------


def _run(out_dir: Path | None = None) -> dict[str, Any]:
    # Every capture of this run goes to ONE directory, resolved at call time:
    # the module constant by default, or the explicit ``--out-dir`` a
    # verification lap passes so it never writes into the tracked reports tree.
    target_dir = out_dir or OUT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv)

    report: dict[str, Any] = {
        "task": "127",
        "note": (
            "Smoke cục bộ Scanner → Detail → Chart với fixture đủ trạng thái; "
            "chỉ dùng fixture của test suite, không cấu hình mới, không dữ liệu vận hành."
        ),
        "themes": list(SMOKE_THEMES),
        "min_ink_ratio": MIN_INK_RATIO,
        "states": [],
        "failures": [],
    }

    for state in _states():
        name = state["name"]
        row = state["row"]
        view = present_smc_row(row)
        entry: dict[str, Any] = {
            "state": name,
            "note": state["note"],
            "expected_source": state["expect"],
            "presentation": view.to_dict(),
            "scanner": None,
            "detail": {},
            "chart": {},
        }

        # --- Scanner ------------------------------------------------------
        try:
            entry["scanner"] = _scanner_observation(row)
        except Exception as exc:  # pragma: no cover - reported, not hidden
            report["failures"].append(f"{name}: scanner {exc!r}")

        if view.source != state["expect"]:
            report["failures"].append(
                f"{name}: nguồn hiển thị {view.source!r} khác kỳ vọng {state['expect']!r}"
            )

        # --- Detail, in both themes ---------------------------------------
        for theme in SMOKE_THEMES:
            try:
                html, widget = _detail_panel(row, app, theme)
                pixmap = widget.grab()
                png = target_dir / f"detail_{name}_{theme}.png"
                saved = pixmap.save(str(png))
                stats = _capture_stats(pixmap, theme)
                widget.deleteLater()
            except Exception as exc:  # pragma: no cover
                report["failures"].append(f"{name}/{theme}: detail {exc!r}")
                continue

            has_score = view.score_text in html if view.available else True
            entry["detail"][theme] = {
                "html_len": len(html),
                "png": str(png) if saved else None,
                "has_smc_text": "Điểm SMC" in html,
                "has_score_text": bool(has_score),
                "capture": stats,
            }
            if not saved:
                report["failures"].append(f"{name}/{theme}: panel không lưu được ảnh")
            if not stats.get("theme_ok"):
                report["failures"].append(
                    f"{name}/{theme}: nền chụp không thuộc theme "
                    f"(rgb={stats.get('background_rgb')})"
                )
            if not stats.get("ink_ok"):
                report["failures"].append(
                    f"{name}/{theme}: ảnh panel không có nội dung đọc được "
                    f"(ink={stats.get('ink_ratio')})"
                )
            if not entry["detail"][theme]["has_smc_text"]:
                report["failures"].append(f"{name}/{theme}: panel thiếu nội dung SMC")

        # --- Chart, in both themes ----------------------------------------
        for theme in SMOKE_THEMES:
            try:
                payload = _chart_payload(row, theme)
                overlay = payload["smc_overlay"]
                layer = next(iter((overlay.get("timeframes") or {}).values()), {})
                render = _render_chart(app, payload, name, theme, out_dir=target_dir)
            except Exception as exc:  # pragma: no cover
                report["failures"].append(f"{name}/{theme}: chart {exc!r}")
                continue

            entry["chart"][theme] = {
                "available": overlay["available"],
                "source": overlay["source"],
                "read_status": overlay["read_status"],
                "reason_codes": overlay["reason_codes"],
                "caption": layer.get("caption"),
                "zones": [
                    {
                        "side": z.get("side"),
                        "status": z.get("status"),
                        "label": z.get("label"),
                        "from": z.get("from"),
                        "to": z.get("to"),
                    }
                    for z in layer.get("zones") or []
                ],
                "render": render,
            }
            stats = render.get("capture") or {}
            if not render.get("loaded"):
                report["failures"].append(f"{name}/{theme}: trang chart không load")
            if not render.get("pdf_saved"):
                report["failures"].append(f"{name}/{theme}: không ghi được PDF")
            if not stats.get("theme_ok"):
                report["failures"].append(
                    f"{name}/{theme}: nền chart không thuộc theme "
                    f"(rgb={stats.get('background_rgb')})"
                )
            if not stats.get("ink_ok"):
                report["failures"].append(
                    f"{name}/{theme}: ảnh chart không có nội dung đọc được "
                    f"(ink={stats.get('ink_ratio')})"
                )
            # Task 145 (Lô D): an execution-view timeframe (H1) draws no SMC
            # layer at all, so the correct caption there is EMPTY even though the
            # payload still carries the layer's data.  Expecting the payload's
            # caption on H1 would assert the behaviour the task removed.
            execution_view = {
                str(tf).upper()
                for tf in (payload.get("execution_view_timeframes") or ())
            }
            if str(payload.get("active_timeframe") or "").upper() in execution_view:
                expected_caption = ""
            else:
                expected_caption = layer.get("caption") or ""
            if str(render.get("caption") or "").strip() != expected_caption.strip():
                report["failures"].append(
                    f"{name}/{theme}: caption trong DOM {render.get('caption')!r} "
                    f"khác payload {expected_caption!r}"
                )

        report["states"].append(entry)

    path = target_dir / "smc_ui_smoke.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(path)
    return report


def _summary(report: dict[str, Any]) -> str:
    lines = [
        "SMC UI smoke — Scanner → Detail → Chart",
        f"Theme chụp: {', '.join(report['themes'])} · ngưỡng nội dung: "
        f"ink >= {report['min_ink_ratio']}",
        "",
    ]
    for entry in report["states"]:
        view = entry["presentation"]
        lines.append(
            f"- {entry['state']:<22} nguồn={view['source']:<10} "
            f"điểm={view['score_text']:<28} trạng thái={view['state_text']}"
        )
        for theme, detail in (entry["detail"] or {}).items():
            stats = detail.get("capture") or {}
            lines.append(
                f"{'':10}{theme:<6} panel: rgb={stats.get('background_rgb')} "
                f"lum={stats.get('background_luminance')} ink={stats.get('ink_ratio')} "
                f"theme_ok={stats.get('theme_ok')} smc_text={detail.get('has_smc_text')}"
            )
        for theme, chart in (entry["chart"] or {}).items():
            zones = ",".join(f"{z['side']}:{z['status']}" for z in (chart.get("zones") or []))
            stats = (chart.get("render") or {}).get("capture") or {}
            render = chart.get("render") or {}
            lines.append(
                f"{'':10}{theme:<6} chart: available={chart.get('available')} "
                f"read={chart.get('read_status')} zones=[{zones}] "
                f"caption={chart.get('caption')!r} ink={stats.get('ink_ratio')} "
                f"pdf={render.get('pdf_saved')}"
            )
    if report["failures"]:
        lines.append("")
        lines.append("THẤT BẠI:")
        lines.extend(f"- {item}" for item in report["failures"])
    else:
        lines.append("")
        lines.append(
            "Không có lỗi: cả ba lớp đọc cùng một kết quả canonical, và mọi ảnh "
            "chụp đúng theme với nội dung đọc được."
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SMC UI smoke (Scanner → Detail → Chart)")
    parser.add_argument(
        "--out-dir",
        default=None,
        help=(
            "thư mục nhận toàn bộ ảnh/PDF/JSON của lượt chạy này "
            f"(mặc định: {OUT_DIR.relative_to(PROJECT_ROOT)})"
        ),
    )
    args = parser.parse_args(argv)
    out_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else None
    report = _run(out_dir)
    print(_summary(report))
    print(f"\nBáo cáo: {report['report_path']}")
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
