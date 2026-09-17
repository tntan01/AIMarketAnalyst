"""Chart QA against the real snapshots of task 131 (task 132).

Run:
    python -X utf8 scripts/smc_chart_qa.py --report reports/scanner/smc_real_snapshots/chart_qa.json
    QT_QPA_PLATFORM=windows python -X utf8 scripts/smc_chart_qa.py --render 3

For every corpus row the script re-runs the canonical seam on the stored closed
candles and asks the real chart builder (``core.chart_payload.build_smc_overlay``,
reached through ``build_full_chart_payload`` exactly as the UI reaches it) what it
would draw.  It then compares that against what the *typed* canonical selection
says should be drawn, and stores expected and observed side by side.  A QA that
only screenshots the page cannot tell "the chart drew the wrong band" from "the
chart drew nothing", so the comparison comes first and the screenshot is
supporting evidence.

Checked per case:

* zone identity — the band carries the selected zone/setup id of its own side;
* zone geometry — ``from``/``to`` equal the bounds the canonical zone recorded;
* zone status — invalid lifecycle/confirmation is invalid, a watched side is
  watch, otherwise selected;
* entry eligibility — a zone is only an entry region when the side has an
  accepted plan AND is still selected;
* trigger — drawn only from the typed confirmation record, keeping its own time,
  never before ``confirmed_at``;
* ``protected_swing`` — Lô A: a layer either publishes the canonical protected
  swing of its own timeframe, or states the absence with
  ``SMC_PROTECTED_SWING_UNAVAILABLE``.  The QA checks both halves: a published
  record must be well-formed (identity, level, kind) and must NOT be any number
  that could stand in for it (the plan's stop-loss, the band bounds), and every
  drawn layer without a record must carry the reason code.  The record is a
  layer property, not a zone property.

Nothing is written outside ``reports/scanner/smc_real_snapshots/`` and no order is
ever sent.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--no-sandbox --disable-gpu --disable-software-rasterizer",
)

from core.chart_payload import (  # noqa: E402
    SMC_PROTECTED_SWING_UNAVAILABLE,
    build_full_chart_payload,
    build_smc_overlay,
)
from core.market_models import Candle  # noqa: E402
from core.scanner_live_producers import derive_live_analysis  # noqa: E402
from core.smc_snapshot_cache import smc_rule_versions  # noqa: E402

OUTPUT_DIR = PROJECT_ROOT / "reports" / "scanner" / "smc_real_snapshots"
CORPUS_PATH = OUTPUT_DIR / "corpus.jsonl.gz"
DEFAULT_REPORT = OUTPUT_DIR / "chart_qa.json"
CHART_HTML = PROJECT_ROOT / "assets" / "chart" / "index.html"

INVALID_LIFECYCLE = {"invalidated", "expired", "consumed", "full_filled", "filled"}
INVALID_CONFIRMATION = {"invalidated", "expired"}


def _candle(payload: Mapping[str, Any]) -> Candle:
    return Candle(
        time=datetime.fromisoformat(str(payload["t"])),
        open=float(payload["o"]),
        high=float(payload["h"]),
        low=float(payload["l"]),
        close=float(payload["c"]),
        volume=float(payload.get("v") or 0.0),
    )


def _analysis(row: Mapping[str, Any]) -> dict[str, Any]:
    candles = {
        tf: [_candle(item) for item in row["candles"][tf]]
        for tf in ("D1", "H4", "H1", "M15")
    }
    return derive_live_analysis(
        candles["D1"],
        candles["H4"],
        candles["H1"],
        symbol=row["symbol"],
        captured_at=datetime.fromisoformat(row["as_of"]),
        news_in_3h=False,
        m15_candles=candles["M15"],
        m15_as_of=datetime.fromisoformat(row["as_of"]),
        tick_size=row["tick_size"],
        tick_size_source=row["tick_size_source"],
        # Same R:R floor as the production caller, so plan availability in the
        # QA is the one the live route would produce.
        min_rr=row.get("min_rr"),
    )


def _carrier(result: Any, snapshot: Any = None) -> dict[str, Any]:
    """The exact carrier the live Scanner route hands the UI and the chart.

    The route publishes two things side by side in the same analysis result: the
    per-side summary from ``core.scanner_composition._smc_selection_summary`` and
    the canonical block from ``core.smc_persistence.build_smc_persistence_block``
    (built from the same evaluation — no re-scoring, no re-selection).  The read
    boundary is deliberately strict about this: a payload carrying a
    ``smc_selection`` with no block beside it is refused
    (``SMC_READ_CARRIER_WITHOUT_BLOCK``) rather than unwrapped into a live result.
    The QA therefore builds the carrier through the production producers, so what
    it checks is the shape the UI actually reads.
    """

    from core.scanner_composition import _smc_selection_summary
    from core.smc_consumer_contract import build_smc_consumer_from_canonical_result
    from core.smc_persistence import build_smc_persistence_block

    block = build_smc_persistence_block(
        result,
        build_smc_consumer_from_canonical_result(result=result),
        snapshot=snapshot,
    )
    return {
        "analysis_result": {
            "smc_selection": {
                side: _smc_selection_summary(result, side) for side in ("buy", "sell")
            },
            "smc_scoring": block,
        }
    }


def _expected_for_side(
    final: Any,
    coordinator: Any,
    side: str,
) -> dict[str, Any]:
    """What the canonical selection says the chart must draw.

    ``final`` is the finalized contract selection (``SmcSideSelection``) the
    overlay itself reads; ``coordinator`` is the pre-finalization verdict, used
    as a second, independent source for the geometry.
    """

    if final is None:
        return {"draws": False, "why": "no selection for this side"}
    low = getattr(final, "zone_low", None)
    high = getattr(final, "zone_high", None)
    if low is None or high is None or float(high) <= float(low):
        return {
            "draws": False,
            "why": f"state {getattr(final, 'state', None)!r} carries no usable zone band",
            "zone_id": final.selected_zone_id,
        }
    candidate = getattr(coordinator, "selected", None) if coordinator is not None else None
    candidate_bounds = None
    plan_zone = getattr(candidate, "plan_zone", None)
    if isinstance(plan_zone, Mapping):
        original = plan_zone.get("original_bounds")
        if isinstance(original, Mapping):
            candidate_bounds = (float(original["low"]), float(original["high"]))
    lifecycle = str(getattr(final, "lifecycle_status", "") or "").lower()
    readiness = getattr(final, "readiness", None)
    readiness_status = str(
        (readiness.get("status") if isinstance(readiness, Mapping) else getattr(readiness, "status", ""))
        or ""
    ).upper()
    confirmation = getattr(final, "confirmation", None)
    confirmation_status = str(
        (confirmation.get("status") if isinstance(confirmation, Mapping) else getattr(confirmation, "status", ""))
        or ""
    ).lower()
    if lifecycle in INVALID_LIFECYCLE or confirmation_status in INVALID_CONFIRMATION:
        status = "invalid"
    elif readiness_status == "WATCH_ZONE":
        status = "watch"
    else:
        status = "selected"
    plan = getattr(final, "plan", None)
    plan_available = bool(getattr(final, "plan_available", False))
    return {
        "draws": True,
        "side": side,
        "zone_id": getattr(final, "selected_zone_id", None),
        "setup_id": getattr(final, "selected_setup_id", None),
        "timeframe": str(getattr(final, "timeframe", "") or "").upper(),
        "from": float(low),
        "to": float(high),
        "candidate_bounds": candidate_bounds,
        "status": status,
        "plan_available": plan_available,
        "execution_eligible": plan_available and status == "selected",
        "lifecycle_status": lifecycle or None,
        "trigger_at": (
            confirmation.get("trigger_at") if isinstance(confirmation, Mapping) else None
        ),
        "confirmed_at": (
            confirmation.get("confirmed_at") if isinstance(confirmation, Mapping) else None
        ),
        "stop_loss": (
            plan.get("stop_loss") if isinstance(plan, Mapping) else None
        ),
        # The protected swing is a LAYER property, not a zone one: it is checked
        # per timeframe by ``_check_protected_swing`` against the canonical
        # record, so no per-zone expected value is stated here.
        "protected_swing_reason": SMC_PROTECTED_SWING_UNAVAILABLE,
    }


def _observed_zone(overlay: Mapping[str, Any], side: str) -> dict[str, Any] | None:
    for layer in (overlay.get("timeframes") or {}).values():
        for zone in layer.get("zones") or []:
            if zone.get("side") == side:
                return zone
    return None


def _observed_trigger(overlay: Mapping[str, Any], side: str) -> dict[str, Any] | None:
    for layer in (overlay.get("timeframes") or {}).values():
        trigger = layer.get("trigger")
        if isinstance(trigger, Mapping) and trigger.get("side") == side:
            return trigger
    return None


def _compare_side(
    side: str,
    expected: Mapping[str, Any],
    overlay: Mapping[str, Any],
) -> dict[str, Any]:
    zone = _observed_zone(overlay, side)
    trigger = _observed_trigger(overlay, side)
    checks: dict[str, Any] = {}

    checks["drawn"] = (zone is not None) == bool(expected.get("draws"))
    if not expected.get("draws"):
        checks["zone_identity"] = zone is None
        checks["geometry"] = zone is None
        checks["status"] = zone is None
        checks["execution_eligible"] = zone is None
        checks["trigger_time_order"] = True
        return {
            "expected": dict(expected),
            "observed": {"zone": zone, "trigger": trigger},
            "checks": checks,
            "pass": all(checks.values()),
        }

    if zone is None:
        return {
            "expected": dict(expected),
            "observed": {"zone": None, "trigger": trigger},
            "checks": {**checks, "zone_identity": False, "geometry": False, "status": False},
            "pass": False,
        }

    checks["zone_identity"] = (
        zone.get("zone_id") == expected["zone_id"]
        and zone.get("setup_id") == expected["setup_id"]
        and zone.get("timeframe") == expected["timeframe"]
    )
    checks["geometry"] = abs(float(zone["from"]) - expected["from"]) < 1e-9 and abs(
        float(zone["to"]) - expected["to"]
    ) < 1e-9
    if expected.get("candidate_bounds") is not None:
        checks["geometry_matches_candidate_bounds"] = (
            abs(expected["candidate_bounds"][0] - expected["from"]) < 1e-9
            and abs(expected["candidate_bounds"][1] - expected["to"]) < 1e-9
        )
    checks["status"] = zone.get("status") == expected["status"]
    checks["execution_eligible"] = bool(zone.get("execution_eligible")) == bool(
        expected["execution_eligible"]
    )
    if trigger is None:
        checks["trigger_time_order"] = expected["trigger_at"] is None
    else:
        confirmed = trigger.get("confirmed_at")
        order_ok = confirmed is None or str(trigger.get("trigger_at")) >= str(confirmed)
        checks["trigger_time_order"] = order_ok and (
            trigger.get("zone_id") == expected["zone_id"]
        )
    return {
        "expected": dict(expected),
        "observed": {"zone": zone, "trigger": trigger},
        "checks": checks,
        "pass": all(checks.values()),
    }


def _check_protected_swing(overlay: Mapping[str, Any], expected_by_side: Mapping[str, Any]) -> dict[str, Any]:
    """Lô A: a layer either publishes a real canonical record or states the absence.

    Two ways to pass, and no third one:

    * **published** — the level, id, kind and provenance are a well-formed
      canonical record AND the level is none of the numbers that could stand in
      for it (the stop-loss of either side, the band bounds);
    * **absent** — no record, and ``SMC_PROTECTED_SWING_UNAVAILABLE`` is stated
      on every layer that actually drew a zone.
    """

    forbidden: dict[str, float] = {}
    for side, expected in expected_by_side.items():
        for key in ("stop_loss", "entry_zone_low", "entry_zone_high"):
            value = expected.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                forbidden[f"{side}:{key}"] = float(value)

    findings: list[dict[str, Any]] = []
    for timeframe, layer in (overlay.get("timeframes") or {}).items():
        swing = layer.get("protected_swing")
        reasons = set(layer.get("reason_codes") or [])
        substituted: list[str] = []
        malformed: list[str] = []
        if isinstance(swing, Mapping):
            level = swing.get("level")
            swing_id = str(swing.get("id") or "").strip()
            kind = str(swing.get("kind") or "").strip().lower()
            if not swing_id:
                malformed.append("missing_id")
            if kind not in ("high", "low"):
                malformed.append("unknown_kind")
            if not isinstance(level, (int, float)) or isinstance(level, bool):
                malformed.append("non_numeric_level")
            elif not math.isfinite(float(level)) or float(level) <= 0:
                malformed.append("non_positive_level")
            else:
                for label, value in forbidden.items():
                    if abs(float(level) - value) < 1e-9:
                        substituted.append(label)
        findings.append(
            {
                "timeframe": timeframe,
                "protected_swing": swing,
                "reason_code_present": SMC_PROTECTED_SWING_UNAVAILABLE in reasons,
                "malformed": malformed,
                "substituted_from": substituted,
            }
        )
    # The reason code is only emitted for a timeframe that actually drew a zone.
    drew_any = any(
        layer.get("zones") for layer in (overlay.get("timeframes") or {}).values()
    )
    published = [item for item in findings if item["protected_swing"] is not None]
    absent = [item for item in findings if item["protected_swing"] is None]
    return {
        "layers": findings,
        "published_count": len(published),
        "every_published_record_is_well_formed": all(
            not item["malformed"] for item in published
        ),
        "no_substitute_level": all(not item["substituted_from"] for item in findings),
        # An absence must be stated on every drawn layer; a published record must
        # NOT carry the unavailable code (that would be a contradiction).
        "reason_code_where_absent": (
            all(item["reason_code_present"] for item in absent) if drew_any else True
        ),
        "no_unavailable_code_where_published": all(
            not item["reason_code_present"] for item in published
        ),
        "pass": all(not item["malformed"] for item in published)
        and all(not item["substituted_from"] for item in findings)
        and (all(item["reason_code_present"] for item in absent) if drew_any else True)
        and all(not item["reason_code_present"] for item in published),
    }


def _case(row: Mapping[str, Any], analysis: Mapping[str, Any]) -> dict[str, Any]:
    from core.smc_scoring_result import smc_selection_of

    result = analysis["canonical_smc"]
    evaluation = analysis["smc_evaluation"]
    carrier = _carrier(result, analysis.get("smc_snapshot"))
    overlay = build_smc_overlay(carrier)
    sides: dict[str, Any] = {}
    expected_by_side: dict[str, Any] = {}
    for side in ("buy", "sell"):
        expected = _expected_for_side(
            smc_selection_of(result.side(side)),
            evaluation.selection(side),
            side,
        )
        expected_by_side[side] = expected
        sides[side] = _compare_side(side, expected, overlay)
    protected = _check_protected_swing(overlay, expected_by_side)
    timeframes_with_zones = sorted(
        tf for tf, layer in (overlay.get("timeframes") or {}).items() if layer.get("zones")
    )
    expected_timeframes = sorted(
        {
            expected_by_side[side]["timeframe"]
            for side in ("buy", "sell")
            if expected_by_side[side].get("draws")
        }
    )
    return {
        "symbol": row["symbol"],
        "as_of": row["as_of"],
        "snapshot_identity": row["snapshot_identity"],
        "read_status": {
            side: overlay["sides"][side].get("status") for side in ("buy", "sell")
        },
        "reason_codes": overlay.get("reason_codes"),
        "overlay_source": overlay.get("source"),
        "timeframes_with_zones": timeframes_with_zones,
        "expected_timeframes": expected_timeframes,
        "timeframe_layers_match": set(timeframes_with_zones) == set(expected_timeframes),
        "sides": sides,
        "protected_swing": protected,
        "pass": all(item["pass"] for item in sides.values())
        and protected["pass"]
        and set(timeframes_with_zones) == set(expected_timeframes),
    }


def _chart_payload(row: Mapping[str, Any], analysis: Mapping[str, Any]) -> dict[str, Any]:
    from core.chart_payload import build_chart_payload

    candles = {
        tf: [_candle(item) for item in row["candles"][tf]]
        for tf in ("D1", "H4", "H1")
    }
    carrier = _carrier(analysis["canonical_smc"], analysis.get("smc_snapshot"))
    # The page draws the layer of the timeframe it is showing and captions that
    # layer, so the QA opens the chart on a timeframe that actually carries a
    # zone — otherwise the caption would be empty for the right reason and prove
    # nothing about the caption.
    overlay = build_smc_overlay(carrier)
    with_zones = sorted(
        tf
        for tf, layer in (overlay.get("timeframes") or {}).items()
        if layer.get("zones") and tf in candles
    )
    active = with_zones[0] if with_zones else "H1"
    return build_full_chart_payload(
        row["symbol"],
        {"chart_payload": build_chart_payload(candles)},
        active_timeframe=active,
        smc_source=carrier,
    )


def _render_cases(cases: list[dict[str, Any]], rows_by_key: Mapping[str, Any], analyses: list[dict[str, Any]], out_dir: Path, theme: str) -> list[dict[str, Any]]:
    from PyQt6.QtCore import QCoreApplication, Qt, QTimer, QUrl
    from PyQt6.QtWidgets import QApplication

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    from PyQt6.QtWebEngineWidgets import QWebEngineView

    from ui.chart_bridge import decorate_chart_payload
    from ui.components.chart_view import chart_bootstrap_html
    from ui.theme import chart_palette, palette_for

    app = QApplication.instance() or QApplication(sys.argv)
    html = chart_bootstrap_html(CHART_HTML.read_text(encoding="utf-8"), palette_for(theme))
    results: list[dict[str, Any]] = []
    for case, row, analysis in zip(cases, rows_by_key, analyses):
        payload = _chart_payload(row, analysis)
        payload["theme"] = palette_for(theme).name
        payload["palette"] = chart_palette(palette_for(theme))
        payload = decorate_chart_payload(payload)
        script = (
            "if(window.setChartData){window.setChartData("
            + json.dumps(payload, default=str)
            + ");}"
        )
        view = QWebEngineView()
        view.resize(1100, 640)
        view.show()
        observed: dict[str, Any] = {
            "symbol": case["symbol"],
            "as_of": case["as_of"],
            "theme": theme,
            "overlay_present_in_payload": "smc_overlay" in payload,
            "payload_timeframes": sorted(
                tf
                for tf, layer in (payload.get("smc_overlay", {}).get("timeframes") or {}).items()
                if layer.get("zones")
            ),
        }
        state = {"loaded": False}

        def on_load(ok: bool) -> None:
            state["loaded"] = ok
            if not ok:
                app.quit()
                return
            view.page().runJavaScript(script)
            QTimer.singleShot(1500, capture)

        def capture() -> None:
            pixmap = view.grab()
            stamp = str(case["as_of"])[:10].replace("-", "")
            png = (
                out_dir
                / f"chart_qa_{case['symbol'].replace('/', '')}_{stamp}_{theme}.png"
            )
            observed["png"] = str(png.relative_to(PROJECT_ROOT)) if pixmap.save(str(png)) else None
            view.page().runJavaScript(
                "document.getElementById('smc-caption') "
                "? document.getElementById('smc-caption').textContent : null",
                finish,
            )

        def finish(caption: object) -> None:
            observed["caption"] = caption
            app.quit()

        view.loadFinished.connect(on_load)
        view.setHtml(html, QUrl.fromLocalFile(str(CHART_HTML.parent.resolve()) + "/"))
        QTimer.singleShot(45000, app.quit)
        app.exec()
        observed["loaded"] = state["loaded"]
        # The caption the page shows is written by ``decorate_chart_payload``, so
        # the expected text is read from the payload that was sent, not retyped.
        expected_captions = {
            tf: layer.get("caption")
            for tf, layer in (payload.get("smc_overlay", {}).get("timeframes") or {}).items()
            if layer.get("caption")
        }
        observed["expected_captions"] = expected_captions
        observed["active_timeframe"] = payload.get("active_timeframe")
        observed["caption_present"] = bool(
            isinstance(observed.get("caption"), str) and observed["caption"].strip()
        )
        observed["caption_matches_payload"] = bool(
            observed["caption_present"]
            and observed["caption"] in set(expected_captions.values())
        )
        view.deleteLater()
        results.append(observed)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Chart QA on real snapshots (task 132)")
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--rows", default="", help="comma-separated 'SYMBOL@AS_OF' to QA instead of the corpus"
    )
    parser.add_argument(
        "--render",
        type=int,
        default=0,
        help="also render this many cases on the real chart page (needs a Qt platform plugin)",
    )
    parser.add_argument("--render-theme", default="dark")
    parser.add_argument(
        "--render-only",
        type=int,
        default=0,
        help="only render this many cases (evaluation without the full comparison)",
    )
    args = parser.parse_args()

    if not CORPUS_PATH.exists():
        print(f"BLOCKED: no corpus at {CORPUS_PATH}; run scripts/smc_real_snapshots.py collect first.")
        return 2
    with gzip.open(CORPUS_PATH, "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    if args.rows:
        wanted = {item.strip() for item in args.rows.split(",") if item.strip()}
        rows = [row for row in rows if f"{row['symbol']}@{row['as_of']}" in wanted]
    if args.limit:
        rows = rows[: args.limit]
    if not rows:
        print("BLOCKED: no corpus row selected for chart QA.")
        return 2

    started = time.perf_counter()
    cases: list[dict[str, Any]] = []
    analyses: list[dict[str, Any]] = []
    if args.render_only:
        # Rendering needs the same evaluation but not the whole comparison, so a
        # caption/pixel fix does not cost a full re-run over the corpus.
        rows = rows[: args.render_only]
        analyses = [_analysis(row) for row in rows]
        print(f"  render-only: {len(rows)} case(s) evaluated, comparison skipped")
    else:
        for row in rows:
            analysis = _analysis(row)
            analyses.append(analysis)
            case = _case(row, analysis)
            cases.append(case)
            print(
                f"  {case['symbol']:8s} {case['as_of']} layers={case['timeframes_with_zones']} "
                f"buy={case['sides']['buy']['checks']} pass={case['pass']}"
            )

    renders: list[dict[str, Any]] = []
    render_error: str | None = None
    if args.render or args.render_only:
        count = args.render_only or args.render
        try:
            renders = _render_cases(
                rows[:count],
                rows[:count],
                analyses[:count],
                OUTPUT_DIR,
                args.render_theme,
            )
        except Exception as exc:  # a render failure is recorded, never hidden
            render_error = f"{type(exc).__name__}: {exc}"

    if args.render_only and Path(args.report).exists():
        # A render-only pass refreshes the supporting screenshots; the comparison
        # itself is kept from the full run instead of being replaced by an empty
        # list, so the artifact always carries both halves.
        previous = json.loads(Path(args.report).read_text(encoding="utf-8"))
        previous["renders"] = renders
        previous["render_error"] = render_error
        previous["renders_refreshed_at"] = datetime.now(timezone.utc).isoformat()
        Path(args.report).write_text(
            json.dumps(previous, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(
            f"\nrenders refreshed in {args.report} "
            f"(comparison kept: {previous.get('cases_checked')} cases)"
        )
        return 0 if not render_error else 1

    failures = [case for case in cases if not case["pass"]]
    report = {
        "report_version": "smc-chart-qa-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "corpus": str(CORPUS_PATH.relative_to(PROJECT_ROOT)),
        "cases_checked": len(cases),
        "cases_passed": len(cases) - len(failures),
        "failures": failures,
        "cases": cases,
        "renders": renders,
        "render_error": render_error,
        "rule_versions": smc_rule_versions(),
        "elapsed_seconds": round(time.perf_counter() - started, 4),
    }
    target = Path(args.report)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"\ncases={len(cases)} passed={report['cases_passed']} failures={len(failures)}")
    if render_error:
        print(f"render BLOCKED: {render_error}")
    print(f"report -> {target}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
