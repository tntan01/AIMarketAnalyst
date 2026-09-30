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

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QTextEdit

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


def _event(time_utc: str, title: str = "Sự kiện") -> CalendarEvent:
    return CalendarEvent(
        day_key=time_utc[:10],
        event_time_utc=time_utc,
        currency="USD",
        title=title,
        impact=EventImpact.HIGH,
        status=EventStatus.SCHEDULED,
        source=EventSource.FF_HTML,
        dedupe_key=f"key-{time_utc}-{title}",
        fetched_at=time_utc,
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
        # Giải thích chỉ số (Owner yêu cầu 30/09/2026): đếm lời gọi + trả câu đã
        # dựng, hoặc raise để kiểm nhánh lỗi (fail-closed).
        self.explain_calls: list[CalendarEvent] = []
        self.explain_answer = "EUR chịu áp lực giảm khi số liệu xấu hơn dự báo."
        self.explain_error: Exception | None = None

    def events_in_range(self, from_utc, to_utc, currencies=None, include_non_impact=True):
        self.event_calls.append((from_utc, to_utc))
        return list(self.events)

    def explain_event(self, event: CalendarEvent) -> str:
        self.explain_calls.append(event)
        if self.explain_error is not None:
            raise self.explain_error
        return self.explain_answer

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


@pytest.fixture(autouse=True)
def _fixed_now(monkeypatch):
    """Chốt "hiện tại" xa (2030) để mọi fixture 2026-09 là quá khứ — mặc định
    không sinh dòng "sắp tới gần nhất" (kết quả tất định theo ngày chạy test)."""
    monkeypatch.setattr(news, "_now_utc", lambda: datetime(2030, 1, 1, tzinfo=UTC))


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
            "ff_json": "ForexFactory (lịch — dữ liệu cũ)",
            "ff_html": "Forex Factory",
            "google_news_rss": "Google News",
            "fxstreet_rss": "FXStreet",
            "investing_rss": "Investing",
            "fred": "FRED",
            "config_fallback": "Cấu hình dự phòng",
            "user": "Nhập tay",
            "import": "Nhập file (dữ liệu cũ)",
        }

    def test_column_filter_and_toolbar_labels_are_the_registered_block(self):
        assert news.COLUMN_LABELS == (
            "Thời gian",
            "Nguồn",
            "Đồng tiền",
            "Loại",
            "Nội dung",
            "Kỳ trước",
            "Dự báo",
            "Thực tế",
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
            "Dán mã nguồn trang",
            "Nhập tin",
            "AI nhận định xu hướng",
            "Tải lại",
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
        # Cột "Chi tiết" thay tiêu đề chữ bằng icon → header DisplayRole rỗng.
        expected = list(news.COLUMN_LABELS)
        detail_col = news.COLUMN_LABELS.index("Chi tiết")
        expected[detail_col] = ""
        assert headers == expected
        assert model.headerData(
            detail_col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DecorationRole
        ) is not None

    def test_event_row_shows_the_registered_labels(self):
        # Múi giờ hiển thị cố định (Asia/Ho_Chi_Minh) — không phụ thuộc settings
        # máy chạy test; hiển thị theo múi giờ người dùng (Owner 25/09/2026).
        news._configure_display_timezone("Asia/Ho_Chi_Minh")
        model = self._model()
        index = model.index(0, 0)

        def cell(column: int) -> str:
            return model.data(model.index(0, column), Qt.ItemDataRole.DisplayRole)

        assert model.data(index, Qt.ItemDataRole.DisplayRole) == "20/09/2026 21:30"
        assert cell(1) == "Forex Factory"
        assert cell(2) == "USD"
        assert cell(3) == news.EVENT_ICON
        assert cell(4) == "FOMC Meeting"
        assert cell(5) == "5.25%"
        assert cell(6) == "5.50%"
        assert cell(7) == "5.50%"
        assert cell(8) == ""  # cột "Chi tiết" thay chữ bằng icon
        assert model.data(
            model.index(0, 8), Qt.ItemDataRole.DecorationRole
        ) is not None

    def test_item_row_shows_type_icon_and_values(self):
        model = self._model()
        row = 1

        def cell(column: int) -> str:
            return model.data(model.index(row, column), Qt.ItemDataRole.DisplayRole)

        assert cell(1) == "Google News"
        assert cell(2) == "USD, EUR"
        assert cell(3) == news.ITEM_ICON
        assert cell(5) == news.NO_VALUE  # tin văn bản không có "kỳ trước"
        assert cell(6) == news.NO_VALUE  # tin văn bản không có "dự báo"
        assert cell(7) == news.NO_VALUE  # tin văn bản không có "thực tế"
        assert cell(8) == ""  # cột "Chi tiết" là icon

    def test_excluded_item_row_values(self):
        model = self._model()

        def cell(row: int, column: int) -> str:
            return model.data(model.index(row, column), Qt.ItemDataRole.DisplayRole)

        assert cell(2, 1) == "Nhập tay"
        assert cell(2, 2) == "JPY"
        assert cell(2, 3) == news.ITEM_ICON

    def test_impact_rows_carry_a_semantic_colour(self):
        model = self._model()

        # Dòng tác động cao (sự kiện) — đỏ (danger): cả chữ lẫn nền.
        high_fg = model.data(model.index(0, 1), Qt.ItemDataRole.ForegroundRole)
        high_bg = model.data(model.index(0, 1), Qt.ItemDataRole.BackgroundRole)
        assert high_fg is not None and high_fg.isValid()
        assert high_bg is not None and high_bg.isValid()

        # Dòng tác động trung bình (headline có impact_hint) — cam (warning).
        medium_fg = model.data(model.index(1, 1), Qt.ItemDataRole.ForegroundRole)
        assert medium_fg is not None and medium_fg.isValid()
        assert medium_fg != high_fg

        # Dòng không rõ mức tác động — không tô nền dòng.
        none_bg = model.data(model.index(2, 1), Qt.ItemDataRole.BackgroundRole)
        assert none_bg is None


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


class TestWeekButtons:
    """Nhóm nút tuần (Owner yêu cầu 30/09/2026) — khuôn "Lọc nhanh" của Journal."""

    def test_buttons_use_the_shared_action_button_style(self):
        screen = _screen()

        assert tuple(screen.week_buttons) == news.WEEK_BUTTON_LABELS
        for label, button in screen.week_buttons.items():
            assert button.text() == label
            # Khuôn nút hành động chung của hệ thống — cùng objectName với nút
            # "Hủy"/"Làm mới"/"Quay lại" các màn khác; KHÔNG tự đặt style riêng.
            assert button.objectName() == "SecondaryButton"
            assert button.isCheckable() is True
            # (Chiều cao 24px — cùng khuôn nút "Tìm kiếm" — do QSS quyết định và
            # chỉ đo được khi theme đã nạp; module test này chạy không QSS nên đo
            # ở đây vô nghĩa: đã kiểm bằng render thật, không ghim số ở đây.)

    def test_week_button_sets_the_week_range_and_reloads(self, monkeypatch):
        # now = 30/09/2026 (Thứ 4) 12:00 UTC → 19:00 giờ VN; tuần này = 28/09 → 04/10.
        monkeypatch.setattr(news, "_now_utc", lambda: datetime(2026, 9, 30, 12, 0, tzinfo=UTC))
        controller = FakeNewsController()
        screen = _screen(controller)
        reads_before = len(controller.event_calls)

        screen.week_buttons["Tuần trước"].click()

        assert _range(screen) == ("21/09/2026", "27/09/2026")
        # Nút tuần áp ngay (khác các ô lọc — đổi ô lọc phải bấm "Tìm kiếm").
        assert _wait_until(lambda: len(controller.event_calls) > reads_before)

        screen.week_buttons["Tuần sau"].click()

        assert _range(screen) == ("05/10/2026", "11/10/2026")

    def test_checked_state_follows_the_applied_range(self, monkeypatch):
        monkeypatch.setattr(news, "_now_utc", lambda: datetime(2026, 9, 30, 12, 0, tzinfo=UTC))
        screen = _screen()

        # Mặc định "hôm nay → hôm nay" không trùng tuần nào → cả ba bỏ chọn.
        assert _checked(screen) == [False, False, False]

        screen.week_buttons["Tuần này"].click()

        assert _range(screen) == ("28/09/2026", "04/10/2026")
        assert _checked(screen) == [False, True, False]

        screen.week_buttons["Tuần sau"].click()

        assert _checked(screen) == [False, False, True]

        # Sửa một ô ngày nhưng CHƯA bấm "Tìm kiếm": nút vẫn phản ánh khoảng ĐANG ÁP.
        screen.date_from_input.setDate(QDate(2026, 1, 1))

        assert _checked(screen) == [False, False, True]


def _range(screen: NewsScreen) -> tuple[str, str]:
    return (
        screen.date_from_input.date().toString("dd/MM/yyyy"),
        screen.date_to_input.date().toString("dd/MM/yyyy"),
    )


def _checked(screen: NewsScreen) -> list[bool]:
    return [button.isChecked() for button in screen.week_buttons.values()]


class TestScreenLayout:
    def test_screen_shows_header_filters_and_toolbar_labels(self):
        screen = _screen()
        texts = _texts(screen)

        assert "Tin tức" in texts
        assert news.SEARCH_BUTTON_TEXT in texts  # nút tìm của card lọc (26/09/2026)
        for label in news.FILTER_LABELS:
            assert label in texts, label
        for label in news.TOOLBAR_LABELS:
            assert label in texts, label

    def test_filter_combos_offer_registered_labels_and_enum_values(self):
        screen = _screen()

        kind = _combo_texts(screen, screen.kind_combo)
        # Mục đầu rút gọn "Tất cả" cho mọi combo (Owner quyết 26/09/2026) —
        # nhãn cạnh ô đã nói ô đó lọc gì.
        assert kind == ["Tất cả", news.EVENT_TEXT, "Headline", "Phát biểu", "Nhập tay"]
        assert [screen.kind_combo.itemData(i) for i in range(1, screen.kind_combo.count())] == [
            "event",
            "headline",
            "statement",
            "user_note",
        ]

        status = _combo_texts(screen, screen.status_combo)
        assert status == [
            "Tất cả",
            "Chưa tới giờ",
            "Đã có số liệu",
            "Thiếu số liệu",
            "Đã loại trừ",
        ]
        impact = _combo_texts(screen, screen.impact_combo)
        assert impact == ["Tất cả", "Cao", "Trung bình", "Thấp", "Không đáng kể"]

    def test_currency_options_come_from_the_loaded_rows(self):
        screen = _screen()
        _wait_until(lambda: screen.table_model.rowCount() > 0)

        assert _combo_texts(screen, screen.currency_combo) == ["Tất cả", "EUR", "JPY", "USD"]

    def test_toolbar_buttons_are_wired_per_lot(self):
        screen = _screen()
        # F4: toolbar đúng 3 nút [ Dán mã nguồn trang | Nhập tin | AI nhận định
        # xu hướng ] — cả ba đã nối hành vi.
        assert set(screen.toolbar_buttons) == set(news.TOOLBAR_LABELS)
        for label, button in screen.toolbar_buttons.items():
            assert button.isEnabled() is True
            assert button.receivers(button.clicked) >= 1

    def test_reload_button_reads_the_window_again(self):
        # Owner yêu cầu 30/09/2026: nút "Tải lại" cập nhật trạng thái mới nhất của
        # trang — đọc lại database theo đúng cửa sổ/bộ lọc đang áp (cùng đường với
        # nút "Tìm kiếm", không đổi khoảng ngày).
        controller = FakeNewsController()
        screen = _screen(controller)
        reads_before = len(controller.event_calls)
        from PyQt6.QtCore import QDate

        assert (screen.date_from_input.date(), screen.date_to_input.date()) == (
            QDate.currentDate(),
            QDate.currentDate(),
        )

        screen.toolbar_buttons["Tải lại"].click()

        assert _wait_until(lambda: len(controller.event_calls) > reads_before)
        # Không đổi cửa sổ ngày — chỉ đọc lại.
        assert (screen.date_from_input.date(), screen.date_to_input.date()) == (
            QDate.currentDate(),
            QDate.currentDate(),
        )

    def test_toolbar_buttons_use_the_system_action_style_with_icons(self):
        screen = _screen()

        assert set(news.TOOLBAR_ICONS) == set(news.TOOLBAR_LABELS)
        for label, button in screen.toolbar_buttons.items():
            # Khuôn nút hành động hệ thống: primary + glyph (không phải nút chữ trơn).
            assert button.objectName() == "PrimaryButton", label
            assert button.icon().isNull() is False, label
            # Bề ngang tự nhiên (vừa đủ chứa tiêu đề + icon), không giãn theo cột.
            assert button.width() <= button.sizeHint().width() + 2, label

    def test_table_headers_are_rendered(self):
        screen = _screen()

        headers = [
            screen.table_model.headerData(index, Qt.Orientation.Horizontal)
            for index in range(screen.table_model.columnCount())
        ]
        expected = list(news.COLUMN_LABELS)
        expected[news.COLUMN_LABELS.index("Chi tiết")] = ""
        assert headers == expected

    def test_date_filter_defaults_to_today(self):
        screen = _screen()

        from PyQt6.QtCore import QDate

        # Mặc định mở màn: khoảng ngày = hôm nay (cả hai đầu).
        assert screen.date_from_input.date() == QDate.currentDate()
        assert screen.date_to_input.date() == QDate.currentDate()


# ---- 4b. tin sắp tới gần nhất (mặc định) -------------------------------------


class TestNearestUpcoming:
    def test_nearest_is_bold_green_with_a_separator(self, monkeypatch):
        # now = 21/09 00:00 UTC → EVENT (20/09) quá khứ; HEADLINE (21/09 08:00)
        # là tin sắp tới gần nhất; EXCLUDED_NOTE (22/09) sau đó.
        monkeypatch.setattr(news, "_now_utc", lambda: datetime(2026, 9, 21, 0, 0, tzinfo=UTC))
        screen = _screen()
        rows = screen.table_model.rows

        # Khuôn vùng của Dashboard cho phần sắp tới: dòng ngăn cách "SẮP TỚI GẦN
        # NHẤT" ngay trên tin sắp tới gần nhất, rồi "SẮP TỚI" trên các tin sắp
        # tới còn lại (vùng rỗng thì không chèn).
        assert [row.section_text for row in rows] == [
            None,
            news.NEAREST_SECTION_TEXT,
            None,
            news.FUTURE_SECTION_TEXT,
            None,
        ]
        assert rows[1].row_type == news.SECTION_ROW
        assert rows[1].section_role == news.SECTION_ROLE
        assert rows[3].section_role == news.FUTURE_ROLE

        nearest = rows[2]
        assert nearest is screen.table_model.nearest
        assert nearest.title == HEADLINE.title

        title_col = next(i for i, (k, _l) in enumerate(screen.table_model.COLUMNS) if k == "title")
        fg = screen.table_model.data(screen.table_model.index(2, title_col), Qt.ItemDataRole.ForegroundRole)
        font = screen.table_model.data(screen.table_model.index(2, title_col), Qt.ItemDataRole.FontRole)
        assert fg is not None and fg.isValid()
        assert font is not None and font.bold()

        # Hai dòng ngăn cách mang màu theo vùng của chúng (dashboard: "sắp tới gần
        # nhất" xanh, "sắp tới" cam) — không dùng chung một màu.
        section_fg = [
            screen.table_model.data(
                screen.table_model.index(index, 0), Qt.ItemDataRole.ForegroundRole
            )
            for index in (1, 3)
        ]
        assert all(color is not None and color.isValid() for color in section_fg)
        assert section_fg[0] != section_fg[1]

        # Dòng ngăn cách trải toàn bề ngang bảng (khuôn span dashboard).
        assert screen.table.columnSpan(1, 0) == screen.table_model.columnCount()
        assert screen.table.columnSpan(3, 0) == screen.table_model.columnCount()

    def test_nearest_without_later_rows_gets_no_future_separator(self, monkeypatch):
        # Chỉ còn đúng MỘT tin sắp tới → không có vùng "SẮP TỚI" (khuôn dashboard:
        # vùng rỗng thì không vẽ dòng ngăn cách).
        monkeypatch.setattr(news, "_now_utc", lambda: datetime(2026, 9, 21, 0, 0, tzinfo=UTC))
        screen = _screen(FakeNewsController(events=[EVENT], items=[HEADLINE]))

        assert [row.section_text for row in screen.table_model.rows] == [
            None,
            news.NEAREST_SECTION_TEXT,
            None,
        ]

    def test_open_scrolls_nearest_to_the_top(self, monkeypatch):
        monkeypatch.setattr(news, "_now_utc", lambda: datetime(2026, 9, 30, 12, 0, tzinfo=UTC))
        past = [_event(f"2026-09-30T{h:02d}:00:00Z", f"P{h}") for h in range(1, 8)]
        upcoming = [_event(f"2026-09-30T{h:02d}:00:00Z", f"U{h}") for h in range(13, 20)]
        controller = FakeNewsController(events=past + upcoming, items=[])
        screen = _screen(controller)

        nearest = screen.table_model.nearest
        assert nearest is not None and nearest.title == "U13"
        assert screen._scroll_pending is False  # yêu cầu cuộn đã được tiêu
        assert _wait_until(lambda: screen.table.verticalScrollBar().value() > 0)

    def test_showing_the_screen_scrolls_the_nearest_zone_to_the_top(self, monkeypatch):
        # Khuôn app thật (main_window._build_screens): màn dựng MỘT LẦN lúc khởi
        # động và nằm trong QStackedWidget — lượt nạp đầu xong khi màn còn ẩn, nên
        # yêu cầu cuộn phải treo lại tới khi màn được hiện, lúc đó thanh cuộn mới
        # thật sự kéo dòng ngăn cách "SẮP TỚI GẦN NHẤT" lên đầu khung nhìn (dòng
        # tin sắp tới gần nhất nằm ngay dưới nó).
        monkeypatch.setattr(news, "_now_utc", lambda: datetime(2026, 9, 30, 12, 0, tzinfo=UTC))
        events = [
            _event(f"2026-09-30T{hour:02d}:{minute:02d}:00Z", f"E{hour:02d}{minute:02d}")
            for hour in range(24)
            for minute in (0, 15, 30, 45)
        ]
        controller = FakeNewsController(events=events, items=[])
        screen = NewsScreen(None, app=SimpleNamespace(news_controller=controller))
        _SCREENS.append(screen)
        assert _wait_until(lambda: bool(controller.event_calls))
        _app().processEvents()

        # Màn còn ẩn: chưa cuộn được (view chưa bày) — yêu cầu vẫn treo.
        assert screen.table.verticalScrollBar().value() == 0
        assert screen._scroll_pending is True

        screen.resize(752, 500)
        screen.show()
        assert _wait_until(lambda: screen.table.verticalScrollBar().value() > 0)

        rows = screen.table_model.rows
        nearest = screen.table_model.nearest
        assert nearest is not None and nearest.title == "E1200"
        at = next(i for i, row in enumerate(rows) if row is nearest)
        assert rows[at - 1].section_text == news.NEAREST_SECTION_TEXT
        # Dòng đầu khung nhìn là dòng ngăn cách, dòng tin nằm ngay dưới.
        assert screen.table.rowAt(0) == at - 1
        assert screen.table.rowViewportPosition(at) == screen.table.rowHeight(at - 1)

    def test_no_upcoming_row_keeps_the_time_order_without_scrolling(self, monkeypatch):
        # Mọi dòng đều đã qua (now = 30/09 23:00 UTC) → không có "tin sắp tới gần
        # nhất": bảng giữ nguyên thứ tự thời gian, không tô đậm, không chèn dòng
        # ngăn cách và không cuộn (screen_design mục "Tin sắp tới gần nhất lên
        # trên cùng").
        monkeypatch.setattr(news, "_now_utc", lambda: datetime(2026, 9, 30, 23, 0, tzinfo=UTC))
        past = [_event(f"2026-09-30T{h:02d}:00:00Z", f"P{h}") for h in range(1, 20)]
        screen = _screen(FakeNewsController(events=past, items=[]))

        assert screen.table_model.nearest is None
        assert [row.title for row in screen.table_model.rows] == [
            f"P{h}" for h in range(1, 20)
        ]
        assert screen.table.verticalScrollBar().value() == 0


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

    def test_empty_filter_leaves_the_table_empty_without_message(self):
        screen = _screen()
        _wait_until(lambda: screen.table_model.rowCount() > 0)

        screen._apply_rows([])  # không có dòng nào trong khoảng lọc

        assert screen.table_model.rowCount() == 0
        # Không có tin → chỉ để bảng rỗng, không thông báo/không nút gợi ý
        # (các nút hành vi đã có sẵn ở thanh công cụ — Owner quyết 27/09/2026).
        assert screen.status_message.isVisible() is False

    def test_reading_error_is_reported_without_crashing(self):
        screen = _screen()

        screen._on_rows_failed("CSDL không đọc được")

        assert "CSDL không đọc được" in screen.status_message.toPlainText()
        assert screen.status_message.isVisible() is True


# ---- 6. chi tiết dòng ---------------------------------------------------------


class TestRowDetailDialog:
    def test_item_detail_shows_provenance_content_and_link(self):
        # Múi giờ hiển thị cố định (Asia/Ho_Chi_Minh) — hiển thị theo múi giờ
        # người dùng (Owner 25/09/2026), không phụ thuộc settings máy chạy test.
        news._configure_display_timezone("Asia/Ho_Chi_Minh")
        screen = _screen()
        rows = build_rows([EVENT], [HEADLINE, EXCLUDED_NOTE])
        dialog = screen.row_detail_dialog(rows[1])

        texts = [label.text() for label in dialog.findChildren(QLabel)]
        joined = " ".join(texts)
        assert dialog.windowTitle() == news.DETAIL_TEXT
        assert "Powell said the committee can wait." in joined
        assert "Google News" in joined
        assert "21/09/2026 16:00" in joined  # giờ fetch (Asia/Ho_Chi_Minh)
        assert "https://example.com/fed" in joined
        for label in news.PROVENANCE_LABELS:
            assert label in joined, label

    def test_event_detail_shows_the_event_figures_instead_of_raw_json(self):
        # Owner yêu cầu 30/09/2026: với tin FF, dialog hiển thị chính số liệu của
        # sự kiện (kỳ trước/dự báo/thực tế); "giờ fetch"/"raw_json" bị bỏ vì vô
        # nghĩa với người dùng.
        screen = _screen()
        dialog = screen.row_detail_dialog(build_rows([EVENT], [])[0])

        joined = " ".join(label.text() for label in dialog.findChildren(QLabel))
        assert "FOMC Meeting" in joined
        assert "Forex Factory" in joined
        for label in news.EVENT_DATA_LABELS:
            assert label in joined, label
        assert "5.25%" in joined  # kỳ trước
        assert "5.50%" in joined  # dự báo + thực tế
        assert "raw_json" not in joined
        assert "Giờ fetch" not in joined

    def test_item_detail_keeps_the_provenance_grid(self):
        # Hàng tin văn bản KHÔNG đụng tới (ngoài phạm vi yêu cầu).
        screen = _screen()
        dialog = screen.row_detail_dialog(build_rows([], [HEADLINE])[0])

        joined = " ".join(label.text() for label in dialog.findChildren(QLabel))
        for label in news.PROVENANCE_LABELS:
            assert label in joined, label
        assert not any(label in joined for label in news.EVENT_DATA_LABELS[2:])

    def test_detail_dialog_has_the_system_close_button(self):
        screen = _screen()
        dialog = screen.row_detail_dialog(build_rows([EVENT], [])[0])

        close = next(
            button
            for button in dialog.findChildren(QPushButton)
            if button.text() == news.CLOSE_TEXT
        )
        assert close.objectName() == "SecondaryButton"  # khuôn nút chung

        close.click()

        assert dialog.result() == int(QDialog.DialogCode.Accepted)

    def test_event_detail_has_the_explanation_frame_and_button(self):
        screen = _screen()
        dialog = screen.row_detail_dialog(build_rows([EVENT], [])[0])

        frame = dialog.findChild(QTextEdit, "ReadonlyText")
        assert frame is not None and frame.isReadOnly()
        assert frame.toPlainText() == news.EXPLAIN_HINT_TEXT
        assert news.EXPLAIN_HEADER_TEXT in [
            label.text() for label in dialog.findChildren(QLabel)
        ]
        button = next(
            button
            for button in dialog.findChildren(QPushButton)
            if button.text() == news.EXPLAIN_TEXT
        )
        assert button.objectName() == "PrimaryButton"  # khuôn nút AI của màn

    def test_explanation_button_calls_the_ai_and_fills_the_frame(self):
        controller = FakeNewsController()
        screen = _screen(controller)
        dialog = screen.row_detail_dialog(build_rows([EVENT], [])[0])
        frame = dialog.findChild(QTextEdit, "ReadonlyText")
        button = next(
            button
            for button in dialog.findChildren(QPushButton)
            if button.text() == news.EXPLAIN_TEXT
        )

        button.click()

        assert _wait_until(lambda: controller.explain_calls == [EVENT])
        assert _wait_until(lambda: frame.toPlainText() == controller.explain_answer)
        # Nút trở lại trạng thái bấm được với nhãn gốc.
        assert _wait_until(lambda: button.text() == news.EXPLAIN_TEXT)
        assert button.isEnabled() is True

    def test_explanation_button_shows_the_running_state(self):
        # Yêu cầu Owner: khi bấm, nút đổi trạng thái thành "AI đang giải thích"
        # trong lúc chờ kết quả (lời gọi chạy worker nền, GUI không chặn).
        import threading

        gate = threading.Event()
        controller = FakeNewsController()

        def blocking_explain(event):
            gate.wait(timeout=5)
            return controller.explain_answer

        controller.explain_event = blocking_explain  # type: ignore[method-assign]
        screen = _screen(controller)
        dialog = screen.row_detail_dialog(build_rows([EVENT], [])[0])
        button = next(
            button
            for button in dialog.findChildren(QPushButton)
            if button.text() == news.EXPLAIN_TEXT
        )

        button.click()

        assert _wait_until(lambda: button.text() == news.AI_EXPLAINING_TEXT)
        assert button.isEnabled() is False

        gate.set()

        assert _wait_until(lambda: button.text() == news.EXPLAIN_TEXT)
        assert button.isEnabled() is True

    def test_explanation_failure_shows_the_friendly_message(self):
        controller = FakeNewsController()
        controller.explain_error = RuntimeError("Chưa cấu hình AI Provider hoặc API key trong Settings.")
        screen = _screen(controller)
        dialog = screen.row_detail_dialog(build_rows([EVENT], [])[0])
        frame = dialog.findChild(QTextEdit, "ReadonlyText")
        button = next(
            button
            for button in dialog.findChildren(QPushButton)
            if button.text() == news.EXPLAIN_TEXT
        )

        button.click()

        assert _wait_until(lambda: "Chưa cấu hình AI" in frame.toPlainText())
        assert _wait_until(lambda: button.isEnabled() is True)

    def test_item_detail_has_no_explanation_block(self):
        # Khung giải thích chỉ dành cho tin SỰ KIỆN FF (Owner yêu cầu 30/09/2026).
        screen = _screen()
        dialog = screen.row_detail_dialog(build_rows([], [HEADLINE])[0])

        assert dialog.findChild(QTextEdit, "ReadonlyText") is None
        assert news.EXPLAIN_TEXT not in [
            button.text() for button in dialog.findChildren(QPushButton)
        ]


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


# ---- 8. cửa sổ AI nhận định 3 tab (đợt 5 — B4) ---------------------------------


class _FakeAiController:
    """Controller tối thiểu cho dialog 3 tab — không gọi AI khi mở."""

    AI_ASSET_SCOPES = ("EUR", "USD", "XAU")

    def ai_scope_preview(self, scope_type, scope_value):
        return SimpleNamespace(
            window_days=7,
            event_count=0,
            item_count=0,
            insufficient=True,
            context=None,
            short_days=7,
            mid_days=42,
            long_days=180,
            long_max_rows=50,
            short_rows=0,
            mid_rows=0,
            long_rows=0,
        )

    def verdicts_for(self, scope_type, scope_value, limit):
        return []

    def analyze_trend(self, scope_type, scope_value):
        raise AssertionError("AI không được gọi khi mở dialog")

    def analyze_all_trends(self, now=None, on_scope_done=None):
        raise AssertionError("batch không được chạy khi mở dialog")


class TestAiDialogThreeTabs:
    def test_open_dialog_has_three_tabs_defaulting_to_overview(self):
        app = _app()
        dialog = news.AiTrendDialog(_FakeAiController(), None)
        try:
            dialog.show()
            app.processEvents()

            assert dialog._tabs.count() == 3
            assert dialog._tabs.tabText(0) == news.AI_TAB_OVERVIEW_TEXT
            assert dialog._tabs.tabText(1) == news.AI_TAB_DETAIL_TEXT
            assert dialog._tabs.tabText(2) == news.AI_TAB_PAIR_TEXT
            assert dialog._tabs.currentIndex() == 0  # mặc định "Tổng quan"
            assert dialog._overview_model.rowCount() == 3  # theo AI_ASSET_SCOPES giả
        finally:
            dialog._shutdown_ai()
            dialog.close()
            app.processEvents()
