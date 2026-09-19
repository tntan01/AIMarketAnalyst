"""R2 — app shell, Scanner và Scanner Detail theo logical viewport.

Bốn viewport hợp đồng (`1280×720`, `1366×768`, `1920×1080`, compact `900×560`) ×
hai theme, chạy offscreen với app giả: không MT5, không lệnh, không QSettings
thật (cửa sổ chỉ được resize, không gọi `apply_startup_policy`).

Bài test bám vào hành vi đo được chứ không phải vào một breakpoint hard-code:

* hàng action của Scanner gộp một hàng khi đủ chỗ và tách hai hàng khi thiếu
  ngang — nhờ đó màn hình không bị cắt ở compact;
* bảng Scanner cuộn ngang thay vì bóp cột;
* cột thông tin của Detail giữ đúng sàn nội dung nên checklist không bị elide;
* panel dài cuộn dọc khi nội dung không vừa, và không cuộn khi đã vừa (desktop
  giữ nguyên hình dạng đã duyệt).
"""

from __future__ import annotations

import os
from contextlib import ExitStack
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QLabel, QScrollArea, QWidget

from tools.capture_ui_style_baseline import _fake_app, _patch_external_activity
from tools.ui_layout_audit import load_visual_qa_fonts
from ui.main_window import MainWindow
from ui.responsive_row import ResponsiveRow
from ui.screens.scanner_detail_screen import ScannerDetailScreen
from ui.screens.scanner_screen import ScannerScreen
from ui.theme_manager import ThemeManager

DESKTOP_VIEWPORTS = ((1280, 720), (1366, 768), (1920, 1080))
COMPACT_VIEWPORT = (900, 560)
CONTRACT_VIEWPORTS = (*DESKTOP_VIEWPORTS, COMPACT_VIEWPORT)
MINIMUM_VIEWPORT = (800, 500)

# Ngưỡng tách hàng của thanh tuỳ chọn quét, đo trên máy này: cần 1107px cho
# hàng, tức viewport trong shell ≳ 1220. Desktop 1280+ vì vậy vẫn một hàng.
SCAN_OPTIONS_REQUIRED_WIDTH = 1107


_QT_APP: QApplication | None = None


def _app() -> QApplication:
    """QApplication dùng chung cho cả module.

    Phải giữ tham chiếu ở cấp module: PyQt huỷ QApplication ngay khi wrapper
    Python cuối cùng bị thu hồi, và widget tạo sau đó sẽ làm tiến trình chết.
    """

    global _QT_APP
    app = QApplication.instance() or QApplication([])
    _QT_APP = app
    # Test tự đóng từng widget rời; không để việc đóng cửa sổ cuối kết thúc
    # vòng lặp sự kiện giữa các test.
    app.setQuitOnLastWindowClosed(False)
    return app


# ---------------------------------------------------------------------------
# Fixture dữ liệu — nến/plan thật để Entry/SL/TP có số mà đọc
# ---------------------------------------------------------------------------


def _detail_payload() -> dict[str, Any]:
    row = {
        "symbol": "AUD/NZD",
        "timestamp": "2026-09-19T05:15:34+00:00",
        "price_vs_zone": "in_zone",
        "price_vs_zone_detail": {
            "price": 1.2379,
            "entry_low": 1.2371,
            "entry_high": 1.23913,
            "snapshot_at": "2026-09-19T05:15:34+00:00",
        },
        "entry_price": 1.2381,
        "stop_loss": 1.23489,
        "take_profit": 1.2455,
        "selected_side": "buy",
        "candidate_status": "READY_NOW",
        "risk_reward_base": 2.4,
        "scanner_candidate_decision": {
            "selected_side": "buy",
            "side_evaluation": {
                "side": "buy",
                "stop_loss": 1.23489,
                "take_profit": 1.2455,
                "entry_price": 1.2381,
            },
        },
        "analysis_result": {
            "symbol": "AUD/NZD",
            "scenarios": [
                {
                    "side": "buy",
                    "entry_zone": [1.2371, 1.23913],
                    "stop_loss": 1.23489,
                    "take_profit": 1.2455,
                }
            ],
            "chart_payload": {
                "H1": [
                    {"t": f"2026-09-19T0{h}:00:00+00:00", "o": 1.23, "h": 1.24,
                     "l": 1.22, "c": 1.235}
                    for h in range(4, 9)
                ]
            },
        },
    }
    return {"scanner_row": row, "scanner_result": {}}


def _scanner_rows() -> list[dict[str, Any]]:
    return [
        {
            "presentation_rank": index + 1,
            "symbol": symbol,
            "candidate_status": status,
            "selected_side": side,
            "market_regime": regime,
            "technical_signal_score": 82 - index * 10,
            "setup_score": 74 - index * 10,
            "evidence_confidence": 68 - index * 10,
            "execution_readiness": readiness,
            "expected_effective_rr": 2.4 - index * 0.5,
            "price_vs_zone": zone,
        }
        for index, (symbol, status, side, regime, readiness, zone) in enumerate(
            (
                ("AUD/NZD", "READY_NOW", "buy", "trend_up", "ready", "in_zone"),
                ("EUR/USD", "WAITING_CONFIRMATION", "sell", "range", "watch", "near_zone"),
                ("XAU/USD", "BLOCKED", "neutral", "high_vol", "blocked", "far"),
            )
        )
    ]


# ---------------------------------------------------------------------------
# Fixture cửa sổ — một shell cho cả module, mỗi test tự resize như người dùng
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def shell() -> Any:
    app = _app()
    load_visual_qa_fonts()
    stack = ExitStack()
    _patch_external_activity(stack)
    window = MainWindow(_fake_app("dark"))
    ThemeManager().apply(window, theme="dark")
    window.show()
    app.processEvents()
    yield window
    for screen in window.screens.values():
        for timer_name in ("_auto_refresh_timer", "_scan_timer", "auto_scan_timer"):
            stop = getattr(getattr(screen, timer_name, None), "stop", None)
            if callable(stop):
                stop()
    window.close()
    stack.close()


def _scanner_resized(shell: Any, viewport: tuple[int, int]) -> ScannerScreen:
    app = _app()
    shell.resize(*viewport)
    shell.navigate("scanner")
    app.processEvents()
    screen: ScannerScreen = shell.screens["scanner"]
    if not screen.table_model.rowCount():
        screen.table_model.set_rows(_scanner_rows())
        screen._configure_table_columns()
    app.processEvents()
    return screen


def _detail_resized(shell: Any, viewport: tuple[int, int]) -> ScannerDetailScreen:
    app = _app()
    shell.resize(*viewport)
    shell.navigate("scanner_detail", _detail_payload())
    app.processEvents()
    return shell.screens["scanner_detail"]


# ---------------------------------------------------------------------------
# ResponsiveRow — hành vi gộp/tách hàng
# ---------------------------------------------------------------------------


def _row_widgets(row: ResponsiveRow) -> list[QWidget]:
    return list(row._left) + list(row._right)  # noqa: SLF001 - điểm neo của test


def test_row_uses_one_line_when_there_is_room() -> None:
    app = _app()
    from PyQt6.QtWidgets import QPushButton

    left = [QPushButton("Chế độ"), QPushButton("Quét 1 lần")]
    right = [QPushButton("Quét thị trường"), QPushButton("Kế hoạch lệnh")]
    row = ResponsiveRow(left=left, right=right)
    row.resize(row.required_width() + 120, 60)
    row.show()
    app.processEvents()

    assert row.row_count() == 1
    assert all(widget.isVisibleTo(row) for widget in (*left, *right))
    centers = [widget.mapTo(row, widget.rect().center()).y() for widget in (*left, *right)]
    assert max(centers) - min(centers) <= 1
    row.close()


def test_row_splits_in_two_when_narrow_and_keeps_everything_visible() -> None:
    app = _app()
    from PyQt6.QtWidgets import QPushButton

    left = [QPushButton("Chế độ"), QPushButton("Quét 1 lần")]
    right = [QPushButton("Quét thị trường"), QPushButton("Kế hoạch lệnh")]
    row = ResponsiveRow(left=left, right=right)
    row.resize(max(row.minimumSizeHint().width(), 120), 60)
    row.show()
    app.processEvents()

    assert row.row_count() == 2
    assert all(widget.isVisibleTo(row) for widget in (*left, *right))
    left_bottom = max(widget.mapTo(row, widget.rect().bottomLeft()).y() for widget in left)
    right_top = min(widget.mapTo(row, widget.rect().topLeft()).y() for widget in right)
    assert right_top > left_bottom, "nhóm phải xuống hàng dưới nhóm trái"
    row.close()


def test_row_minimum_width_floor_is_the_two_line_width() -> None:
    _app()
    from PyQt6.QtWidgets import QPushButton

    left = [QPushButton("Chế độ"), QPushButton("Quét 1 lần")]
    right = [QPushButton("Quét thị trường"), QPushButton("Kế hoạch lệnh")]
    row = ResponsiveRow(left=left, right=right)
    spacing = row._spacing  # noqa: SLF001 - đọc hằng số bố cục của chính widget

    def line(widgets):
        return sum(w.sizeHint().width() for w in widgets) + spacing * (len(widgets) - 1)

    assert row.required_width() == line(left) + spacing + line(right)
    assert row.minimumSizeHint().width() == max(line(left), line(right))
    assert row.minimumSizeHint().width() < row.required_width(), (
        "sàn phải là bề ngang của chế độ hai hàng, không phải của chế độ một hàng"
    )


def test_row_never_shows_a_control_the_screen_hid() -> None:
    app = _app()
    from PyQt6.QtWidgets import QPushButton

    hidden = QPushButton("Dừng quét tự động")
    hidden.setVisible(False)
    left = [QPushButton("Chế độ")]
    right = [hidden, QPushButton("Quét thị trường")]
    row = ResponsiveRow(left=left, right=right)
    row.show()

    wide = sum(w.sizeHint().width() for w in (*left, *right)) + row._spacing * 2  # noqa: SLF001
    row.resize(wide + 200, 60)
    app.processEvents()
    assert row.row_count() == 1
    assert hidden.isHidden() is True

    row.resize(row.minimumSizeHint().width(), 60)
    app.processEvents()
    assert row.row_count() == 2
    assert hidden.isHidden() is True, "đổi hàng không được bật lại nút screen đã ẩn"
    assert right[1].isVisibleTo(row) is True
    row.close()


@pytest.mark.parametrize("narrow", [False, True])
def test_row_controls_never_overlap(narrow: bool) -> None:
    app = _app()
    from PyQt6.QtWidgets import QPushButton

    left = [QPushButton("Chế độ"), QPushButton("Quét 1 lần"), QPushButton("Khoảng thời gian")]
    right = [QPushButton("Tự động vào lệnh MT5"), QPushButton("Quét thị trường")]
    row = ResponsiveRow(left=left, right=right)
    width = row.minimumSizeHint().width() if narrow else row.required_width() + 80
    row.resize(width, 60)
    row.show()
    app.processEvents()

    rects = [
        widget.mapTo(row, widget.rect().topLeft()) for widget in (*left, *right)
    ]
    sizes = [widget.size() for widget in (*left, *right)]
    for index, origin in enumerate(rects):
        first = (origin, sizes[index])
        for other_origin, other_size in zip(rects[index + 1 :], sizes[index + 1 :]):
            horizontal = min(
                first[0].x() + first[1].width(), other_origin.x() + other_size.width()
            ) - max(first[0].x(), other_origin.x())
            vertical = min(
                first[0].y() + first[1].height(), other_origin.y() + other_size.height()
            ) - max(first[0].y(), other_origin.y())
            assert not (horizontal > 1 and vertical > 1)
    row.close()


# ---------------------------------------------------------------------------
# Scanner — hàng action, bảng, rail
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("viewport", DESKTOP_VIEWPORTS)
def test_scanner_toolbar_keeps_one_row_at_desktop_viewports(
    shell: Any, viewport: tuple[int, int]
) -> None:
    screen = _scanner_resized(shell, viewport)

    assert screen.scan_options_row.row_count() == 1
    controls = (
        screen.scan_mode_label,
        screen.scan_mode_combo,
        screen.scan_interval_label,
        screen.scan_interval_combo,
        screen.auto_trade_check,
        screen.scan_button,
        screen.show_orders_button,
    )
    centers = [c.mapTo(screen, c.rect().center()).y() for c in controls]
    assert max(centers) - min(centers) <= 1


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_scanner_screen_is_not_clipped_at_the_compact_viewport(theme: str) -> None:
    app = _app()
    load_visual_qa_fonts()
    with ExitStack() as stack:
        _patch_external_activity(stack)
        window = MainWindow(_fake_app(theme))
        ThemeManager().apply(window, theme=theme)
        window.resize(*COMPACT_VIEWPORT)
        window.show()
        window.navigate("scanner")
        app.processEvents()
        screen: ScannerScreen = window.screens["scanner"]
        screen.table_model.set_rows(_scanner_rows())
        screen._configure_table_columns()
        app.processEvents()

        assert screen.width() >= screen.minimumSizeHint().width()
        assert screen.height() >= screen.minimumSizeHint().height()
        assert screen.scan_options_row.row_count() == 2

        # Không control nào thò ra ngoài vùng nhìn thấy của màn hình.
        for control in (
            screen.scan_mode_combo,
            screen.scan_interval_combo,
            screen.auto_trade_check,
            screen.scan_button,
            screen.show_orders_button,
            screen.detail_button,
            screen.save_button,
            screen.brief_button,
        ):
            assert control.isVisibleTo(screen)
            top_left = control.mapTo(screen, control.rect().topLeft())
            assert 0 <= top_left.x()
            assert top_left.x() + control.width() <= screen.width()

        window.close()


@pytest.mark.parametrize("viewport", [(900, 560), (800, 500)])
def test_scanner_table_scrolls_instead_of_squeezing_columns(
    shell: Any, viewport: tuple[int, int]
) -> None:
    screen = _scanner_resized(shell, viewport)
    table = screen.table
    screen._configure_table_columns()
    _app().processEvents()

    widths = [table.columnWidth(i) for i in range(screen.table_model.columnCount())]
    needs = [
        screen._content_width_for_column(i, screen.TABLE_CELL_HORIZONTAL_PADDING)
        for i in range(screen.table_model.columnCount())
    ]

    assert table.horizontalScrollBar().maximum() > 0, "phải cuộn ngang được"
    assert all(
        width >= need for width, need in zip(widths, needs)
    ), "cột không được hẹp hơn bề ngang nội dung của nó"


@pytest.mark.parametrize("viewport", DESKTOP_VIEWPORTS)
def test_scanner_table_fills_the_width_without_scrolling_at_desktop(
    shell: Any, viewport: tuple[int, int]
) -> None:
    screen = _scanner_resized(shell, viewport)
    table = screen.table

    assert table.horizontalScrollBar().maximum() == 0
    total = sum(
        table.columnWidth(i) for i in range(screen.table_model.columnCount())
    )
    assert total <= table.viewport().width()


# ---------------------------------------------------------------------------
# Scanner Detail — cột thông tin, cuộn dọc, Entry/SL/TP, chart
# ---------------------------------------------------------------------------


def _elided_labels(screen: QWidget, object_name: str) -> list[str]:
    elided: list[str] = []
    for label in screen.findChildren(QLabel):
        if label.objectName() != object_name or not label.isVisibleTo(screen):
            continue
        text = label.text() or ""
        if label.fontMetrics().elidedText(
            text, Qt.TextElideMode.ElideRight, label.width()
        ) != text:
            elided.append(text)
    return elided


@pytest.mark.parametrize("viewport", CONTRACT_VIEWPORTS)
def test_detail_left_column_keeps_its_content_minimum(
    shell: Any, viewport: tuple[int, int]
) -> None:
    screen = _detail_resized(shell, viewport)
    left = screen.overview_layout.itemAt(0).widget()

    assert left.width() >= left.minimumSizeHint().width()
    assert _elided_labels(screen, "ScannerChecklistName") == []


@pytest.mark.parametrize("viewport", CONTRACT_VIEWPORTS)
def test_entry_stop_and_target_stay_readable(
    shell: Any, viewport: tuple[int, int]
) -> None:
    screen = _detail_resized(shell, viewport)

    for expected in ("1.23489", "1.24550"):
        labels = [
            label
            for label in screen.findChildren(QLabel)
            if label.isVisibleTo(screen) and expected in (label.text() or "")
        ]
        assert labels, f"{expected} phải hiển thị trên màn hình"
        assert all(
            label.fontMetrics().elidedText(
                label.text(), Qt.TextElideMode.ElideRight, label.width()
            )
            == label.text()
            for label in labels
        )


def test_detail_scrolls_vertically_only_when_the_panel_does_not_fit(shell: Any) -> None:
    app = _app()

    desktop = _detail_resized(shell, (1280, 720))
    desktop_area = desktop.findChildren(QScrollArea)[0]
    assert (
        desktop_area.verticalScrollBarPolicy()
        == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    )
    assert desktop_area.verticalScrollBar().maximum() == 0, (
        "desktop đã vừa thì không được mọc thanh cuộn"
    )

    compact = _detail_resized(shell, COMPACT_VIEWPORT)
    compact_area = compact.findChildren(QScrollArea)[0]
    assert compact_area.widget().minimumSizeHint().height() > (
        compact_area.viewport().height()
    )
    assert compact_area.verticalScrollBar().maximum() > 0, (
        "panel dài ở compact phải cuộn tới được"
    )
    app.processEvents()


def test_chart_absorbs_the_leftover_area_in_every_viewport(shell: Any) -> None:
    for viewport in CONTRACT_VIEWPORTS:
        screen = _detail_resized(shell, viewport)
        left = screen.overview_layout.itemAt(0).widget()
        right = screen.overview_layout.itemAt(1).widget()

        assert screen.overview_layout.stretch(0) == 25
        assert screen.overview_layout.stretch(1) == 75
        assert right.width() > left.width(), "chart nhận phần diện tích dư"
        assert screen.chart_frame.width() >= 360


def test_resize_does_not_republish_the_chart(shell: Any) -> None:
    """Resize chỉ đổi bố cục: không đụng payload/zoom/mật độ nến của chart."""

    app = _app()
    screen = _detail_resized(shell, (1280, 720))
    calls: list[str] = []
    original_payload = screen.chart.set_payload
    original_switch = screen.chart.switch_timeframe
    screen.chart.set_payload = lambda *a, **k: calls.append("set_payload")
    screen.chart.switch_timeframe = lambda *a, **k: calls.append("switch_timeframe")
    try:
        for viewport in (*CONTRACT_VIEWPORTS, (1280, 720)):
            shell.resize(*viewport)
            app.processEvents()
    finally:
        screen.chart.set_payload = original_payload
        screen.chart.switch_timeframe = original_switch

    assert calls == [], f"resize không được đụng chart: {calls}"


# ---------------------------------------------------------------------------
# App shell — rail 48px và minimum R1 giữ nguyên
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("viewport", CONTRACT_VIEWPORTS)
def test_rail_stays_48px_and_window_minimum_is_unchanged(
    shell: Any, viewport: tuple[int, int]
) -> None:
    shell.resize(*viewport)
    _app().processEvents()

    assert shell.sidebar_width == 48
    assert shell.sidebar.width() == 48
    assert shell.minimumSize().width() == 800
    assert shell.minimumSize().height() == 500
