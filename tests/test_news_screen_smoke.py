"""Smoke + hợp đồng hiển thị của màn Quản lý tin (plan lô L3.2).

Kiểm ba nhóm hành vi của khung màn (screen_design "Bố cục" + "Trạng thái tải và
rỗng"), không kiểm hành vi của các lô sau:

* **Từ điển hiển thị (S5):** mọi nhãn enum hiển thị đúng chuỗi đã đăng ký ở
  screen_design d.1557, nhãn cột/bộ lọc/nút đúng khối "Bố cục" — không nhãn nào
  tự đặt;
* **Bảng + bộ lọc + chi tiết dòng:** bảng hợp nhất sự kiện/tin văn bản, lọc theo
  tập enum contract, dialog chi tiết có provenance (`nguồn`, `giờ fetch`,
  `raw_json` nếu có, liên kết ngoài khi tin có URL);
* **Trạng thái tải và rỗng:** chỉ báo loading khi đọc, empty state đúng câu chữ
  đã đăng ký khi lọc rỗng.

Controller là **fake có kiểu** (trả mô hình miền thật của `core/news_models`),
không mock sâu, không DB, không mạng.  Test chạy offscreen; artifact (nếu có) ghi
vào `tmp_path` — không ghi gì vào repo.
"""

from __future__ import annotations

import contextlib
import os
import sys
import threading
import time
from datetime import UTC, datetime
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton

from core.news_models import (
    CalendarEvent,
    EventImpact,
    EventSource,
    EventStatus,
    ImpactHint,
    NewsItem,
    NewsItemKind,
    NewsItemSource,
)
from ui.main_window import MainWindow, nav_route
from ui.navigation import NAV_ICONS, NAV_ITEMS
from ui.screens import news_screen as news
from ui.screens.news_screen import NewsScreen, NewsTableModel, build_rows, filter_rows
from tools.capture_ui_style_baseline import _fake_app, _patch_external_activity

# QApplication phải được giữ ở phạm vi module (khuôn tests/test_dashboard_status_cards.py):
# nếu để nó chỉ sống trong một biến cục bộ, Python thu hồi wrapper ⇒ Qt huỷ ứng dụng
# ⇒ mọi widget đã dựng bị xoá theo ("wrapped C/C++ object has been deleted").
_APP = QApplication.instance() or QApplication(sys.argv)


def _app() -> QApplication:
    return _APP


EVENT = CalendarEvent(
    day_key="2026-09-20",
    event_time_utc="2026-09-20T14:30:00Z",
    currency="USD",
    title="FOMC Meeting",
    impact=EventImpact.HIGH,
    status=EventStatus.RELEASED,
    source=EventSource.FF_HTML,
    dedupe_key="event-1",
    fetched_at="2026-09-20T15:00:00Z",
    forecast="5.50%",
    previous="5.25%",
    actual="5.50%",
    raw_json='{"country": "USD", "title": "FOMC Meeting"}',
    id=11,
)
HEADLINE = NewsItem(
    kind=NewsItemKind.HEADLINE,
    source=NewsItemSource.GOOGLE_NEWS_RSS,
    title="Fed signals patience",
    content="Powell said the committee can wait.",
    url="https://example.com/fed",
    published_utc="2026-09-21T08:00:00Z",
    currencies=["USD", "EUR"],
    impact_hint=ImpactHint.MEDIUM,
    dedupe_key="item-1",
    fetched_at="2026-09-21T09:00:00Z",
    id=22,
)
EXCLUDED_NOTE = NewsItem(
    kind=NewsItemKind.USER_NOTE,
    source=NewsItemSource.USER,
    title="Ghi chú nội bộ",
    content="Theo dõi thêm.",
    published_utc="2026-09-22T07:00:00Z",
    currencies=["JPY"],
    dedupe_key="item-2",
    fetched_at="2026-09-22T07:05:00Z",
    excluded=True,
    id=33,
)


class FakeNewsController:
    """Controller giả có kiểu: ghi lại lời gọi, trả mô hình miền thật."""

    def __init__(
        self,
        events: list[CalendarEvent] | None = None,
        items: list[NewsItem] | None = None,
    ) -> None:
        self.events = [EVENT] if events is None else events
        self.items = [HEADLINE, EXCLUDED_NOTE] if items is None else items
        self.event_calls: list[tuple[str, str]] = []
        self.item_calls: list[tuple[str, str, bool]] = []

    def events_in_range(self, from_utc, to_utc, currencies=None, include_non_impact=True):
        self.event_calls.append((from_utc, to_utc))
        return list(self.events)

    def items_in_range(self, from_utc, to_utc=None, kinds=None, currencies=None, exclude_flagged=True):
        self.item_calls.append((from_utc, to_utc, exclude_flagged))
        return list(self.items)


_SCREENS: list[NewsScreen] = []


@pytest.fixture(scope="module", autouse=True)
def _close_screens():
    """Đóng mọi màn đã dựng (dừng worker nền) trước khi kết thúc module."""
    yield
    for screen in _SCREENS:
        screen.shutdown()
    _app().processEvents()


def _screen(
    controller: FakeNewsController | None = None, *, wait: bool = True
) -> NewsScreen:
    app = _app()
    controller = controller or FakeNewsController()
    fake_app = SimpleNamespace(news_controller=controller)
    screen = NewsScreen(None, app=fake_app)
    screen.resize(752, 500)
    screen.show()
    app.processEvents()
    _SCREENS.append(screen)
    if wait:
        # Lượt đọc nền phải xong trong test (worker + thread không sống ngoài test).
        _wait_until(lambda: bool(controller.event_calls and controller.item_calls))
        app.processEvents()
    return screen


def _wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _app().processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def _labels(screen: NewsScreen) -> list[str]:
    return [label.text() for label in screen.findChildren(QLabel)]


def _texts(screen: NewsScreen) -> set[str]:
    """Mọi chuỗi đang hiển thị trên màn (nhãn + nút) — để đối chiếu từ điển."""
    texts = {label.text() for label in screen.findChildren(QLabel)}
    texts |= {button.text() for button in screen.findChildren(QPushButton)}
    return texts


def _combo_texts(screen: NewsScreen, combo) -> list[str]:
    return [combo.itemText(index) for index in range(combo.count())]


# ---- 1. từ điển hiển thị (S5) --------------------------------------------------


class TestDisplayDictionary:
    def test_status_labels_match_the_registered_dictionary(self):
        assert news.STATUS_TEXT == {
            "scheduled": "Chưa tới giờ",
            "released": "Đã có số liệu",
            "stale": "Thiếu số liệu",
        }
        assert news.EXCLUDED_TEXT == "Đã loại trừ"

    def test_kind_source_impact_labels_match_the_registered_dictionary(self):
        assert news.KIND_TEXT == {
            "headline": "Headline",
            "statement": "Phát biểu",
            "user_note": "Nhập tay",
        }
        assert news.IMPACT_TEXT == {
            "high": "Cao",
            "medium": "Trung bình",
            "low": "Thấp",
            "non": "Không đáng kể",
        }
        assert news.SOURCE_TEXT == {
            "ff_json": "ForexFactory (lịch)",
            "ff_html": "ForexFactory (actual)",
            "google_news_rss": "Google News",
            "fxstreet_rss": "FXStreet",
            "investing_rss": "Investing",
            "fred": "FRED",
            "config_fallback": "Cấu hình dự phòng",
            "user": "Nhập tay",
            "import": "Nhập file",
        }

    def test_column_filter_and_toolbar_labels_are_the_registered_block(self):
        assert news.COLUMN_LABELS == (
            "Thời gian",
            "Loại",
            "Nguồn",
            "Đồng tiền",
            "Tiêu đề/Nội dung",
            "Tác động",
            "Thực tế",
            "Trạng thái",
            "Chi tiết",
        )
        assert news.FILTER_LABELS == (
            "Loại tin",
            "Đồng tiền",
            "Tác động",
            "Nguồn",
            "Trạng thái",
            "Khoảng ngày",
        )
        assert news.TOOLBAR_LABELS == (
            "Lấy lịch kinh tế",
            "Cập nhật actual",
            "Nhập tin",
            "Xuất file",
            "Nhập file",
            "AI nhận định xu hướng",
        )


# ---- 2. bảng: dòng + nhãn từng ô ----------------------------------------------


class TestTableModel:
    def _model(self) -> NewsTableModel:
        model = NewsTableModel()
        model.set_rows(build_rows([EVENT], [HEADLINE, EXCLUDED_NOTE]))
        return model

    def test_rows_are_merged_and_sorted_by_time(self):
        rows = build_rows([EVENT], [HEADLINE, EXCLUDED_NOTE])

        assert [row.timestamp_utc for row in rows] == [
            "2026-09-20T14:30:00Z",
            "2026-09-21T08:00:00Z",
            "2026-09-22T07:00:00Z",
        ]
        assert [row.row_type for row in rows] == [news.EVENT_ROW, news.ITEM_ROW, news.ITEM_ROW]

    def test_headers_are_the_registered_column_labels(self):
        model = self._model()

        headers = [
            model.headerData(index, Qt.Orientation.Horizontal)
            for index in range(model.columnCount())
        ]
        assert headers == list(news.COLUMN_LABELS)

    def test_event_row_shows_the_registered_labels(self):
        model = self._model()
        index = model.index(0, 0)

        def cell(column: int) -> str:
            return model.data(model.index(0, column), Qt.ItemDataRole.DisplayRole)

        assert model.data(index, Qt.ItemDataRole.DisplayRole) == "20/09/2026 14:30"
        assert cell(1) == news.EVENT_TEXT
        assert cell(2) == "ForexFactory (actual)"
        assert cell(3) == "USD"
        assert cell(4) == "FOMC Meeting"
        assert cell(5) == "Cao"
        assert cell(6) == "5.50%"
        assert cell(7) == "Đã có số liệu"
        assert cell(8) == "Chi tiết"

    def test_item_row_shows_kind_source_and_impact_hint_labels(self):
        model = self._model()
        row = 1

        def cell(column: int) -> str:
            return model.data(model.index(row, column), Qt.ItemDataRole.DisplayRole)

        assert cell(1) == "Headline"
        assert cell(2) == "Google News"
        assert cell(3) == "USD, EUR"
        assert cell(5) == "Trung bình"
        assert cell(6) == news.NO_VALUE  # tin văn bản không có "thực tế"
        assert cell(7) == news.NO_VALUE  # không có trạng thái sự kiện, không bị loại trừ

    def test_excluded_item_shows_the_registered_flag_label(self):
        model = self._model()

        def cell(row: int, column: int) -> str:
            return model.data(model.index(row, column), Qt.ItemDataRole.DisplayRole)

        assert cell(2, 1) == "Nhập tay"
        assert cell(2, 2) == "Nhập tay"
        assert cell(2, 7) == news.EXCLUDED_TEXT
        assert cell(2, 3) == "JPY"

    def test_status_and_impact_cells_carry_a_semantic_colour(self):
        model = self._model()

        status_color = model.data(model.index(0, 7), Qt.ItemDataRole.ForegroundRole)
        excluded_color = model.data(model.index(2, 7), Qt.ItemDataRole.ForegroundRole)
        detail_color = model.data(model.index(0, 8), Qt.ItemDataRole.ForegroundRole)

        assert status_color is not None and status_color.isValid()
        assert excluded_color is not None and excluded_color.isValid()
        assert detail_color is not None and detail_color.isValid()
        assert status_color != excluded_color


# ---- 3. bộ lọc ----------------------------------------------------------------


class TestFilters:
    def test_filters_use_the_contract_enum_values(self):
        rows = build_rows([EVENT], [HEADLINE, EXCLUDED_NOTE])

        assert filter_rows(rows, kind=news.EVENT_ROW) == [rows[0]]
        assert filter_rows(rows, kind="headline") == [rows[1]]
        assert filter_rows(rows, kind="user_note") == [rows[2]]
        assert filter_rows(rows, currency="EUR") == [rows[1]]
        assert filter_rows(rows, impact="high") == [rows[0]]
        assert filter_rows(rows, source="user") == [rows[2]]
        assert filter_rows(rows, status="released") == [rows[0]]
        assert filter_rows(rows, status="excluded") == [rows[2]]

    def test_no_filter_returns_every_row(self):
        rows = build_rows([EVENT], [HEADLINE, EXCLUDED_NOTE])

        assert filter_rows(rows) == rows


# ---- 4. khung màn: nhãn, bộ lọc, thanh công cụ, khoảng ngày --------------------


class TestScreenLayout:
    def test_screen_shows_header_filters_and_toolbar_labels(self):
        screen = _screen()
        texts = _texts(screen)

        assert "Tin tức" in texts
        assert "Quản lý tin" in texts
        for label in news.FILTER_LABELS:
            assert label in texts, label
        for label in news.TOOLBAR_LABELS:
            assert label in texts, label

    def test_filter_combos_offer_registered_labels_and_enum_values(self):
        screen = _screen()

        kind = _combo_texts(screen, screen.kind_combo)
        assert kind == ["Tất cả loại tin", news.EVENT_TEXT, "Headline", "Phát biểu", "Nhập tay"]
        assert [screen.kind_combo.itemData(i) for i in range(1, screen.kind_combo.count())] == [
            "event",
            "headline",
            "statement",
            "user_note",
        ]

        status = _combo_texts(screen, screen.status_combo)
        assert status == [
            "Tất cả trạng thái",
            "Chưa tới giờ",
            "Đã có số liệu",
            "Thiếu số liệu",
            "Đã loại trừ",
        ]
        impact = _combo_texts(screen, screen.impact_combo)
        assert impact == ["Tất cả tác động", "Cao", "Trung bình", "Thấp", "Không đáng kể"]

    def test_currency_options_come_from_the_loaded_rows(self):
        screen = _screen()
        _wait_until(lambda: screen.table_model.rowCount() > 0)

        assert _combo_texts(screen, screen.currency_combo) == ["Tất cả đồng tiền", "EUR", "JPY", "USD"]

    def test_toolbar_buttons_are_drawn_but_not_wired_in_this_batch(self):
        screen = _screen()

        assert set(screen.toolbar_buttons) == set(news.TOOLBAR_LABELS)
        for button in screen.toolbar_buttons.values():
            assert button.isEnabled() is False  # hành vi thuộc L3.3/L3.4/L3.5
            assert button.receivers(button.clicked) == 0

    def test_table_headers_are_rendered(self):
        screen = _screen()

        headers = [
            screen.table_model.headerData(index, Qt.Orientation.Horizontal)
            for index in range(screen.table_model.columnCount())
        ]
        assert headers == list(news.COLUMN_LABELS)

    def test_date_filter_defaults_to_the_last_month(self):
        screen = _screen()

        from PyQt6.QtCore import QDate

        assert screen.date_to_input.date() == QDate.currentDate()
        assert screen.date_from_input.date() == QDate.currentDate().addMonths(-1)


# ---- 5. trạng thái tải và rỗng -------------------------------------------------


class TestLoadingAndEmptyState:
    def test_loading_indicator_is_shown_while_the_read_runs(self):
        gate = threading.Event()
        controller = FakeNewsController()
        original = controller.events_in_range

        def blocking_read(from_utc, to_utc, *args, **kwargs):
            gate.wait(timeout=5)
            return original(from_utc, to_utc, *args, **kwargs)

        controller.events_in_range = blocking_read  # type: ignore[method-assign]
        screen = _screen(controller, wait=False)

        assert _wait_until(lambda: news.LOADING_TEXT in screen.status_message.toPlainText())
        assert screen.status_message.isVisible() is True

        gate.set()
        assert _wait_until(lambda: screen.table_model.rowCount() == 3)

    def test_rows_land_after_the_background_read(self):
        controller = FakeNewsController()
        screen = _screen(controller)

        assert _wait_until(lambda: screen.table_model.rowCount() == 3)
        assert controller.item_calls and controller.item_calls[0][2] is False  # excluded=1 vẫn đọc
        assert screen.status_message.isVisible() is False

    def test_empty_filter_shows_the_registered_empty_state(self):
        screen = _screen()
        _wait_until(lambda: screen.table_model.rowCount() > 0)

        screen._apply_rows([])  # không có dòng nào trong khoảng lọc

        assert screen.table_model.rowCount() == 0
        assert news.EMPTY_TEXT in screen.status_message.toPlainText()
        assert screen.status_message.isVisible() is True
        assert screen.empty_actions.isVisible() is True
        assert set(screen.empty_state_buttons) == {"Lấy lịch kinh tế", "Nhập tin"}

    def test_reading_error_is_reported_without_crashing(self):
        screen = _screen()

        screen._on_rows_failed("CSDL không đọc được")

        assert "CSDL không đọc được" in screen.status_message.toPlainText()
        assert screen.status_message.isVisible() is True


# ---- 6. chi tiết dòng ---------------------------------------------------------


class TestRowDetailDialog:
    def test_item_detail_shows_provenance_content_and_link(self):
        screen = _screen()
        rows = build_rows([EVENT], [HEADLINE, EXCLUDED_NOTE])
        dialog = screen.row_detail_dialog(rows[1])

        texts = [label.text() for label in dialog.findChildren(QLabel)]
        joined = " ".join(texts)
        assert dialog.windowTitle() == news.DETAIL_TEXT
        assert "Powell said the committee can wait." in joined
        assert "Google News" in joined
        assert "21/09/2026 09:00" in joined  # giờ fetch
        assert "https://example.com/fed" in joined
        for label in news.PROVENANCE_LABELS:
            assert label in joined, label

    def test_event_detail_shows_raw_json(self):
        screen = _screen()
        dialog = screen.row_detail_dialog(build_rows([EVENT], [])[0])

        joined = " ".join(label.text() for label in dialog.findChildren(QLabel))
        assert "raw_json" in joined
        assert "FOMC Meeting" in joined
        assert "ForexFactory (actual)" in joined


# ---- 7. màn không vỡ layout 800px + đăng ký điều hướng ------------------------


class TestShellIntegration:
    def test_nav_item_and_route_are_registered(self):
        assert ("news", "Tin tức") in NAV_ITEMS
        assert NAV_ICONS["news"] == "message-square"
        assert nav_route("news") == "news"

    def test_shell_opens_the_news_screen_at_the_minimum_window(self):
        app = _app()
        with contextlib.ExitStack() as stack:
            _patch_external_activity(stack)
            window = MainWindow(_fake_app("dark"))
            window.resize(800, 500)
            window.show()
            app.processEvents()
            try:
                window.navigate("news")
                app.processEvents()
                screen = window.screens["news"]

                assert isinstance(screen, NewsScreen)
                assert window.minimumSize().width() == 800
                assert window.sidebar_width == 48
                assert screen.width() >= screen.minimumSizeHint().width()
                assert screen.table.isVisible()
            finally:
                window.close()
                app.processEvents()


@pytest.mark.parametrize("width", [800, 1000, 1280])
def test_screen_minimum_width_fits_the_shell_content_width(width):
    screen = _screen()
    content_width = width - 48  # rail 48px (ui/main_window.py)

    assert screen.minimumSizeHint().width() <= content_width
