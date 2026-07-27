"""Capture the Phase-0 visual baseline without external services.

The harness uses the real widgets and QSS, while replacing MT5, network calls,
workers and persistence with in-memory doubles.  It does not mutate application
settings or production data.
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QImageReader, QPainter
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from services.settings_service import SettingsService
from ui.main_window import MainWindow
from ui.screens import backtest_screen as backtest_module
from ui.screens.backtest_screen import BacktestScreen, SymbolSelectionDialog
from ui.screens.dashboard_screen import DashboardScreen
from ui.screens.journal_screen import JournalScreen, MetricsExplanationDialog
from ui.screens.orders_screen import OrdersScreen
from ui.screens.scanner_screen import (
    ScannerColumnsHelpDialog,
    ScannerRowExplanationDialog,
    ScannerScreen,
    ScannerSymbolSelectionDialog,
    ScannerTableModel,
)
from ui.screens.settings_screen import SettingsScreen
from ui.theme_manager import ThemeManager
DEFAULT_OUTPUT = ROOT / "docs" / "ui-baseline" / "current"
CANVAS = (1600, 900)
SUITE_ROUTES = (
    "dashboard",
    "scanner",
    "orders",
    "scanner_detail",
    "backtest",
    "journal",
    "journal_detail",
    "settings",
)
SUITE_SECTIONS = ("runtime", "explicit", "states")
SUITE_EXPECTED_PER_THEME = 40


def _slug(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "unnamed"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


class SnapshotWriter:
    def __init__(
        self,
        output: Path,
        theme: str,
        app: QApplication,
        *,
        canvas: tuple[int, int] = CANVAS,
    ) -> None:
        self.output = output
        self.theme = theme
        self.app = app
        self.canvas = canvas
        self.captures: list[dict[str, object]] = []
        self.failures: list[dict[str, str]] = []
        self._names: CounterLike = CounterLike()
        (output / theme).mkdir(parents=True, exist_ok=True)

    def capture(self, widget: QWidget, name: str, *, dialog: bool = False) -> None:
        base = _slug(name)
        sequence = self._names.next(base)
        suffix = f"-{sequence}" if sequence > 1 else ""
        path = self.output / self.theme / f"{base}{suffix}.png"
        try:
            if dialog:
                hint = widget.sizeHint()
                widget.resize(
                    max(widget.width(), hint.width(), 420),
                    max(widget.height(), hint.height(), 240),
                )
            else:
                widget.resize(*self.canvas)
            widget.show()
            widget.raise_()
            self.app.processEvents()
            # Render into an offscreen image instead of relying on a native
            # window handle. This keeps screen/dialog captures deterministic
            # when the desktop application is already running and avoids
            # platform-specific grabWindow deadlocks.
            image = QImage(widget.size(), QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            widget.render(painter)
            painter.end()
            if image.isNull() or not image.save(str(path), "PNG"):
                raise RuntimeError("Qt could not save the widget pixmap")
            self.captures.append(
                {
                    "theme": self.theme,
                    "name": name,
                    "kind": "dialog" if dialog else "screen",
                    "path": _manifest_path(path),
                    "width": image.width(),
                    "height": image.height(),
                    "sha256": _sha256(path),
                }
            )
            print(
                f"[{self.theme}] captured {name} "
                f"({image.width()}x{image.height()})",
                flush=True,
            )
        except Exception as exc:
            self.failures.append(
                {
                    "theme": self.theme,
                    "name": name,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    def record_failure(self, name: str, exc: Exception) -> None:
        self.failures.append(
            {
                "theme": self.theme,
                "name": name,
                "error": f"{type(exc).__name__}: {exc}",
            }
        )


class CounterLike:
    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    def next(self, key: str) -> int:
        value = self._counts.get(key, 0) + 1
        self._counts[key] = value
        return value


class FakeSettingsService:
    def __init__(self, theme: str) -> None:
        self.settings = deepcopy(SettingsService().load())
        self.settings.display.theme = theme

    def load(self):
        return self.settings

    def save(self, settings) -> None:
        self.settings = settings


def _fake_app(theme: str) -> SimpleNamespace:
    catalog = MagicMock()
    catalog.load.return_value = {}
    return SimpleNamespace(
        settings_service=FakeSettingsService(theme),
        mt5=MagicMock(),
        scanner_controller=MagicMock(),
        backtest_controller=MagicMock(),
        journal_controller=MagicMock(),
        ai_catalog_service=catalog,
    )


def _patch_external_activity(stack: ExitStack) -> None:
    stack.enter_context(
        patch.object(DashboardScreen, "_refresh_market_overview", lambda self: None)
    )
    stack.enter_context(
        patch.object(DashboardScreen, "refresh_news_section", lambda self: None)
    )
    stack.enter_context(
        patch.object(DashboardScreen, "refresh_status", lambda self: None)
    )
    stack.enter_context(
        patch.object(OrdersScreen, "refresh_orders", lambda self: None)
    )
    stack.enter_context(
        patch.object(OrdersScreen, "_load_trailing_state", lambda self: None)
    )
    stack.enter_context(
        patch.object(ScannerScreen, "_run_scan", lambda self: None)
    )
    stack.enter_context(
        patch.object(SettingsScreen, "refresh_mt5_status", lambda self: None)
    )
    stack.enter_context(
        patch.object(JournalScreen, "_refresh_performance", lambda self: None)
    )
    stack.enter_context(
        patch.object(JournalScreen, "refresh_status", lambda self: None)
    )


def _capture_visible_tabs(
    writer: SnapshotWriter,
    window: MainWindow,
    screen: QWidget,
    route: str,
) -> None:
    visible_tabs = [
        tab
        for tab in screen.findChildren(QTabWidget)
        if tab.isVisibleTo(screen) and tab.count() > 0
    ]
    if not visible_tabs:
        return
    # Every current screen has a single primary tab set. Nested tab containers
    # are either single-page presentation widgets or are covered by the parent
    # page capture. Avoid recursive combinations, which add duplicate images.
    tabs = visible_tabs[0]
    original = tabs.currentIndex()
    for page_index in range(tabs.count()):
        if page_index == original:
            continue
        tabs.setCurrentIndex(page_index)
        writer.app.processEvents()
        writer.capture(
            window,
            f"screen-{route}-tab-{page_index}-{tabs.tabText(page_index)}",
        )
    tabs.setCurrentIndex(original)
    writer.app.processEvents()


def _capture_settings_tabs(
    writer: SnapshotWriter,
    window: MainWindow,
    screen: QWidget,
) -> None:
    tabs_list = [
        tabs
        for tabs in screen.findChildren(QTabWidget)
        if tabs.isVisibleTo(screen) and tabs.count() > 0
    ]
    if not tabs_list:
        return
    tabs = tabs_list[0]
    original = tabs.currentIndex()
    for page_index in range(tabs.count()):
        if page_index == original:
            continue
        tabs.setCurrentIndex(page_index)
        writer.app.processEvents()
        writer.capture(
            window,
            f"screen-settings-tab-{page_index}-{tabs.tabText(page_index)}",
        )
    tabs.setCurrentIndex(original)
    writer.app.processEvents()


def _repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def _state_gallery(theme: str) -> QDialog:
    dialog = QDialog()
    dialog.setWindowTitle("UI component state baseline")
    dialog.setObjectName("AnalysisDetailDialog")
    root = QVBoxLayout(dialog)
    title = QLabel("Trạng thái component")
    title.setObjectName("ActionTitle")
    root.addWidget(title)

    grid = QGridLayout()
    grid.setHorizontalSpacing(12)
    grid.setVerticalSpacing(10)
    root.addLayout(grid)

    widgets: list[tuple[str, QWidget]] = []
    primary = QPushButton("Primary")
    primary.setObjectName("PrimaryButton")
    widgets.append(("Mặc định", primary))

    secondary = QPushButton("Secondary")
    secondary.setObjectName("SecondaryButton")
    widgets.append(("Phụ", secondary))

    disabled = QPushButton("Disabled")
    disabled.setObjectName("PrimaryButton")
    disabled.setEnabled(False)
    widgets.append(("Vô hiệu hóa", disabled))

    checked = QPushButton("Checked")
    checked.setObjectName("SecondaryButton")
    checked.setCheckable(True)
    checked.setChecked(True)
    widgets.append(("Đã chọn", checked))

    field = QLineEdit("Giá trị nhập")
    field.setObjectName("FilterField")
    widgets.append(("Ô nhập", field))

    invalid = QLineEdit("Không hợp lệ")
    invalid.setObjectName("FilterField")
    invalid.setProperty("state", "error")
    widgets.append(("Validation lỗi", invalid))

    checkbox = QCheckBox("Đã bật")
    checkbox.setChecked(True)
    widgets.append(("Checkbox", checkbox))

    for state in ("ok", "warning", "danger"):
        card = QFrame()
        card.setObjectName("StatusCard")
        card.setProperty("state", state)
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(10, 6, 10, 6)
        value = QLabel(state.upper())
        value.setObjectName("CardValue")
        card_layout.addWidget(value)
        widgets.append((f"Status {state}", card))

    for row, (label, widget) in enumerate(widgets):
        grid.addWidget(QLabel(label), row, 0)
        grid.addWidget(widget, row, 1)
        _repolish(widget)

    dialog._baseline_primary = primary
    dialog._baseline_field = field
    dialog._baseline_disabled = disabled
    dialog._baseline_checked = checked
    dialog._baseline_invalid = invalid
    ThemeManager().apply(dialog, theme=theme)
    return dialog


def _capture_state_gallery(writer: SnapshotWriter) -> None:
    gallery = _state_gallery(writer.theme)
    writer.capture(gallery, "state-default", dialog=True)
    field = gallery._baseline_field
    field.setFocus()
    writer.app.processEvents()
    writer.capture(gallery, "state-focus", dialog=True)

    button = gallery._baseline_primary
    QTest.mouseMove(button, button.rect().center())
    writer.app.processEvents()
    writer.capture(gallery, "state-hover", dialog=True)
    QTest.mousePress(
        button,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        button.rect().center(),
    )
    writer.app.processEvents()
    writer.capture(gallery, "state-pressed", dialog=True)
    QTest.mouseRelease(
        button,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        button.rect().center(),
    )
    gallery._baseline_disabled.setFocus()
    writer.app.processEvents()
    writer.capture(gallery, "state-disabled", dialog=True)
    gallery._baseline_checked.setFocus()
    writer.app.processEvents()
    writer.capture(gallery, "state-checked", dialog=True)
    gallery._baseline_invalid.setFocus()
    writer.app.processEvents()
    writer.capture(gallery, "state-validation", dialog=True)
    gallery.close()
    gallery.deleteLater()


def _capture_explicit_dialogs(
    writer: SnapshotWriter,
    window: MainWindow,
) -> None:
    dialogs: list[tuple[str, QDialog]] = [
        (
            "dialog-backtest-symbol-selection",
            SymbolSelectionDialog(["EUR/USD"], window),
        ),
        (
            "dialog-scanner-symbol-selection",
            ScannerSymbolSelectionDialog(
                ["EUR/USD", "GBP/USD", "XAU/USD"],
                {"EUR/USD"},
                {"EUR/USD", "GBP/USD"},
                ["EUR/USD"],
                window,
            ),
        ),
        (
            "dialog-scanner-row-explanation",
            ScannerRowExplanationDialog(
                {
                    "symbol": "EUR/USD",
                    "status": "ready",
                    "selected_side": "buy",
                    "final_score": 72,
                    "opportunity_score": 68,
                    "rr": 2.1,
                },
                ScannerTableModel(),
                window,
            ),
        ),
        (
            "dialog-scanner-columns-help",
            ScannerColumnsHelpDialog(window),
        ),
        (
            "dialog-journal-metrics-help",
            MetricsExplanationDialog(window),
        ),
    ]
    for name, dialog in dialogs:
        writer.capture(dialog, name, dialog=True)
        dialog.close()
        dialog.deleteLater()


def _capture_runtime_dialogs(
    writer: SnapshotWriter,
    window: MainWindow,
) -> None:
    current_name = {"value": "dialog-runtime"}

    def capture_exec(dialog: QDialog) -> int:
        writer.capture(dialog, current_name["value"], dialog=True)
        dialog.close()
        return int(QDialog.DialogCode.Rejected)

    def run(name: str, callback) -> None:
        current_name["value"] = name
        try:
            callback()
        except Exception as exc:
            writer.record_failure(name, exc)

    with patch.object(QDialog, "exec", capture_exec):
        # Capture the rich Backtest/Scanner Detail dialogs first. Repeated
        # native grabs of many earlier dialogs can starve embedded rich-text
        # surfaces on the offscreen platform.
        backtest: BacktestScreen = window.screens["backtest"]
        backtest._ai_thread = MagicMock()
        with patch.object(backtest, "_generate_stats_html", return_value=""):
            run(
                "dialog-backtest-ai-analysis",
                lambda: backtest._on_ai_analysis_done(
                    "Kết luận: hiệu suất ổn định trong mẫu baseline."
                ),
            )

        action = SimpleNamespace(
            visible=True,
            label="💾 Lưu bản nháp",
            kind=backtest_module.ACTION_SAVE_DRAFT,
        )
        config = {
            "status": "DRAFT",
            "regime": "aligned",
            "side": "buy",
            "min_score": 65,
            "min_rr": 2.0,
            "_evidence": "Đủ dữ liệu nghiên cứu baseline",
            "out_of_sample_trades": 0,
            "walk_forward_windows": 0,
            "validation_reasons": [],
        }
        backtest.result = {"summary": {}}
        import core.backtest_config_validation as validation_module

        with patch.object(
            backtest_module,
            "result_action",
            return_value=action,
        ), patch.object(
            validation_module,
            "build_backtest_config",
            return_value=config,
        ):
            run("dialog-backtest-config", backtest._apply_scanner_config)

        scanner_detail = window.screens["scanner_detail"]
        scanner_detail.row = {
            "symbol": "EUR/USD",
            "status": "ready",
            "selected_side": "buy",
            "final_score": 72,
            "best_score": 72,
            "buy_score": 72,
            "sell_score": 41,
            "opportunity_score": 68,
            "min_score": 65,
            "rr": 2.1,
            "entry_price": 1.085,
            "stop_loss": 1.08,
            "take_profit": 1.095,
            "direction_bias": {
                "best_side": "buy",
                "is_clear_bias": True,
            },
        }
        scanner_detail.scanner_result = {}
        run(
            "dialog-scanner-analysis-detail",
            scanner_detail._show_scan_detail_dialog,
        )

        dashboard = window.screens["dashboard"]
        run("dialog-dashboard-market-help", dashboard._show_market_help)
        run(
            "dialog-dashboard-headline",
            lambda: dashboard._show_headline_detail(
                {
                    "title": "Lạm phát hạ nhiệt, thị trường chờ quyết định lãi suất",
                    "source": "Baseline News",
                    "url": "https://example.com",
                    "display_time": datetime.now(timezone.utc),
                },
                timezone.utc,
            ),
        )
        run(
            "dialog-dashboard-event",
            lambda: dashboard._show_event_detail(
                {
                    "impact": "high",
                    "currency": "USD",
                    "event": "CPI",
                    "forecast": "3.0%",
                    "previous": "3.2%",
                },
                datetime.now(timezone.utc) + timedelta(days=1),
                timezone.utc,
            ),
        )

        scanner = window.screens["scanner"]
        scanner._market_brief_text = (
            "## Tổng quan\n- USD đang tích lũy.\n"
            "- EUR/USD chờ xác nhận cấu trúc."
        )
        run("dialog-scanner-market-brief", scanner._show_market_brief_impl)

        scanner.scan_result = {
            "rows": [{"symbol": "EUR/USD"}],
            "auto_trade_results": {"enabled": False},
            "rollout_policy": {"stage": "LIVE"},
        }
        order = {
            "symbol": "EUR/USD",
            "broker_symbol": "EURUSD",
            "side": "buy",
            "entry_price": 1.085,
            "stop_loss": 1.08,
            "take_profit": 1.095,
            "volume": 0.1,
            "price_digits": 5,
        }
        with patch.object(
            scanner,
            "_build_order_rows",
            return_value=[order],
        ):
            run("dialog-scanner-orders", scanner._show_orders_dialog)

        orders = window.screens["orders"]
        position = {
            "position_id": 12345,
            "symbol": "EURUSD",
            "side": "buy",
            "sl": 1.08,
            "volume": 0.1,
            "profit": 25.0,
            "swap": -0.2,
            "open_price": 1.085,
        }
        with patch.object(
            orders,
            "_get_selected_position",
            return_value=position,
        ):
            run("dialog-orders-trailing-stop", orders._show_trailing_dialog)


def capture_theme(
    app: QApplication,
    output: Path,
    theme: str,
    *,
    section: str = "all",
    routes: set[str] | None = None,
    canvas: tuple[int, int] = CANVAS,
) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    fake_app = _fake_app(theme)
    writer = SnapshotWriter(output, theme, app, canvas=canvas)
    with ExitStack() as stack:
        _patch_external_activity(stack)
        window = MainWindow(fake_app)
        window.resize(*canvas)
        window.show()
        app.processEvents()

        if section in {"all", "runtime"}:
            _capture_runtime_dialogs(writer, window)

        if section in {"all", "screens"}:
            selected_routes = routes or set(window.screens)
            for route, screen in window.screens.items():
                if route not in selected_routes:
                    continue
                window.navigate(route)
                app.processEvents()
                writer.capture(window, f"screen-{route}")
                if route == "settings":
                    _capture_settings_tabs(writer, window, screen)
                else:
                    _capture_visible_tabs(writer, window, screen, route)

        if section in {"all", "states"}:
            _capture_state_gallery(writer)
        if section in {"all", "explicit"}:
            _capture_explicit_dialogs(writer, window)

        for screen in window.screens.values():
            for timer_name in ("_refresh_timer", "_trail_timer"):
                timer = getattr(screen, timer_name, None)
                if timer is not None:
                    timer.stop()
        window.close()
        window.deleteLater()
        app.processEvents()
    return writer.captures, writer.failures


def manifest_from_images(
    output: Path,
    *,
    canvas: tuple[int, int] = CANVAS,
) -> Path:
    captures: list[dict[str, object]] = []
    for theme in ("dark", "light"):
        for path in sorted((output / theme).glob("*.png")):
            reader = QImageReader(str(path))
            size = reader.size()
            captures.append(
                {
                    "theme": theme,
                    "name": path.stem,
                    "kind": (
                        "dialog"
                        if path.stem.startswith(("dialog-", "state-"))
                        else "screen"
                    ),
                    "path": _manifest_path(path),
                    "width": size.width(),
                    "height": size.height(),
                    "sha256": _sha256(path),
                }
            )
    return write_manifest(output, captures, [], canvas=canvas)


def write_manifest(
    output: Path,
    captures: list[dict[str, object]],
    failures: list[dict[str, str]],
    *,
    canvas: tuple[int, int] = CANVAS,
) -> Path:
    manifest = {
        "schema_version": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "canvas": {"width": canvas[0], "height": canvas[1]},
        "themes": ["dark", "light"],
        "external_services": "disabled",
        "captures": captures,
        "failures": failures,
    }
    path = output / "screenshot-manifest.json"
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _suite_jobs() -> list[tuple[str, str, str | None]]:
    jobs: list[tuple[str, str, str | None]] = []
    for theme in ("dark", "light"):
        jobs.extend((theme, "screens", route) for route in SUITE_ROUTES)
        jobs.extend((theme, section, None) for section in SUITE_SECTIONS)
    return jobs


def _run_capture_suite(
    output: Path,
    *,
    canvas: tuple[int, int],
    timeout_seconds: int,
    retries: int,
) -> int:
    existing_images = list(output.glob("dark/*.png")) + list(
        output.glob("light/*.png")
    )
    if existing_images:
        print(
            "Suite output must be empty to prevent stale baseline images: "
            f"{output}",
            flush=True,
        )
        return 1

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8:backslashreplace"
    canvas_arg = f"{canvas[0]}x{canvas[1]}"
    for theme, section, route in _suite_jobs():
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--output",
            str(output),
            "--theme",
            theme,
            "--section",
            section,
            "--canvas",
            canvas_arg,
        ]
        if route is not None:
            command.extend(("--routes", route))
        label = f"{theme}/{section}/{route or 'all'}"
        for attempt in range(1, retries + 2):
            try:
                completed = subprocess.run(
                    command,
                    cwd=ROOT,
                    env=env,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="backslashreplace",
                    timeout=timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                print(
                    f"[{label}] timeout on attempt {attempt}",
                    flush=True,
                )
                continue
            if completed.stdout:
                print(completed.stdout.rstrip(), flush=True)
            if completed.returncode == 0:
                break
            if completed.stderr:
                print(completed.stderr.rstrip(), flush=True)
            print(
                f"[{label}] failed on attempt {attempt} "
                f"with exit code {completed.returncode}",
                flush=True,
            )
        else:
            print(f"Capture suite failed permanently: {label}", flush=True)
            return 1

    manifest_path = manifest_from_images(output, canvas=canvas)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    captures = manifest["captures"]
    themed_names = {
        theme: {
            item["name"] for item in captures if item["theme"] == theme
        }
        for theme in ("dark", "light")
    }
    expected_total = SUITE_EXPECTED_PER_THEME * 2
    if (
        len(captures) != expected_total
        or any(
            len(names) != SUITE_EXPECTED_PER_THEME
            for names in themed_names.values()
        )
        or themed_names["dark"] != themed_names["light"]
    ):
        print(
            "Capture suite coverage mismatch: "
            f"total={len(captures)}, "
            f"dark={len(themed_names['dark'])}, "
            f"light={len(themed_names['light'])}",
            flush=True,
        )
        return 1
    print(
        f"Capture suite complete: {len(captures)} images; "
        f"manifest={manifest_path}",
        flush=True,
    )
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--theme", choices=("dark", "light"))
    parser.add_argument(
        "--section",
        choices=("all", "screens", "runtime", "states", "explicit"),
        default="all",
    )
    parser.add_argument(
        "--routes",
        help="Comma-separated screen routes; only used with --section screens.",
    )
    parser.add_argument(
        "--canvas",
        default=f"{CANVAS[0]}x{CANVAS[1]}",
        help="Screen capture size in WIDTHxHEIGHT form.",
    )
    parser.add_argument(
        "--finalize",
        action="store_true",
        help="Build screenshot-manifest.json from previously captured images.",
    )
    parser.add_argument(
        "--suite",
        action="store_true",
        help=(
            "Capture the complete dark/light baseline in isolated, retried "
            "subprocess jobs. The output directory must not contain PNG files."
        ),
    )
    parser.add_argument(
        "--job-timeout",
        type=int,
        default=60,
        help="Timeout in seconds for each isolated --suite job.",
    )
    parser.add_argument(
        "--job-retries",
        type=int,
        default=1,
        help="Number of retries after the first --suite job attempt.",
    )
    args = parser.parse_args()
    canvas_match = re.fullmatch(r"(\d+)x(\d+)", args.canvas.strip().lower())
    if canvas_match is None:
        parser.error("--canvas must use WIDTHxHEIGHT, for example 1366x768")
    canvas = (int(canvas_match.group(1)), int(canvas_match.group(2)))
    if canvas[0] < 800 or canvas[1] < 600:
        parser.error("--canvas must be at least 800x600")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    if args.suite:
        return _run_capture_suite(
            output,
            canvas=canvas,
            timeout_seconds=max(10, args.job_timeout),
            retries=max(0, args.job_retries),
        )

    app = QApplication.instance() or QApplication([])
    if args.finalize:
        manifest = manifest_from_images(output, canvas=canvas)
        print(f"Wrote screenshot manifest: {manifest}")
        return 0

    all_captures: list[dict[str, object]] = []
    all_failures: list[dict[str, str]] = []
    themes = (args.theme,) if args.theme else ("dark", "light")
    routes = (
        {route.strip() for route in args.routes.split(",") if route.strip()}
        if args.routes
        else None
    )
    for theme in themes:
        captures, failures = capture_theme(
            app,
            output,
            theme,
            section=args.section,
            routes=routes,
            canvas=canvas,
        )
        all_captures.extend(captures)
        all_failures.extend(failures)

    print(
        f"Captured {len(all_captures)} images; "
        f"failures={len(all_failures)}"
    )
    if all_failures:
        for failure in all_failures:
            print(
                f"{failure['theme']} {failure['name']}: "
                f"{failure['error']}"
            )
        return 1
    app.closeAllWindows()
    app.processEvents()
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
