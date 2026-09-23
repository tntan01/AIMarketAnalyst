"""Hành vi tương tác màn Quản lý tin (plan lô L3.3).

Kiểm các nhánh hành vi của lô (screen_design "Hành vi lấy dữ liệu ForexFactory
(2 nút)" + "Hành vi nhập/sửa tin"; contract §6.1/§6.4):

* 2 nút FF chạy trong worker nền: disable + tiến trình khi chạy, thông báo tóm
  tắt/lỗi có kiểu khi xong, không retry, đọc lại bảng;
* form nhập/sửa ``user_note``: thiếu trường bắt buộc → lỗi trên form, KHÔNG ghi;
  lỗi validate controller hiện từng trường, không đóng;
* sửa/xóa chỉ ``source=user``; toggle Loại trừ mọi dòng tin văn bản; dòng sự
  kiện không có;
* empty state: 2 nút gợi ý enabled và đi đúng 2 đường hành vi;
* ranh giới lô: 1 nút còn lại (AI nhận định) vẫn disabled.
* 2 nút "Xuất file"/"Nhập file" (L3.4): chạy nền + disable khi chạy; xuất báo
  đường dẫn file, nhập báo tóm tắt mới/cập nhật/bỏ qua trùng, đọc lại bảng;
  chọn format/file hủy → không gọi controller.

Controller là **fake có kiểu** (trả mô hình miền thật ``core/news_models`` +
kết quả thật của ``controllers/news_controller`` / ``ff_calendar_producer``),
không mock sâu, không DB, không mạng.  Riêng đường D1 (sửa tin) được kiểm thêm
với ``NewsController`` THẬT + repository giả ghi lời gọi (không DB) để ghim thứ
tự "validate trước, xóa sau".  Test chạy offscreen; không ghi gì vào repo.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox, QPushButton

from controllers.news_controller import (
    NewsController,
    UserNoteFieldError,
    UserNoteResult,
)
from core.news_models import (
    CalendarEvent,
    EventImpact,
    EventSource,
    EventStatus,
    ImpactHint,
    IngestProducer,
    IngestRunStatus,
    NewsItem,
    NewsItemKind,
    NewsItemSource,
)
from core.news_policy import load_news_policy
from services.news_file_transfer import FileExportResult, FileImportResult
from services.news_producers.ff_calendar_producer import (
    HtmlCalendarFetchError,
    HtmlCalendarResult,
    JsonCalendarFetchError,
    JsonCalendarResult,
)
from services.news_repository import UpsertItemsResult
from ui.screens import news_screen as news
from ui.screens.news_screen import NewsScreen, build_rows, suggest_manual_actual_event

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
    actual="5.50%",
    id=11,
)
AUTO_ITEM = NewsItem(
    kind=NewsItemKind.HEADLINE,
    source=NewsItemSource.GOOGLE_NEWS_RSS,
    title="Fed signals patience",
    content="Powell said the committee can wait.",
    url="https://example.com/fed",
    published_utc="2026-09-21T08:00:00Z",
    currencies=["USD"],
    impact_hint=ImpactHint.MEDIUM,
    dedupe_key="item-1",
    fetched_at="2026-09-21T09:00:00Z",
    id=22,
)
USER_ITEM = NewsItem(
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


def _weekday_of_this_week(week: str) -> str:
    today = datetime.now(UTC).date()
    monday = today - timedelta(days=today.weekday())
    offset = 1 if week == "this" else 8
    return (monday + timedelta(days=offset)).isoformat()


# ---------------------------------------------------------------------------
# Fake controller có kiểu
# ---------------------------------------------------------------------------


class FakeNewsController:
    """Controller giả: ghi lời gọi, trả mô hình/kết quả thật của miền."""

    def __init__(
        self,
        events: list[CalendarEvent] | None = None,
        items: list[NewsItem] | None = None,
        pending: list[CalendarEvent] | None = None,
    ) -> None:
        self.events = list(events) if events is not None else [EVENT]
        self.items = list(items) if items is not None else [AUTO_ITEM, USER_ITEM]
        self.pending = list(pending) if pending is not None else []
        self.event_calls: list[tuple[str, str]] = []
        self.item_calls: list[tuple] = []
        self.pending_calls: list[datetime] = []
        self.json_calls = 0
        self.html_calls = 0
        self.add_calls: list[dict] = []
        self.update_calls: list[tuple] = []
        self.exclude_calls: list[tuple] = []
        self.delete_calls: list[int] = []
        self.json_gate: threading.Event | None = None
        self.note_result = UserNoteResult(errors=())
        self.export_calls: list[tuple[str, str, str]] = []
        self.import_calls: list[str] = []
        self.export_gate: threading.Event | None = None
        self.import_gate: threading.Event | None = None
        self.export_error: Exception | None = None
        self.import_error: Exception | None = None
        self.export_result = FileExportResult(
            path="C:/tmp/exports/news_export_test.csv",
            events_written=2,
            items_written=1,
        )
        self.import_result = FileImportResult(inserted=3, updated=2, skipped_duplicates=1)
        self.json_result = JsonCalendarResult(
            inserted=3,
            updated=2,
            conflicts=(),
            run_status=IngestRunStatus.OK,
            run_id=1,
            feed_errors=(),
        )
        self.html_result = HtmlCalendarResult(
            pending_count=0,
            weeks_fetched=(),
            written=4,
            conflicts=(),
            run_status=IngestRunStatus.OK,
            run_id=2,
            fetch_errors=(),
        )

    def events_in_range(self, from_utc, to_utc, currencies=None, include_non_impact=True):
        self.event_calls.append((from_utc, to_utc))
        return list(self.events)

    def items_in_range(self, from_utc, to_utc=None, kinds=None, currencies=None, exclude_flagged=True):
        self.item_calls.append((from_utc, to_utc, exclude_flagged))
        return list(self.items)

    def fetch_calendar_json(self):
        self.json_calls += 1
        if self.json_gate is not None:
            self.json_gate.wait(timeout=5)
        return self.json_result

    def fetch_actual_html(self, now=None):
        self.html_calls += 1
        return self.html_result

    def events_pending_actual(self, now):
        self.pending_calls.append(now)
        return list(self.pending)

    def set_excluded(self, item_id, excluded):
        self.exclude_calls.append((item_id, bool(excluded)))
        return 1

    def delete_user_note(self, item_id):
        self.delete_calls.append(item_id)
        return 1

    def add_user_note(self, **kwargs):
        self.add_calls.append(kwargs)
        return self.note_result

    def update_user_note(self, item_id, **kwargs):
        self.update_calls.append((item_id, kwargs))
        return self.note_result

    def export_news_range(self, from_utc, to_utc, fmt):
        self.export_calls.append((from_utc, to_utc, fmt))
        if self.export_gate is not None:
            self.export_gate.wait(timeout=5)
        if self.export_error is not None:
            raise self.export_error
        return self.export_result

    def import_news_file(self, path):
        self.import_calls.append(path)
        if self.import_gate is not None:
            self.import_gate.wait(timeout=5)
        if self.import_error is not None:
            raise self.import_error
        return self.import_result


_SCREENS: list[NewsScreen] = []


@pytest.fixture(scope="module", autouse=True)
def _close_screens():
    yield
    for screen in _SCREENS:
        screen.shutdown()
        screen._shutdown_fetch()
    _app().processEvents()


def _screen(controller: FakeNewsController | None = None, *, wait: bool = True) -> NewsScreen:
    app = _app()
    controller = controller or FakeNewsController()
    screen = NewsScreen(None, app=SimpleNamespace(news_controller=controller))
    screen.resize(752, 500)
    screen.show()
    app.processEvents()
    _SCREENS.append(screen)
    if wait:
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


def _dismiss_box(captured: list[str], button_label: str, attempts: int = 250):
    """Khi QMessageBox hiện: ghi text rồi bấm ``button_label`` (chạy trong event loop)."""

    def attempt(remaining: int):
        for widget in _app().topLevelWidgets():
            if isinstance(widget, QMessageBox) and widget.isVisible():
                captured.append(widget.text())
                for button in widget.findChildren(QPushButton):
                    if button.text() == button_label:
                        button.click()
                        return
                widget.reject()
                return
        if remaining > 0:
            QTimer.singleShot(20, lambda: attempt(remaining - 1))

    QTimer.singleShot(20, lambda: attempt(attempts))


def _row_for(screen: NewsScreen, row_type: str, title: str) -> news.NewsRow:
    for row in screen.table_model.rows:
        if row.row_type == row_type and row.title == title:
            return row
    raise AssertionError(f"không thấy dòng {row_type}:{title}")


# ---- 1. nút "Lấy lịch kinh tế" -------------------------------------------------


class TestCalendarJsonButton:
    def test_runs_in_background_disables_button_and_reports_summary(self):
        gate = threading.Event()
        controller = FakeNewsController()
        controller.json_gate = gate
        screen = _screen(controller)
        reads_before = len(controller.event_calls)

        captured: list[str] = []
        _dismiss_box(captured, news.CLOSE_TEXT)
        screen.toolbar_buttons[news.TOOLBAR_LABELS[0]].click()

        assert _wait_until(lambda: not screen.toolbar_buttons[news.TOOLBAR_LABELS[0]].isEnabled())
        assert news.LOADING_TEXT in screen.status_message.toPlainText()

        gate.set()
        assert _wait_until(lambda: captured), "không thấy thông báo kết quả"
        assert "3" in captured[0] and "2" in captured[0]
        assert controller.json_calls == 1
        assert _wait_until(lambda: screen.toolbar_buttons[news.TOOLBAR_LABELS[0]].isEnabled())
        assert _wait_until(lambda: len(controller.event_calls) > reads_before)

    def test_error_reports_cause_and_never_retries(self):
        controller = FakeNewsController()
        controller.json_result = JsonCalendarResult(
            inserted=0,
            updated=0,
            conflicts=(),
            run_status=IngestRunStatus.FAILED,
            run_id=9,
            feed_errors=(JsonCalendarFetchError(feed="thisweek", error_type="Http429", detail="HTTP 429"),),
        )
        screen = _screen(controller)

        captured: list[str] = []
        _dismiss_box(captured, news.CLOSE_TEXT)
        screen.toolbar_buttons[news.TOOLBAR_LABELS[0]].click()

        assert _wait_until(lambda: captured)
        assert "Http429" in captured[0]
        assert "HTTP 429" in captured[0]
        assert controller.json_calls == 1  # không retry


# ---- 2. nút "Cập nhật actual" --------------------------------------------------


class TestCalendarActualButton:
    def test_reports_written_actual(self):
        controller = FakeNewsController()
        screen = _screen(controller)

        captured: list[str] = []
        _dismiss_box(captured, news.CLOSE_TEXT)
        screen.toolbar_buttons[news.TOOLBAR_LABELS[1]].click()

        assert _wait_until(lambda: captured)
        assert "4" in captured[0]
        assert controller.html_calls == 1

    def test_html_error_offers_manual_entry_with_the_related_event(self):
        monday_event = CalendarEvent(
            day_key=_weekday_of_this_week("this"),
            event_time_utc=f"{_weekday_of_this_week('this')}T12:00:00Z",
            currency="USD",
            title="Non-Farm Payrolls",
            impact=EventImpact.HIGH,
            status=EventStatus.STALE,
            source=EventSource.FF_JSON,
            dedupe_key="pending-1",
            fetched_at="2026-09-22T00:00:00Z",
            id=77,
        )
        controller = FakeNewsController(pending=[monday_event])
        controller.html_result = HtmlCalendarResult(
            pending_count=1,
            weeks_fetched=("this",),
            written=0,
            conflicts=(),
            run_status=IngestRunStatus.FAILED,
            run_id=6,
            fetch_errors=(HtmlCalendarFetchError(week="this", error_type="UrlError", detail="boom"),),
        )
        screen = _screen(controller)

        opened: list[dict] = []
        screen.open_note_dialog = lambda **kwargs: opened.append(kwargs)  # type: ignore[method-assign]

        captured: list[str] = []
        _dismiss_box(captured, news.MANUAL_ACTUAL_TEXT)
        screen.toolbar_buttons[news.TOOLBAR_LABELS[1]].click()

        assert _wait_until(lambda: opened), "không thấy form nhập actual tay"
        assert "UrlError" in captured[0] and "boom" in captured[0]
        assert opened[0]["prefill_event"] is monday_event

    def test_manual_actual_prefill_carries_event_fields(self):
        event = CalendarEvent(
            day_key="2026-09-20",
            event_time_utc="2026-09-20T14:30:00Z",
            currency="EUR",
            title="ECB Speech",
            impact=EventImpact.MEDIUM,
            status=EventStatus.STALE,
            source=EventSource.FF_JSON,
            dedupe_key="pending-2",
            fetched_at="2026-09-20T00:00:00Z",
            id=88,
        )
        controller = FakeNewsController()
        screen = _screen(controller)
        dialog = screen.create_note_dialog(prefill_event=event)

        assert dialog.time_value() is not None
        assert dialog.time_value().isoformat() == "2026-09-20T14:30:00+00:00"
        assert dialog.content_edit.toPlainText() == "ECB Speech"
        assert dialog.currency_values() == ["EUR"]
        assert dialog.impact_combo.currentData() is None
        assert dialog.url_edit.text() == ""

    def test_suggest_manual_actual_event_prefers_the_errored_week(self):
        now = datetime(2026, 9, 23, 10, 0, tzinfo=UTC)  # Wednesday
        this_week = CalendarEvent(
            day_key="2026-09-21", event_time_utc="2026-09-21T10:00:00Z", currency="USD",
            title="this", impact=EventImpact.HIGH, status=EventStatus.STALE,
            source=EventSource.FF_JSON, dedupe_key="a", fetched_at="2026-09-21T00:00:00Z",
        )
        next_week = CalendarEvent(
            day_key="2026-09-28", event_time_utc="2026-09-28T10:00:00Z", currency="EUR",
            title="next", impact=EventImpact.HIGH, status=EventStatus.STALE,
            source=EventSource.FF_JSON, dedupe_key="b", fetched_at="2026-09-28T00:00:00Z",
        )
        assert suggest_manual_actual_event([this_week, next_week], "next", now) is next_week
        assert suggest_manual_actual_event([this_week, next_week], "", now) is this_week
        assert suggest_manual_actual_event([], "this", now) is None


# ---- 3. form nhập/sửa tin ------------------------------------------------------


class TestUserNoteForm:
    def test_missing_required_fields_show_errors_and_write_nothing(self):
        controller = FakeNewsController()
        screen = _screen(controller)
        dialog = screen.create_note_dialog()

        dialog.save_button.click()
        _app().processEvents()

        assert dialog.result() == 0
        assert dialog.field_error_text("published_utc") != ""
        assert dialog.field_error_text("content") != ""
        assert dialog.field_error_text("currencies") != ""
        assert controller.add_calls == []

    def test_missing_content_alone_blocks_the_write(self):
        controller = FakeNewsController()
        screen = _screen(controller)
        dialog = screen.create_note_dialog()
        dialog.time_edit.setDateTime(news._iso_to_qdatetime("2026-09-23T10:30:00Z"))
        dialog.currency_edit.setCurrentText("USD")

        dialog.save_button.click()
        _app().processEvents()

        assert dialog.field_error_text("content") != ""
        assert dialog.field_error_text("currencies") == ""
        assert controller.add_calls == []

    def test_controller_errors_are_shown_per_field_and_dialog_stays_open(self):
        controller = FakeNewsController()
        controller.note_result = UserNoteResult(
            errors=(UserNoteFieldError("content", "missing"),)
        )
        screen = _screen(controller)
        dialog = screen.create_note_dialog()
        dialog.time_edit.setDateTime(news._iso_to_qdatetime("2026-09-23T10:30:00Z"))
        dialog.content_edit.setPlainText("Nội dung")
        dialog.currency_edit.setCurrentText("USD")

        dialog.save_button.click()
        _app().processEvents()

        assert dialog.result() == 0  # không đóng
        assert dialog.field_error_text("content") != ""
        assert len(controller.add_calls) == 1  # đã gọi controller, controller không ghi

    def test_valid_draft_is_written_through_the_controller(self):
        controller = FakeNewsController()
        screen = _screen(controller)
        dialog = screen.create_note_dialog()
        dialog.time_edit.setDateTime(news._iso_to_qdatetime("2026-09-23T10:30:00Z"))
        dialog.content_edit.setPlainText("Tin mới")
        dialog.currency_edit.setCurrentText("USD, EUR")
        dialog.impact_combo.setCurrentIndex(dialog.impact_combo.findData("high"))
        dialog.url_edit.setText("https://example.com/x")

        dialog.save_button.click()
        _app().processEvents()

        assert dialog.result() == 1  # đóng = đã ghi
        assert len(controller.add_calls) == 1
        call = controller.add_calls[0]
        assert call["kind"] == "user_note"
        assert call["content"] == "Tin mới"
        assert call["currencies"] == ["USD", "EUR"]
        assert call["impact_hint"] == "high"
        assert call["url"] == "https://example.com/x"
        assert call["published_utc"].isoformat() == "2026-09-23T10:30:00+00:00"

    def test_edit_form_prefills_and_writes_through_update_path(self):
        controller = FakeNewsController()
        screen = _screen(controller)
        dialog = screen.create_note_dialog(editing_item=USER_ITEM)

        assert dialog.windowTitle() == news.EDIT_DIALOG_TITLE
        assert dialog.content_edit.toPlainText() == "Theo dõi thêm."
        assert dialog.currency_values() == ["JPY"]
        assert dialog.impact_combo.currentData() is None

        dialog.content_edit.setPlainText("Đã sửa")
        dialog.save_button.click()
        _app().processEvents()

        assert dialog.result() == 1
        assert len(controller.update_calls) == 1
        item_id, kwargs = controller.update_calls[0]
        assert item_id == USER_ITEM.id
        assert kwargs["content"] == "Đã sửa"
        assert controller.add_calls == []

    def test_edit_form_with_broken_draft_never_calls_the_update_path(self):
        controller = FakeNewsController()
        screen = _screen(controller)
        dialog = screen.create_note_dialog(editing_item=USER_ITEM)

        dialog.content_edit.setPlainText("")  # draft hỏng: thiếu nội dung
        dialog.save_button.click()
        _app().processEvents()

        assert dialog.result() == 0
        assert controller.update_calls == []  # không xóa/ghi gì


# ---- 4. đường D1 (sửa tin) với NewsController thật + repo giả ------------------


class _NullFF:
    def lookup_event_actual(self, event_id):
        return None


class _RecordingRepo:
    """Repository giả chỉ ghi lời gọi — không DB, không mạng."""

    def __init__(self) -> None:
        self.on_demand_lookup = None
        self.delete_calls: list[int] = []
        self.upsert_calls: list[list[NewsItem]] = []
        self.run_calls: list = []

    def upsert_items(self, items):
        self.upsert_calls.append(list(items))
        return UpsertItemsResult(inserted=1, updated=0)

    def record_run(self, run):
        self.run_calls.append(run)
        return 7

    def delete_user_note(self, item_id):
        self.delete_calls.append(item_id)
        return 1


def _real_controller(repo: _RecordingRepo) -> NewsController:
    return NewsController(
        repo=repo,
        policy=load_news_policy(),
        rss_producer=object(),
        ff_producer=_NullFF(),
    )


class TestUpdateUserNoteContract:
    def test_broken_draft_is_rejected_without_deleting_the_old_row(self):
        repo = _RecordingRepo()
        controller = _real_controller(repo)

        result = controller.update_user_note(
            9, kind="user_note", published_utc=None, content="", currencies=["USD"]
        )

        assert not result.ok
        assert repo.delete_calls == []
        assert repo.upsert_calls == []

    def test_wrong_kind_is_rejected_without_deleting(self):
        repo = _RecordingRepo()
        controller = _real_controller(repo)

        result = controller.update_user_note(
            9,
            kind="headline",
            published_utc="2026-09-23T10:00:00Z",
            content="x",
            currencies=["USD"],
        )

        assert result.errors == (UserNoteFieldError("kind", "not_manual_note"),)
        assert repo.delete_calls == []

    def test_valid_draft_deletes_then_writes_a_fresh_manual_note(self):
        repo = _RecordingRepo()
        controller = _real_controller(repo)

        result = controller.update_user_note(
            9,
            kind="user_note",
            published_utc="2026-09-23T10:00:00Z",
            content="Đã sửa",
            currencies=["USD"],
        )

        assert result.ok
        assert repo.delete_calls == [9]
        assert len(repo.upsert_calls) == 1
        assert repo.upsert_calls[0][0].kind is NewsItemKind.USER_NOTE
        assert repo.run_calls[0].producer is IngestProducer.USER


# ---- 5. sửa/xóa/toggle theo dòng ----------------------------------------------


class TestRowActions:
    def test_user_row_has_toggle_edit_and_delete(self):
        screen = _screen()
        row = _row_for(screen, news.ITEM_ROW, USER_ITEM.title)
        dialog = screen.row_detail_dialog(row)

        labels = {button.text() for button in dialog.findChildren(QPushButton)}
        assert news.EXCLUDE_TEXT in labels
        assert news.EDIT_TEXT in labels
        assert news.DELETE_TEXT in labels

    def test_automatic_row_has_toggle_but_no_edit_or_delete(self):
        screen = _screen()
        row = _row_for(screen, news.ITEM_ROW, AUTO_ITEM.title)
        dialog = screen.row_detail_dialog(row)

        labels = {button.text() for button in dialog.findChildren(QPushButton)}
        assert news.EXCLUDE_TEXT in labels
        assert news.EDIT_TEXT not in labels
        assert news.DELETE_TEXT not in labels

    def test_event_row_has_no_row_actions(self):
        screen = _screen()
        row = _row_for(screen, news.EVENT_ROW, EVENT.title)
        dialog = screen.row_detail_dialog(row)

        labels = {button.text() for button in dialog.findChildren(QPushButton)}
        assert news.EXCLUDE_TEXT not in labels
        assert news.EDIT_TEXT not in labels
        assert news.DELETE_TEXT not in labels

    def test_toggle_excluded_calls_controller_and_reloads(self):
        controller = FakeNewsController()
        screen = _screen(controller)
        reads_before = len(controller.item_calls)
        row = _row_for(screen, news.ITEM_ROW, USER_ITEM.title)
        dialog = screen.row_detail_dialog(row)
        toggle = next(
            button
            for button in dialog.findChildren(QPushButton)
            if button.text() == news.EXCLUDE_TEXT
        )
        assert toggle.isCheckable() is True
        assert toggle.isChecked() is True  # USER_ITEM.excluded = True

        toggle.click()
        _app().processEvents()

        assert controller.exclude_calls == [(USER_ITEM.id, False)]
        assert _wait_until(lambda: len(controller.item_calls) > reads_before)

    def test_delete_confirmation_requires_the_confirm_button(self):
        screen = _screen()
        row = _row_for(screen, news.ITEM_ROW, USER_ITEM.title)

        captured: list[str] = []
        _dismiss_box(captured, news.CANCEL_TEXT)
        assert screen._confirm_delete(row.item) is False

        _dismiss_box(captured, news.DELETE_TEXT)
        assert screen._confirm_delete(row.item) is True

    def test_delete_action_calls_controller_and_closes_detail(self):
        controller = FakeNewsController()
        screen = _screen(controller)
        reads_before = len(controller.item_calls)
        row = _row_for(screen, news.ITEM_ROW, USER_ITEM.title)
        dialog = screen.row_detail_dialog(row)
        screen._confirm_delete = lambda item: True  # type: ignore[method-assign]
        delete_button = next(
            button
            for button in dialog.findChildren(QPushButton)
            if button.text() == news.DELETE_TEXT
        )

        delete_button.click()
        _app().processEvents()

        assert controller.delete_calls == [USER_ITEM.id]
        assert dialog.result() == 1
        assert _wait_until(lambda: len(controller.item_calls) > reads_before)


# ---- 6. empty state + ranh giới lô --------------------------------------------


class TestEmptyStateAndBoundaries:
    def test_empty_state_buttons_are_enabled_and_wired(self):
        controller = FakeNewsController(events=[], items=[])
        screen = _screen(controller)
        _wait_until(lambda: screen.empty_actions.isVisible())

        assert set(screen.empty_state_buttons) == {news.TOOLBAR_LABELS[0], news.TOOLBAR_LABELS[2]}
        for button in screen.empty_state_buttons.values():
            assert button.isEnabled() is True

        opened: list[dict] = []
        screen.open_note_dialog = lambda **kwargs: opened.append(kwargs)  # type: ignore[method-assign]
        captured: list[str] = []
        _dismiss_box(captured, news.CLOSE_TEXT)

        screen.empty_state_buttons[news.TOOLBAR_LABELS[0]].click()
        assert _wait_until(lambda: controller.json_calls == 1)
        # đợi lượt fetch kết thúc (nút re-enable) rồi mới bấm nút form
        assert _wait_until(lambda: screen.empty_state_buttons[news.TOOLBAR_LABELS[2]].isEnabled())

        screen.empty_state_buttons[news.TOOLBAR_LABELS[2]].click()
        assert len(opened) == 1

    def test_remaining_toolbar_buttons_stay_disabled(self):
        screen = _screen()
        live = {
            news.TOOLBAR_LABELS[0],
            news.TOOLBAR_LABELS[1],
            news.TOOLBAR_LABELS[2],
            news.TOOLBAR_LABELS[3],
            news.TOOLBAR_LABELS[4],
        }
        for label, button in screen.toolbar_buttons.items():
            if label in live:
                continue
            assert button.isEnabled() is False  # AI nhận định xu hướng (L3.5)
            assert button.receivers(button.clicked) == 0


# ---- 8. nút "Xuất file"/"Nhập file" (L3.4) ------------------------------------


class TestExportFileButton:
    def test_exports_in_background_disables_and_reports_path(self):
        controller = FakeNewsController()
        controller.export_gate = threading.Event()
        screen = _screen(controller)
        reads_before = len(controller.item_calls)

        captured: list[str] = []
        _dismiss_box(captured, news.CLOSE_TEXT)
        screen._choose_export_format = lambda: "csv"  # type: ignore[method-assign]
        screen.toolbar_buttons[news.TOOLBAR_LABELS[3]].click()

        assert _wait_until(lambda: not screen.toolbar_buttons[news.TOOLBAR_LABELS[3]].isEnabled())
        assert news.LOADING_TEXT in screen.status_message.toPlainText()

        controller.export_gate.set()
        assert _wait_until(lambda: captured), "không thấy thông báo kết quả xuất"
        assert "C:/tmp/exports/news_export_test.csv" in captured[0]  # đường dẫn file
        assert len(controller.export_calls) == 1
        from_utc, to_utc, fmt = controller.export_calls[0]
        assert fmt == "csv"
        assert from_utc and to_utc  # khoảng ngày đang lọc của màn
        assert _wait_until(lambda: screen.toolbar_buttons[news.TOOLBAR_LABELS[3]].isEnabled())
        assert len(controller.item_calls) == reads_before  # xuất không đọc lại bảng

    def test_export_error_reports_cause(self):
        controller = FakeNewsController()
        controller.export_error = RuntimeError("boom")
        screen = _screen(controller)

        captured: list[str] = []
        _dismiss_box(captured, news.CLOSE_TEXT)
        screen._choose_export_format = lambda: "json"  # type: ignore[method-assign]
        screen.toolbar_buttons[news.TOOLBAR_LABELS[3]].click()

        assert _wait_until(lambda: captured)
        assert "boom" in captured[0]

    def test_cancel_format_box_exports_nothing(self):
        controller = FakeNewsController()
        screen = _screen(controller)

        screen._choose_export_format = lambda: None  # type: ignore[method-assign]
        screen.toolbar_buttons[news.TOOLBAR_LABELS[3]].click()
        _app().processEvents()

        assert controller.export_calls == []
        assert screen.toolbar_buttons[news.TOOLBAR_LABELS[3]].isEnabled() is True


class TestImportFileButton:
    def test_imports_the_picked_file_in_background_and_reports_summary(self):
        controller = FakeNewsController()
        controller.import_gate = threading.Event()
        screen = _screen(controller)
        reads_before = len(controller.item_calls)

        captured: list[str] = []
        _dismiss_box(captured, news.CLOSE_TEXT)
        screen._pick_import_path = lambda: "C:/tmp/news_export_test.csv"  # type: ignore[method-assign]
        screen.toolbar_buttons[news.TOOLBAR_LABELS[4]].click()

        assert _wait_until(lambda: not screen.toolbar_buttons[news.TOOLBAR_LABELS[4]].isEnabled())
        assert news.LOADING_TEXT in screen.status_message.toPlainText()

        controller.import_gate.set()
        assert _wait_until(lambda: captured), "không thấy thông báo kết quả nhập"
        text = captured[0]
        assert "3" in text and "2" in text and "1" in text  # mới / cập nhật / bỏ qua trùng
        assert controller.import_calls == ["C:/tmp/news_export_test.csv"]
        assert _wait_until(lambda: screen.toolbar_buttons[news.TOOLBAR_LABELS[4]].isEnabled())
        assert _wait_until(lambda: len(controller.item_calls) > reads_before)  # đọc lại bảng

    def test_import_error_reports_cause(self):
        controller = FakeNewsController()
        controller.import_error = RuntimeError("boom")
        screen = _screen(controller)

        captured: list[str] = []
        _dismiss_box(captured, news.CLOSE_TEXT)
        screen._pick_import_path = lambda: "C:/tmp/bad.csv"  # type: ignore[method-assign]
        screen.toolbar_buttons[news.TOOLBAR_LABELS[4]].click()

        assert _wait_until(lambda: captured)
        assert "boom" in captured[0]

    def test_cancel_picker_imports_nothing(self):
        controller = FakeNewsController()
        screen = _screen(controller)

        screen._pick_import_path = lambda: ""  # type: ignore[method-assign]
        screen.toolbar_buttons[news.TOOLBAR_LABELS[4]].click()
        _app().processEvents()

        assert controller.import_calls == []
        assert screen.toolbar_buttons[news.TOOLBAR_LABELS[4]].isEnabled() is True


# ---- 9. ranh giới mạng của màn (điểm review lô) --------------------------------


def test_screen_has_no_direct_network_or_producer_import():
    import pathlib

    source = pathlib.Path(news.__file__).read_text(encoding="utf-8")
    for forbidden in ("import requests", "import urllib", "import socket", "from services."):
        assert forbidden not in source, forbidden
