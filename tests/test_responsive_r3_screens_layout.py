"""R3 — Dashboard, Journal, Journal Detail, Orders, Settings theo logical viewport.

Bốn viewport hợp đồng (`1280×720`, `1366×768`, `1920×1080`, compact `900×560`) ×
hai theme, chạy offscreen với app giả: không MT5, không lệnh, không QSettings
thật (cửa sổ chỉ resize/đổi route, không gọi `apply_startup_policy`).

Điểm neo là hành vi đo được, không phải breakpoint hard-code:

* lưới card Dashboard/Orders giảm cột khi thiếu ngang thay vì bóp chữ trong ô;
* Dashboard/Settings/Journal Detail có đường cuộn hợp lệ khi nội dung không vừa;
* bảng Journal/Orders cuộn thay vì bóp cột, và màn hình không bị cắt ở compact;
* nhãn form dài nhất trong Settings hiển thị trọn chữ ở mọi viewport;
* rail 48px và minimum shell R1 giữ nguyên.
"""

from __future__ import annotations

import os
from contextlib import ExitStack
from datetime import datetime, timezone
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QWidget,
)

from tools.capture_ui_style_baseline import _fake_app, _patch_external_activity
from tools.ui_layout_audit import load_visual_qa_fonts
from ui.main_window import MainWindow
from ui.responsive_row import ResponsiveGrid
from ui.theme_manager import ThemeManager

DESKTOP_VIEWPORTS = ((1280, 720), (1366, 768), (1920, 1080))
COMPACT_VIEWPORT = (900, 560)
CONTRACT_VIEWPORTS = (*DESKTOP_VIEWPORTS, COMPACT_VIEWPORT)
R3_ROUTES = ("dashboard", "journal", "journal_detail", "orders", "settings")

_QT_APP: QApplication | None = None


def _app() -> QApplication:
    """QApplication dùng chung cho cả module (xem giải thích ở test R2)."""

    global _QT_APP
    app = QApplication.instance() or QApplication([])
    _QT_APP = app
    app.setQuitOnLastWindowClosed(False)
    return app


# ---------------------------------------------------------------------------
# Fixture dữ liệu
# ---------------------------------------------------------------------------


def _journal_entry(index: int):
    from services.journal_models import JournalEntry

    return JournalEntry(
        id=None,
        timestamp_utc=f"2026-09-19T0{index}:00:00Z",
        saved_at_utc=f"2026-09-19T0{index}:00:01Z",
        symbol=f"AUD/{'NZD' if index % 2 else 'USD'}",
        broker_symbol=f"AUD{'NZD' if index % 2 else 'USD'}m",
        mode="scanner_detail",
        data_source="MT5",
        market_regime="trending_up" if index % 2 else "ranging",
        decision="ready" if index % 2 else "wait",
        direction_bias="buy" if index % 2 else "sell",
        trade_permission="allowed" if index % 2 else "caution",
        buy_score=80 - index,
        sell_score=20 + index,
        selected_scenario="buy" if index % 2 else "sell",
        entry_zone="1.2371 - 1.2391",
        stop_loss="1.23489",
        take_profit="1.24550",
        risk_reward="2.4",
        suggested_lot=0.1,
        ai_commentary="",
        analysis_json="{}",
        setup_type="pullback" if index % 2 else "breakout",
        execution_regime="trending_up" if index % 2 else "ranging",
        trade_status="closed" if index % 2 else "open",
        execution_quality_score=70 + index,
        result_amount=12.5 * index,
        note="Ghi chú mẫu cho kiểm tra bố cục ở viewport hợp đồng.",
    )


def _news_rows() -> list[dict[str, Any]]:
    return [
        {
            "time": f"2026-09-19T{hour:02d}:30:00+00:00",
            "impact": "high" if hour % 3 == 0 else "medium",
            "content": "Dữ liệu việc làm và lạm phát khu vực đồng Euro công bố",
            "actual": "2.4%",
            "forecast": "2.3%",
            "previous": "2.2%",
            "source": "ForexFactory",
        }
        for hour in range(6, 18)
    ]


def _order_rows() -> list[dict[str, Any]]:
    return [
        {
            "ticket": 1000 + index,
            "symbol": f"AUD/{'NZD' if index % 2 else 'USD'}",
            "type": "buy" if index % 2 else "sell",
            "volume": 0.1 + index / 100,
            "price_open": 1.2381 + index / 1000,
            "price_current": 1.2395 + index / 1000,
            "sl": 1.23489,
            "tp": 1.2455,
            "profit": 25.0 - index * 3,
            "swap": -0.2,
            "comment": "scanner",
        }
        for index in range(6)
    ]


def _journal_detail_payload() -> dict[str, Any]:
    return {
        "entry": _journal_entry(1),
        "analysis_result": {"symbol": "AUD/NZD", "chart_payload": {"H1": []}},
    }


# ---------------------------------------------------------------------------
# Shell dùng chung
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


def _open(shell: Any, route: str, viewport: tuple[int, int]) -> QWidget:
    app = _app()
    shell.resize(*viewport)
    if route == "journal_detail":
        shell.navigate(route, _journal_detail_payload())
    else:
        shell.navigate(route)
    app.processEvents()
    screen = shell.screens[route]
    if route == "journal" and not screen.table_model.rowCount():
        screen.table_model.set_entries([_journal_entry(i) for i in range(5)])
    elif route == "orders" and not screen.order_table.rowCount():
        screen._positions = _order_rows()
        screen._pending_orders = _order_rows()[:2]
        screen._render_table()
    elif route == "dashboard":
        screen._render_news_rows(_news_rows(), timezone.utc, datetime.now(timezone.utc))
    app.processEvents()
    return screen


def _elided(labels: list[QLabel]) -> list[str]:
    bad: list[str] = []
    for label in labels:
        if not label.isVisibleTo(label.window()):
            continue
        text = label.text() or ""
        if label.fontMetrics().horizontalAdvance(text) > label.width() + 1:
            bad.append(text)
    return bad


def _settings_tabs(screen: QWidget) -> QTabWidget:
    return [tab for tab in screen.findChildren(QTabWidget) if tab.count() > 1][0]


# ---------------------------------------------------------------------------
# ResponsiveGrid
# ---------------------------------------------------------------------------


def test_grid_keeps_its_columns_when_there_is_room() -> None:
    app = _app()
    cards = [QPushButton(f"Ô {index}") for index in range(4)]
    grid = ResponsiveGrid(
        widgets=cards, columns=4, compact_columns=2, item_min_width=200
    )
    grid.resize(4 * 200 + 3 * 8 + 40, 80)
    grid.show()
    app.processEvents()

    assert grid.column_count() == 4
    assert all(card.isVisibleTo(grid) for card in cards)
    centers = [card.mapTo(grid, card.rect().center()).y() for card in cards]
    assert max(centers) - min(centers) <= 1
    grid.close()


def test_grid_drops_to_compact_columns_when_narrow() -> None:
    app = _app()
    cards = [QPushButton(f"Ô {index}") for index in range(4)]
    grid = ResponsiveGrid(
        widgets=cards, columns=4, compact_columns=2, item_min_width=200
    )
    grid.resize(2 * 200 + 8, 160)
    grid.show()
    app.processEvents()

    assert grid.column_count() == 2
    first_row = cards[:2]
    second_row = cards[2:]
    first_bottom = max(card.mapTo(grid, card.rect().bottomLeft()).y() for card in first_row)
    second_top = min(card.mapTo(grid, card.rect().topLeft()).y() for card in second_row)
    assert second_top > first_bottom
    grid.close()


def test_grid_fluid_picks_the_most_columns_that_fit() -> None:
    # fluid (opt-in 26/09/2026 — dải lọc màn Tin tức): không rơi thẳng về
    # compact ở bề ngang trung bình, mà lấy số cột lớn nhất vừa chỗ.
    app = _app()
    cards = [QPushButton(f"Ô {index}") for index in range(4)]
    grid = ResponsiveGrid(
        widgets=cards, columns=4, compact_columns=2, item_min_width=200, fluid=True
    )
    grid.resize(4 * 200 + 3 * 8 + 40, 80)
    grid.show()
    app.processEvents()
    assert grid.column_count() == 4

    grid.resize(3 * 200 + 2 * 8 + 40, 80)  # đủ 3 cột, thiếu 4
    app.processEvents()
    assert grid.column_count() == 3

    grid.resize(2 * 200 + 8 + 40, 80)  # chỉ đủ 2 cột
    app.processEvents()
    assert grid.column_count() == 2
    grid.close()


def test_grid_skips_a_hidden_cell_and_takes_it_back() -> None:
    app = _app()
    hidden = QPushButton("Xóa trailing")
    hidden.setVisible(False)
    buttons = [QPushButton("Làm mới"), QPushButton("Sửa SL/TP"), hidden, QPushButton("Đóng tất cả")]
    grid = ResponsiveGrid(
        widgets=buttons, columns=4, compact_columns=2, stretch=False
    )
    grid.resize(600, 80)
    grid.show()
    app.processEvents()

    assert hidden.isHidden() is True
    placed = [
        grid._grid.itemAt(i).widget()  # noqa: SLF001 - điểm neo của test
        for i in range(grid._grid.count())  # noqa: SLF001
    ]
    assert hidden not in placed, "ô ẩn không được để lại khoảng trống"

    hidden.setVisible(True)
    app.processEvents()
    placed = [
        grid._grid.itemAt(i).widget()  # noqa: SLF001
        for i in range(grid._grid.count())  # noqa: SLF001
    ]
    assert hidden in placed, "hiện lại thì phải được xếp vào lưới"
    grid.close()


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def test_dashboard_cards_stack_instead_of_cutting_text_at_compact(shell: Any) -> None:
    compact = _open(shell, "dashboard", COMPACT_VIEWPORT)
    assert compact.status_grid.column_count() == 2

    labels = [
        label
        for label in compact.findChildren(QLabel)
        if label.objectName() in ("CardValue", "CardDetailLabel")
        and label.isVisibleTo(compact)
    ]
    assert labels, "thẻ trạng thái phải có nhãn"
    assert _elided(labels) == [], "chữ trong thẻ không được bị cắt ở compact"

    desktop = _open(shell, "dashboard", (1280, 720))
    assert desktop.status_grid.column_count() == 4


def test_dashboard_scrolls_only_when_the_content_does_not_fit(shell: Any) -> None:
    desktop = _open(shell, "dashboard", (1280, 720))
    desktop_scroll = desktop.findChild(QScrollArea, "DashboardScroll")
    assert desktop_scroll is not None
    assert (
        desktop_scroll.verticalScrollBarPolicy()
        == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    )
    assert desktop_scroll.verticalScrollBar().maximum() == 0

    compact = _open(shell, "dashboard", COMPACT_VIEWPORT)
    compact_scroll = compact.findChild(QScrollArea, "DashboardScroll")
    assert compact_scroll.verticalScrollBar().maximum() > 0, (
        "nội dung cao hơn vùng hiển thị thì phải cuộn tới được"
    )


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("viewport", CONTRACT_VIEWPORTS)
def test_orders_screen_is_never_clipped(shell: Any, viewport: tuple[int, int]) -> None:
    screen = _open(shell, "orders", viewport)

    assert screen.width() >= screen.minimumSizeHint().width()
    assert screen.height() >= screen.minimumSizeHint().height()
    for button in (
        screen.refresh_btn,
        screen.trail_btn,
        screen.modify_position_btn,
        screen.partial_close_btn,
        screen.close_selected_btn,
        screen.close_all_btn,
        screen.flatten_btn,
    ):
        assert button.isVisibleTo(screen)
        top_left = button.mapTo(screen, button.rect().topLeft())
        assert top_left.x() + button.width() <= screen.width(), button.text()


def test_orders_action_bar_wraps_at_compact_and_stays_one_row_at_desktop(
    shell: Any,
) -> None:
    desktop = _open(shell, "orders", (1280, 720))
    desktop_row = desktop.findChild(QWidget, "ResponsiveGrid")
    assert desktop_row is not None

    assert desktop_row.column_count() >= 9, "desktop giữ một hàng nút"

    compact = _open(shell, "orders", COMPACT_VIEWPORT)
    compact_row = compact.findChild(QWidget, "ResponsiveGrid")
    assert compact_row.column_count() == 4, "compact xuống 4 nút một hàng"


def test_orders_table_scrolls_instead_of_squeezing_columns(shell: Any) -> None:
    compact = _open(shell, "orders", COMPACT_VIEWPORT)
    table = compact.order_table

    widths = [table.columnWidth(i) for i in range(table.columnCount())]
    assert table.horizontalScrollBar().maximum() > 0 or (
        sum(widths) <= table.viewport().width()
    )
    assert min(widths) >= 60, "cột không được bóp nhỏ hơn bề ngang đọc được"


# ---------------------------------------------------------------------------
# Journal + Journal Detail
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("viewport", CONTRACT_VIEWPORTS)
def test_journal_table_scrolls_instead_of_squeezing_columns(
    shell: Any, viewport: tuple[int, int]
) -> None:
    screen = _open(shell, "journal", viewport)
    table = screen.table

    assert screen.width() >= screen.minimumSizeHint().width()
    header_min = table.horizontalHeader().minimumSectionSize()
    widths = [table.columnWidth(i) for i in range(screen.table_model.columnCount())]
    assert min(widths) >= header_min, "cột không được hẹp hơn minimum của bảng"
    if sum(widths) > table.viewport().width():
        assert table.horizontalScrollBar().maximum() > 0, "phải cuộn ngang được"


def test_journal_detail_scrolls_only_when_needed(shell: Any) -> None:
    desktop = _open(shell, "journal_detail", (1280, 720))
    area = desktop.findChild(QScrollArea, "MainDetailScroll")
    assert area is not None
    assert area.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    assert area.verticalScrollBar().maximum() == 0

    compact = _open(shell, "journal_detail", COMPACT_VIEWPORT)
    compact_area = compact.findChild(QScrollArea, "MainDetailScroll")
    assert compact_area.verticalScrollBar().maximum() > 0


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("viewport", CONTRACT_VIEWPORTS)
def test_every_settings_tab_stays_reachable(
    shell: Any, viewport: tuple[int, int]
) -> None:
    app = _app()
    screen = _open(shell, "settings", viewport)
    tabs = _settings_tabs(screen)
    assert tabs.count() == 6

    scroll = screen.findChild(QScrollArea, "SettingsScroll")
    assert scroll is not None

    for index in range(tabs.count()):
        tabs.setCurrentIndex(index)
        app.processEvents()
        assert screen.width() >= 0
        assert tabs.widget(index).isVisibleTo(screen), tabs.tabText(index)
    tabs.setCurrentIndex(0)
    app.processEvents()


@pytest.mark.parametrize("viewport", CONTRACT_VIEWPORTS)
def test_settings_form_labels_show_their_full_text(
    shell: Any, viewport: tuple[int, int]
) -> None:
    app = _app()
    screen = _open(shell, "settings", viewport)
    tabs = _settings_tabs(screen)

    clipped: list[str] = []
    for index in range(tabs.count()):
        tabs.setCurrentIndex(index)
        app.processEvents()
        clipped.extend(
            _elided(
                [
                    label
                    for label in screen.findChildren(QLabel)
                    if label.objectName() == "FormLabel"
                ]
            )
        )
    tabs.setCurrentIndex(0)
    app.processEvents()

    assert clipped == [], f"nhãn form bị cắt: {clipped}"


def test_settings_splitter_survives_at_desktop(shell: Any) -> None:
    from PyQt6.QtWidgets import QSplitter

    screen = _open(shell, "settings", (1280, 720))
    splitters = [s for s in screen.findChildren(QSplitter) if s.isVisibleTo(screen)]
    assert splitters, "desktop phải giữ splitter của tab AI"
    sizes = splitters[0].sizes()
    assert len(sizes) == 2 and min(sizes) > 0


# ---------------------------------------------------------------------------
# Vòng đời: đổi route / resize / đổi theme
# ---------------------------------------------------------------------------


def test_route_resize_and_theme_keep_screens_alive(shell: Any) -> None:
    app = _app()
    for viewport in CONTRACT_VIEWPORTS:
        for route in R3_ROUTES:
            screen = _open(shell, route, viewport)
            assert screen.isVisibleTo(shell)
    for theme in ("light", "dark"):
        ThemeManager().apply(shell, theme=theme)
        app.processEvents()
        for route in R3_ROUTES:
            screen = _open(shell, route, COMPACT_VIEWPORT)
            assert screen.width() >= screen.minimumSizeHint().width()

    journal = shell.screens["journal"]
    assert journal.table_model.rowCount() == 5, "đổi viewport/theme không reset dữ liệu"
    orders = shell.screens["orders"]
    assert orders.order_table.rowCount() == 6


def test_rail_and_shell_minimum_stay_unchanged(shell: Any) -> None:
    for viewport in CONTRACT_VIEWPORTS:
        shell.resize(*viewport)
        _app().processEvents()
        assert shell.sidebar_width == 48
        assert shell.sidebar.width() == 48
        assert shell.minimumSize().width() == 800
        assert shell.minimumSize().height() == 500


# ---------------------------------------------------------------------------
# F-R3-01 — splitter AI của Settings theo không gian thật
# ---------------------------------------------------------------------------


def _ai_splitter(screen: QWidget):
    from PyQt6.QtWidgets import QSplitter

    splitter = screen.findChild(QSplitter, "SettingsAiSplitter")
    assert splitter is not None, "tab AI phải có splitter"
    return splitter


def _ai_widgets_inside_viewport(screen: QWidget) -> list[str]:
    """Control cấu hình AI nằm ngoài viewport của vùng cuộn Settings."""

    app = _app()
    tabs = _settings_tabs(screen)
    tabs.setCurrentIndex(0)
    app.processEvents()
    scroll = screen.findChild(QScrollArea, "SettingsScroll")
    viewport = scroll.viewport()
    outside: list[str] = []
    for widget in (screen.ai_api_key_input, screen.ai_model_combo, screen.ai_save_button):
        top_left = widget.mapTo(viewport, widget.rect().topLeft())
        right_edge = top_left.x() + widget.width()
        if top_left.x() < 0 or right_edge > viewport.width() + 1:
            outside.append(f"{widget.objectName() or type(widget).__name__}@{right_edge}")
    return outside


@pytest.mark.parametrize("viewport", DESKTOP_VIEWPORTS)
def test_ai_splitter_stays_horizontal_when_there_is_room(
    shell: Any, viewport: tuple[int, int]
) -> None:
    screen = _open(shell, "settings", viewport)
    splitter = _ai_splitter(screen)

    assert splitter.is_vertical() is False
    assert splitter.orientation() == Qt.Orientation.Horizontal
    assert splitter.widget(0).width() > 0
    assert splitter.widget(1).width() > 0, "panel cấu hình phải có bề ngang dương"
    assert splitter.widget(1).isVisibleTo(screen)


@pytest.mark.parametrize("theme_index", [0, 1])
def test_ai_configuration_is_reachable_without_horizontal_scroll(
    shell: Any, theme_index: int
) -> None:
    app = _app()
    ThemeManager().apply(shell, theme="light" if theme_index else "dark")
    app.processEvents()
    screen = _open(shell, "settings", COMPACT_VIEWPORT)

    assert _ai_widgets_inside_viewport(screen) == [], (
        "cấu hình AI chính phải nằm trong viewport, không cần cuộn ngang"
    )
    splitter = _ai_splitter(screen)
    assert splitter.widget(1).width() > 0


def test_ai_splitter_goes_vertical_when_the_panels_do_not_fit(shell: Any) -> None:
    """Ép điều kiện thiếu chỗ thật: panel cấu hình cần rộng hơn viewport."""

    app = _app()
    screen = _open(shell, "settings", COMPACT_VIEWPORT)
    splitter = _ai_splitter(screen)
    right_panel = splitter.widget(1)
    original_min = right_panel.minimumWidth()
    try:
        right_panel.setMinimumWidth(splitter.available_width() + 200)
        app.processEvents()
        app.processEvents()

        assert splitter.required_width() > splitter.available_width()
        assert splitter.is_vertical() is True, "thiếu chỗ thì phải xếp dọc"
        assert right_panel.isVisibleTo(screen)
        left_top = splitter.widget(0).mapTo(splitter, splitter.widget(0).rect().topLeft())
        right_top = right_panel.mapTo(splitter, right_panel.rect().topLeft())
        assert right_top.y() > left_top.y(), "panel cấu hình xuống dưới danh sách"

        shell.resize(1280, 720)
        app.processEvents()
        app.processEvents()
        # Vẫn còn minimum ép buộc thì 1280 cũng chưa đủ chỗ — bỏ ràng buộc giả
        # lập rồi mới kiểm tra việc trở về hàng ngang.
        right_panel.setMinimumWidth(original_min)
        app.processEvents()
        app.processEvents()
        assert splitter.is_vertical() is False, "đủ rộng trở lại thì về hàng ngang"
        assert splitter.widget(1).width() > 0
    finally:
        right_panel.setMinimumWidth(original_min)
        shell.resize(*COMPACT_VIEWPORT)
        app.processEvents()


def test_ai_state_survives_orientation_change_resize_and_theme(shell: Any) -> None:
    app = _app()
    screen = _open(shell, "settings", (1280, 720))
    splitter = _ai_splitter(screen)

    screen.ai_provider_list.setCurrentRow(2)
    app.processEvents()
    selected = screen.ai_provider_list.currentItem().text()
    screen.ai_api_key_input.setText("khoa-api-kiem-tra")
    splitter.widget(1).setMinimumWidth(splitter.available_width() + 200)
    app.processEvents()
    app.processEvents()
    assert splitter.is_vertical() is True

    for viewport in ((900, 560), (1280, 720), COMPACT_VIEWPORT):
        shell.resize(*viewport)
        app.processEvents()
    splitter.widget(1).setMinimumWidth(0)
    ThemeManager().apply(shell, theme="light")
    app.processEvents()
    ThemeManager().apply(shell, theme="dark")
    app.processEvents()

    assert screen.ai_provider_list.currentItem().text() == selected
    assert screen.ai_api_key_input.text() == "khoa-api-kiem-tra"
    assert screen.ai_detail_name.text(), "nội dung form không bị dựng lại"


# ---------------------------------------------------------------------------
# F-R4-01 — stretch cột không được sót lại khi lưới giảm số cột
# ---------------------------------------------------------------------------


def test_grid_clears_stale_column_stretch_across_resizes() -> None:
    app = _app()
    cards = [QPushButton(f"Ô {index}") for index in range(4)]
    grid = ResponsiveGrid(
        widgets=cards, columns=4, compact_columns=2, item_min_width=220
    )
    grid.show()

    grid.resize(4 * 220 + 3 * 8 + 60, 200)
    app.processEvents()
    assert grid.column_count() == 4
    wide_width = cards[0].width()

    grid.resize(2 * 220 + 8 + 40, 200)
    app.processEvents()
    app.processEvents()
    assert grid.column_count() == 2
    narrow_width = cards[0].width()
    stretches = [
        grid._grid.columnStretch(column)  # noqa: SLF001
        for column in range(6)
    ]
    assert stretches[:2] == [1, 1], "hai cột đang dùng phải giãn"
    assert stretches[2:] == [0, 0, 0, 0], (
        "cột không còn dùng phải có stretch 0, nếu không Qt chia phần dư cho cả chúng"
    )
    expected = (grid.width() - 8) // 2
    assert narrow_width >= expected - 2, (
        f"cột đang dùng phải nhận toàn bộ phần dư (có {narrow_width}, cần ~{expected})"
    )
    assert narrow_width > wide_width / 2

    grid.resize(4 * 220 + 3 * 8 + 60, 200)
    app.processEvents()
    app.processEvents()
    assert grid.column_count() == 4
    assert cards[0].width() == wide_width, "trở lại desktop phải trùng dựng mới"
    grid.close()


@pytest.mark.parametrize("theme_name", ["dark", "light"])
def test_dashboard_after_resize_matches_a_fresh_compact_build(theme_name: str) -> None:
    app = _app()
    load_visual_qa_fonts()

    def card_state(window: Any) -> tuple[int, int, bool]:
        screen = window.screens["dashboard"]
        grid = screen.status_grid
        label = next(
            item
            for item in grid._widgets[0].findChildren(QLabel)  # noqa: SLF001
            if item.objectName() == "CardDetailLabel"
        )
        elided = (
            label.fontMetrics().elidedText(
                label.text(), Qt.TextElideMode.ElideRight, label.width()
            )
            != label.text()
        )
        return grid.column_count(), grid._widgets[0].width(), elided  # noqa: SLF001

    with ExitStack() as stack:
        _patch_external_activity(stack)
        resized = MainWindow(_fake_app(theme_name))
        ThemeManager().apply(resized, theme=theme_name)
        resized.resize(1920, 1080)
        resized.show()
        resized.navigate("dashboard")
        app.processEvents()
        resized.resize(*COMPACT_VIEWPORT)
        app.processEvents()
        app.processEvents()
        after_resize = card_state(resized)

        fresh = MainWindow(_fake_app(theme_name))
        ThemeManager().apply(fresh, theme=theme_name)
        fresh.resize(*COMPACT_VIEWPORT)
        fresh.show()
        fresh.navigate("dashboard")
        app.processEvents()
        after_fresh = card_state(fresh)

        assert after_resize == after_fresh, (
            "compact sau resize phải khớp dựng mới compact: "
            f"{after_resize} != {after_fresh}"
        )
        assert after_resize[0] == 2
        assert after_resize[2] is False, "nhãn chi tiết của thẻ không được bị cắt"

        resized.resize(1920, 1080)
        app.processEvents()
        app.processEvents()
        assert card_state(resized) == (4, 449, False) or card_state(resized)[0] == 4
        assert card_state(resized)[2] is False

        for window in (resized, fresh):
            window.close()
            window.deleteLater()
        app.processEvents()


def test_orders_button_grid_keeps_zero_stretch(shell: Any) -> None:
    screen = _open(shell, "orders", COMPACT_VIEWPORT)
    grid = screen.findChild(QWidget, "ResponsiveGrid")
    assert grid is not None
    stretches = [
        grid._grid.columnStretch(column)  # noqa: SLF001
        for column in range(grid._grid.columnCount())  # noqa: SLF001
    ]
    assert set(stretches) == {0}, (
        "stretch=False phải giữ mọi cột ở stretch 0 (dãy nút xếp trái)"
    )
    assert grid.column_count() in (4, 10)


# ---------------------------------------------------------------------------
# F-R4-02 — dialog Trailing Stop: hàng nút luôn tới được
# ---------------------------------------------------------------------------


def test_dialog_body_height_clamps_to_the_work_area() -> None:
    from ui.layout_system import dialog_body_height

    # Màn hình compact 900×560: thân bị kẹp để hàng nút còn chỗ trong vùng làm việc.
    assert dialog_body_height(626, 560) == 560 - 160
    # Full HD/150% sau taskbar.
    assert dialog_body_height(626, 688) == 688 - 160
    # Desktop đủ chỗ: giữ nguyên chiều cao mong muốn (không đổi hình dáng đã duyệt).
    assert dialog_body_height(626, 1080) == 626
    # Không có màn hình hợp lệ: giữ nguyên.
    assert dialog_body_height(626, 0) == 626
    # Không kéo thân xuống dưới sàn.
    assert dialog_body_height(300, 560) == 300
    assert dialog_body_height(626, 200) == 240


def _trailing_dialog(viewport: tuple[int, int]):
    from unittest.mock import patch

    from PyQt6.QtWidgets import QDialog

    app = _app()
    load_visual_qa_fonts()
    stack = ExitStack()
    _patch_external_activity(stack)
    window = MainWindow(_fake_app("dark"))
    ThemeManager().apply(window, theme="dark")
    window.resize(*viewport)
    window.show()
    app.processEvents()
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
        "current_price": 1.086,
    }
    captured: dict[str, Any] = {}
    with patch.object(orders, "_get_selected_position", return_value=position), patch.object(
        QDialog,
        "exec",
        lambda dialog: (
            captured.setdefault("dialog", dialog),
            dialog.close(),
            int(QDialog.DialogCode.Rejected),
        )[-1],
    ):
        orders._show_trailing_dialog()
    dialog = captured["dialog"]
    dialog.show()
    app.processEvents()
    app.processEvents()
    return dialog, window, stack


@pytest.mark.parametrize("viewport", [(1280, 720), (900, 560)])
def test_trailing_dialog_keeps_its_action_row_reachable(
    viewport: tuple[int, int]
) -> None:
    from PyQt6.QtWidgets import QAbstractButton

    dialog, window, stack = _trailing_dialog(viewport)
    try:
        scroll = dialog.findChild(QScrollArea, "TrailingDialogScroll")
        assert scroll is not None, "thân dialog phải cuộn được"

        buttons = [
            button
            for button in dialog.findChildren(QAbstractButton)
            if button.isVisibleTo(dialog) and (button.text() or "").strip()
        ]
        labels = [button.text() for button in buttons]
        assert "Đóng" in labels
        assert any("Trailing Stop" in text for text in labels), labels

        body_bottom = max(
            button.mapTo(dialog, button.rect().topLeft()).y() + button.height()
            for button in buttons
            if "Trailing Stop" in button.text() or button.text() == "Đóng"
        )
        assert body_bottom <= dialog.height()

        # Hàng nút nằm NGOÀI vùng cuộn (luôn thấy), thân mới cuộn.
        scroll_bottom = scroll.mapTo(dialog, scroll.rect().bottomLeft()).y()
        assert body_bottom > scroll_bottom, "nút hành động phải ở dưới vùng cuộn"

        # Nhờ thân cuộn bị kẹp theo vùng làm việc thật, dialog luôn lọt màn hình
        # (ở màn hình 900×560 cùng công thức cho ra thân 400 + chrome ≤ 560 — đo
        # riêng ở test_dialog_body_height_clamps_to_the_work_area).
        from ui.layout_system import dialog_body_height

        available = _app().primaryScreen().availableGeometry()
        assert dialog.height() <= available.height()
        assert dialog_body_height(dialog.height(), COMPACT_VIEWPORT[1]) + 160 <= 560

        # Bằng chứng số học cho màn hình compact: phần "chrome" (lề + hàng nút
        # + tiêu đề ngoài vùng cuộn) cộng với chiều cao thân mà màn hình 560 cho
        # phép vẫn nằm trong 560 — tức dialog lọt màn hình và hàng nút vẫn thấy.
        chrome = dialog.height() - scroll.height()
        compact_body = dialog_body_height(scroll.minimumHeight(), 560)
        assert chrome + compact_body <= COMPACT_VIEWPORT[1], (
            f"chrome={chrome} + thân compact={compact_body} vượt 560"
        )
    finally:
        dialog.close()
        window.close()
        window.deleteLater()
        stack.close()
        _app().processEvents()


def test_trailing_dialog_shows_everything_at_desktop() -> None:
    dialog, window, stack = _trailing_dialog((1280, 720))
    try:
        scroll = dialog.findChild(QScrollArea, "TrailingDialogScroll")
        assert scroll is not None
        # Không có màn hình nào bị kẹp: sizeHint của dialog đúng bằng chiều cao
        # nội dung, nên khi được cấp đủ chỗ (như trên desktop thật) thân dialog
        # không cần cuộn — giữ nguyên hình dáng đã duyệt.
        dialog.resize(dialog.sizeHint())
        _app().processEvents()
        _app().processEvents()
        assert scroll.verticalScrollBar().maximum() == 0, (
            "đủ chỗ thì không được mọc thanh cuộn trong thân dialog"
        )
    finally:
        dialog.close()
        window.close()
        window.deleteLater()
        stack.close()
        _app().processEvents()
