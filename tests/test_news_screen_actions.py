"""Hành vi tương tác màn Quản lý tin (plan lô L3.3).

Kiểm các nhánh hành vi của lô (screen_design "Hành vi nhập/sửa tin"; contract
§6.4):

* form nhập/sửa ``user_note``: thiếu trường bắt buộc → lỗi trên form, KHÔNG ghi;
  lỗi validate controller hiện từng trường, không đóng;
* sửa/xóa chỉ ``source=user``; toggle Loại trừ mọi dòng tin văn bản; dòng sự
  kiện không có;
* empty state: nút "Nhập tin" enabled và đi đúng đường form; nút "Dán mã nguồn
  trang" là giữ chỗ disabled (đợt 3 — hành vi thật ở F4);
* ranh giới lô: đúng 2 nút thanh công cụ đã nối hành vi [Nhập tin | AI] (đợt 3 —
  4 nút FF/xuất-nhập đã gỡ khỏi toolbar).

Controller là **fake có kiểu** (trả mô hình miền thật ``core/news_models`` +
kết quả thật của ``controllers/news_controller``), không mock sâu, không DB,
không mạng.  Riêng đường D1 (sửa tin) được kiểm thêm với ``NewsController``
THẬT + repository giả ghi lời gọi (không DB) để ghim thứ tự "validate trước,
xóa sau".  Test chạy offscreen; không ghi gì vào repo.
"""

from __future__ import annotations

import dataclasses
import os
import sys
import time
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication, QDialog, QLabel, QMessageBox, QPushButton

from controllers.news_controller import (
    NewsController,
    SourceIngestResult,
    SourcePreview,
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
    NewsItem,
    NewsItemKind,
    NewsItemSource,
    RateObservation,
    RateSource,
)
from core.news_policy import load_news_policy
from services.ff_source_parser import ParseError, ParseErrorKind, RowDisposition
from services.news_repository import UpsertItemsResult
from ui.responsive_row import ResponsiveGrid
from ui.screens import news_screen as news
from ui.screens.news_screen import NewsScreen, build_rows

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


# ---------------------------------------------------------------------------
# Fake controller có kiểu
# ---------------------------------------------------------------------------


class FakeNewsController:
    """Controller giả: ghi lời gọi, trả mô hình/kết quả thật của miền.

    (Đợt 3 — các thành viên của 2 nút FF và xuất/nhập file đã gỡ cùng hành vi
    bị xóa; fake chỉ còn các đường màn còn dùng: đọc bảng, nhập/sửa tin,
    sửa/xóa/toggle.  F4 — mở rộng đúng chữ ký controller thật: parse/commit/
    reclassify.)"""

    def __init__(
        self,
        events: list[CalendarEvent] | None = None,
        items: list[NewsItem] | None = None,
    ) -> None:
        self.events = list(events) if events is not None else [EVENT]
        self.items = list(items) if items is not None else [AUTO_ITEM, USER_ITEM]
        self.event_calls: list[tuple[str, str]] = []
        self.item_calls: list[tuple] = []
        self.add_calls: list[dict] = []
        self.update_calls: list[tuple] = []
        self.exclude_calls: list[tuple] = []
        self.delete_calls: list[int] = []
        self.note_result = UserNoteResult(errors=())
        # F4 — đường dán mã nguồn 2 pha (khuôn chữ ký F3/QĐ-F9).
        self.paste_parse_calls: list[str] = []
        self.paste_commit_calls: list[tuple] = []
        self.paste_reclassify_calls: list[tuple] = []
        self.paste_preview = _sample_preview()
        self.paste_error_preview: SourcePreview | None = None
        self.paste_commit_result = SourceIngestResult(
            inserted=3, updated=1, conflicts=(), rates_written=1, run_id=7
        )
        self.paste_reclassify_result: tuple | None = None

    def events_in_range(self, from_utc, to_utc, currencies=None, include_non_impact=True):
        self.event_calls.append((from_utc, to_utc))
        return list(self.events)

    def items_in_range(self, from_utc, to_utc=None, kinds=None, currencies=None, exclude_flagged=True):
        self.item_calls.append((from_utc, to_utc, exclude_flagged))
        return list(self.items)

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

    # --- F4 — kênh dán mã nguồn (đúng chữ ký controller thật) ------------------

    def parse_pasted_source(self, source_text):
        self.paste_parse_calls.append(source_text)
        if self.paste_error_preview is not None:
            return self.paste_error_preview
        return self.paste_preview

    def commit_pasted_source(self, preview, edited_actuals):
        self.paste_commit_calls.append((preview, dict(edited_actuals)))
        return self.paste_commit_result

    def reclassify_pasted_rows(self, preview, edited_actuals):
        self.paste_reclassify_calls.append((preview, dict(edited_actuals)))
        if self.paste_reclassify_result is not None:
            return self.paste_reclassify_result
        return tuple(self.paste_preview.dispositions)


def _sample_preview() -> SourcePreview:
    """Lô bóc giả có kiểu: 3 sự kiện (new / sẽ cập nhật / xung đột-giữ-nhập-tay)
    + 1 quan sát lãi suất — để kiểm bảng preview + đếm lãi suất."""

    def event(*, day: str, time_utc: str, currency: str, title: str, actual: str | None, key: str) -> CalendarEvent:
        return dataclasses.replace(
            EVENT,
            day_key=day,
            event_time_utc=time_utc,
            currency=currency,
            title=title,
            actual=actual,
            dedupe_key=key,
        )

    return SourcePreview(
        events=[
            event(day="2026-09-20", time_utc="2026-09-20T14:30:00Z", currency="USD", title="FOMC Meeting", actual="5.50%", key="event-1"),
            event(day="2026-09-21", time_utc="2026-09-21T09:00:00Z", currency="AUD", title="AU Employment Change", actual="39.5K", key="event-2"),
            event(day="2026-09-22", time_utc="2026-09-22T10:00:00Z", currency="JPY", title="JN Flash Manufacturing PMI", actual="54.1", key="event-3"),
        ],
        rates=[
            RateObservation(
                currency="CHF", rate=0.0, observed_at="2026-09-24",
                source=RateSource.FF_HTML, fetched_at="2026-09-24T22:00:00Z",
            )
        ],
        dispositions=(
            RowDisposition.NEW,
            RowDisposition.WILL_UPDATE,
            RowDisposition.CONFLICT_KEEP_MANUAL,
        ),
        error=None,
        fetched_at="2026-09-24T22:00:00Z",
    )


_SCREENS: list[NewsScreen] = []


@pytest.fixture(scope="module", autouse=True)
def _close_screens():
    yield
    for screen in _SCREENS:
        screen.shutdown()
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


def _preview_cell(dialog, row: int, key: str) -> str:
    """Ô của bảng xem trước theo khóa cột (vd "actual", "disposition")."""
    model = dialog.preview_model
    column = next(i for i, (k, _label) in enumerate(model.COLUMNS) if k == key)
    return model.data(model.index(row, column), Qt.ItemDataRole.DisplayRole)


def _paste_dialog(controller: FakeNewsController | None = None):
    """Dựng màn + dialog dán mã nguồn (không exec — test lái trực tiếp; dialog
    được show để ``isVisible`` phản ánh đúng pha)."""
    controller = controller or FakeNewsController()
    screen = _screen(controller)
    dialog = screen.create_paste_dialog()
    dialog.show()
    _app().processEvents()
    return controller, dialog


def _parse_source(controller, dialog, source: str = "SOURCE") -> None:
    """Đưa dialog qua pha 1 → pha 2 (đợi worker parse hoàn tất — không block)."""
    dialog.source_edit.setPlainText(source)
    dialog.parse_button.click()
    assert _wait_until(lambda: not dialog._busy), "worker parse chưa kết thúc"
    _app().processEvents()


# ---- 1-2. (gỡ đợt 3: 2 nút FF "Lấy lịch kinh tế"/"Cập nhật actual" + gợi ý
# ----    "Nhập actual bằng tay" — test của hành vi bị xóa) --------------------

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


class _RecordingRepo:
    """Repository giả chỉ ghi lời gọi — không DB, không mạng."""

    def __init__(self) -> None:
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
        """F4 — empty state gợi ý "Dán mã nguồn trang" (nối dialog dán — không
        còn giữ chỗ) + "Nhập tin" (đi thẳng form)."""
        controller = FakeNewsController(events=[], items=[])
        screen = _screen(controller)
        _wait_until(lambda: screen.empty_actions.isVisible())

        assert set(screen.empty_state_buttons) == {news.PASTE_SOURCE_TEXT, news.TOOLBAR_LABELS[1]}
        for label, button in screen.empty_state_buttons.items():
            assert button.isEnabled() is True
            assert button.receivers(button.clicked) >= 1

    def test_the_three_toolbar_buttons_are_wired(self):
        """F4: toolbar đúng 3 nút [ Dán mã nguồn trang | Nhập tin | AI nhận định
        xu hướng ] — cả ba đã nối hành vi."""
        screen = _screen()
        assert set(screen.toolbar_buttons) == set(news.TOOLBAR_LABELS)
        skipped: list[str] = []
        for label, button in screen.toolbar_buttons.items():
            if label == news.TOOLBAR_LABELS[0]:
                continue  # mở dialog chặn — không click trong test
            assert button.isEnabled() is True
            assert button.receivers(button.clicked) >= 1
        assert news.TOOLBAR_LABELS[0] not in skipped
        assert screen.toolbar_buttons[news.TOOLBAR_LABELS[0]].isEnabled() is True

    def test_empty_state_paste_button_opens_the_paste_dialog(self):
        """Nút empty state "Dán mã nguồn trang" đi thẳng dialog dán (cùng handler
        với nút toolbar — d.1634-1635)."""
        controller = FakeNewsController(events=[], items=[])
        screen = _screen(controller)
        _wait_until(lambda: screen.empty_actions.isVisible())

        opened: list[str] = []
        screen.open_paste_dialog = lambda: opened.append("paste")  # type: ignore[method-assign]

        screen.empty_state_buttons[news.PASTE_SOURCE_TEXT].click()
        assert opened == ["paste"]


# ---- 8. (gỡ đợt 3: 2 nút "Xuất file"/"Nhập file" — test của hành vi bị xóa) ----

# ---- 9. ranh giới mạng của màn (điểm review lô) --------------------------------


def test_screen_has_no_direct_network_or_producer_import():
    import pathlib

    source = pathlib.Path(news.__file__).read_text(encoding="utf-8")
    for forbidden in ("import requests", "import urllib", "import socket", "from services."):
        assert forbidden not in source, forbidden
    # UI không tự bóc/phân loại — chỉ đi qua controller (R8/S2).
    for symbol in ("parse_calendar_source", "classify_incoming_events", "finalize_edited_batch"):
        assert symbol not in source, symbol


# ---- 10. F4 — dialog dán mã nguồn 2 pha (screen_design d.1579-1617) -------------


class TestPasteDialog:
    def test_dialog_starts_in_phase_one_with_registered_labels(self):
        controller, dialog = _paste_dialog()

        assert dialog.windowTitle() == news.PASTE_DIALOG_TITLE
        assert dialog._phase_1.isVisible() is True
        assert dialog._phase_2.isVisible() is False
        assert dialog.cancel_button.isVisible() is False  # "Hủy" chỉ hiện ở pha 2
        assert dialog.commit_button.isVisible() is False  # "Cập nhật" chỉ hiện ở pha 2
        labels = {button.text() for button in dialog.findChildren(QPushButton)}
        assert news.PASTE_PARSE_TEXT in labels  # "Bóc tách"
        assert news.PASTE_FILE_TEXT in labels  # "Chọn file .html"
        step_texts = " ".join(
            label.text() for label in dialog._phase_1.findChildren(QLabel)
        )  # hướng dẫn 3 bước (d.1588-1590)
        assert "Mở trang lịch FF" in step_texts

    def test_parse_fills_the_preview_table_with_badges_and_rates(self):
        controller, dialog = _paste_dialog()
        _parse_source(controller, dialog)

        assert controller.paste_parse_calls == ["SOURCE"]
        model = dialog.preview_model
        assert model.rowCount() == 3
        assert _preview_cell(dialog, 0, "actual") == "5.50%"
        # nhãn badge ĐÚNG TỪNG CHUỖI từ điển d.1577
        assert _preview_cell(dialog, 0, "disposition") == news.PREVIEW_STATUS_TEXT["new"]
        assert _preview_cell(dialog, 1, "disposition") == news.PREVIEW_STATUS_TEXT["will_update"]
        assert _preview_cell(dialog, 2, "disposition") == news.PREVIEW_STATUS_TEXT["conflict_keep_manual"]
        assert dialog.rates_label.text() == news.PASTE_RATES_TEXT.format(count=1)
        assert controller.paste_commit_calls == []

    def test_every_column_except_actual_is_read_only(self):
        controller, dialog = _paste_dialog()
        _parse_source(controller, dialog)
        model = dialog.preview_model

        for row in range(model.rowCount()):
            for column in range(model.columnCount()):
                key = model.COLUMNS[column][0]
                flags = model.flags(model.index(row, column))
                editable = bool(flags & Qt.ItemFlag.ItemIsEditable)
                assert editable is (key == news.PastePreviewModel.ACTUAL_KEY), key

    def test_editing_actual_marks_edited_badge_and_calls_reclassify(self):
        controller, dialog = _paste_dialog()
        _parse_source(controller, dialog)

        model = dialog.preview_model
        actual_col = next(
            i for i, (k, _l) in enumerate(model.COLUMNS) if k == model.ACTUAL_KEY
        )
        wrote = model.setData(model.index(1, actual_col), "40.0", Qt.ItemDataRole.EditRole)

        assert wrote is True
        assert _preview_cell(dialog, 1, "disposition") == news.PREVIEW_STATUS_TEXT["edited"]
        assert _wait_until(lambda: len(controller.paste_reclassify_calls) >= 1)
        preview_arg, edited_arg = controller.paste_reclassify_calls[0]
        assert preview_arg is controller.paste_preview
        assert edited_arg == {"event-2": "40.0"}
        assert controller.paste_commit_calls == []

    def test_commit_sends_edited_actuals_shows_summary_and_accepts(self):
        controller, dialog = _paste_dialog()
        _parse_source(controller, dialog)
        model = dialog.preview_model
        actual_col = next(i for i, (k, _l) in enumerate(model.COLUMNS) if k == model.ACTUAL_KEY)
        model.setData(model.index(0, actual_col), "5.75%", Qt.ItemDataRole.EditRole)
        _wait_until(lambda: not dialog._busy)

        dialog.commit_button.click()
        assert _wait_until(lambda: dialog.result() == QDialog.DialogCode.Accepted, 8)

        assert len(controller.paste_commit_calls) == 1
        preview_arg, edited_arg = controller.paste_commit_calls[0]
        assert preview_arg is controller.paste_preview
        assert edited_arg == {"event-1": "5.75%"}
        expected = news.PASTE_SUMMARY_TEXT.format(
            inserted=3, updated=1, conflicts=0, rates=1
        )
        assert dialog.summary_label.text() == expected

    def test_cancel_rejects_without_calling_commit(self):
        controller, dialog = _paste_dialog()
        _parse_source(controller, dialog)

        dialog.cancel_button.click()
        _app().processEvents()

        assert dialog.result() == QDialog.DialogCode.Rejected
        assert controller.paste_commit_calls == []  # "Hủy" không chạm commit

    def test_parse_error_shows_dictionary_message_and_stays_in_phase_one(self):
        controller = FakeNewsController()
        controller.paste_error_preview = SourcePreview(
            events=[],
            rates=[],
            dispositions=(),
            error=ParseError(ParseErrorKind.NOT_FOUND, "no calendar"),
            fetched_at="2026-09-24T22:00:00Z",
        )
        _, dialog = _paste_dialog(controller)
        _parse_source(controller, dialog)

        assert news.PARSE_ERROR_TEXT["not_found"] in dialog._status_label.text()
        assert dialog._phase_1.isVisible() is True
        assert dialog._phase_2.isVisible() is False
        assert controller.paste_parse_calls == ["SOURCE"]

    def test_choose_html_file_reads_in_worker_and_enters_the_flow(self, tmp_path, monkeypatch):
        controller, dialog = _paste_dialog()
        target = tmp_path / "page.html"
        target.write_text("FILE_CONTENT", encoding="utf-8")
        monkeypatch.setattr(
            news.QFileDialog, "getOpenFileName",
            lambda *args, **kwargs: (str(target), ""),
        )

        dialog.file_button.click()

        assert _wait_until(lambda: controller.paste_parse_calls == ["FILE_CONTENT"])  # đưa vào luồng bóc
        assert dialog.source_edit.toPlainText() == "FILE_CONTENT"
        assert _wait_until(lambda: dialog._phase_2.isVisible())


# ---- 11. card tìm kiếm: chỉ tìm khi bấm nút (Owner duyệt 26/09/2026) -----------

class TestFilterSearchButton:
    def test_changing_combo_or_date_does_not_trigger_a_read(self):
        controller = FakeNewsController()
        screen = _screen(controller)
        assert len(controller.event_calls) == 1  # lượt nạp khi mở màn

        screen.kind_combo.setCurrentIndex(screen.kind_combo.findData("user_note"))
        screen.date_from_input.setDate(screen.date_from_input.date().addDays(-3))
        _app().processEvents()

        assert len(controller.event_calls) == 1  # KHÔNG tự đọc lại DB khi chọn ô

    def test_search_button_rereads_the_database(self):
        controller = FakeNewsController()
        screen = _screen(controller)

        screen.search_button.click()

        assert _wait_until(lambda: len(controller.event_calls) == 2)
        assert _wait_until(lambda: len(controller.item_calls) == 2)

    def test_search_applies_the_selected_filters(self):
        controller = FakeNewsController()
        screen = _screen(controller)
        assert screen.table_model.rowCount() > 1  # mặc định: nhiều loại tin

        screen.kind_combo.setCurrentIndex(screen.kind_combo.findData("user_note"))
        screen.search_button.click()
        assert _wait_until(lambda: len(controller.event_calls) == 2)
        _app().processEvents()

        # lọc theo loại "Nhập tay": chỉ còn dòng USER_ITEM
        assert _wait_until(lambda: screen.table_model.rowCount() == 1)


# ---- 12. card lọc gọn ở mọi bề ngang (defect 1920×1200@150% = 1280px logic) ----

class TestFilterCardLayout:
    def _assert_glued(self, cell, widget_indexes):
        """Nhãn và các ô trong một ô lọc phải sát nhau (khe ≤ 6px, nhãn x=0)."""
        layout = cell.layout()
        label = layout.itemAt(0).widget()
        assert label.x() == 0
        assert label.width() <= 200, "nhãn bị giãn nở"
        previous_end = label.x() + label.width()
        for index in widget_indexes:
            widget = layout.itemAt(index).widget()
            assert widget.x() - previous_end <= 6, f"khe {widget} ↔ nhãn bị rộng"
            previous_end = widget.x() + widget.width()

    def test_labels_stay_glued_to_fields_at_1280_logical(self):
        controller = FakeNewsController()
        screen = _screen(controller)
        screen.resize(1280, 800)
        _app().processEvents()

        grid = screen.findChildren(ResponsiveGrid)[0]
        # không rơi thẳng về compact 1 cột ở 1280px logic (1920×1200@150%) —
        # metric font đổi theo môi trường nên chỉ ghim BẤT BIẾN: nhiều hơn compact.
        assert grid.column_count() > grid._compact_columns

        for combo in (
            screen.kind_combo,
            screen.currency_combo,
            screen.impact_combo,
            screen.source_combo,
            screen.status_combo,
        ):
            self._assert_glued(combo.parent(), [1])
        self._assert_glued(screen.date_from_input.parent(), [1, 2, 3])
        assert screen.search_button.width() <= 200, "nút tìm kiếm giãn full cột"

    def test_narrow_screen_never_keeps_the_full_column_count(self):
        controller = FakeNewsController()
        screen = _screen(controller)
        screen.resize(752, 500)
        _app().processEvents()

        grid = screen.findChildren(ResponsiveGrid)[0]
        # hẹp thì xuống dòng: không giữ nguyên 4 cột desktop; số cột đúng bằng
        # số cột vừa bề ngang (fluid — không ghim số tuyệt đối vì metric font
        # đổi theo môi trường chạy).
        assert grid.column_count() < grid._columns
        assert grid.column_count() == grid._fitted_columns()

    def test_cells_flow_in_row_major_order_for_the_fitted_columns(self):
        # Owner quyết 26/09/2026: dòng 1 = Loại tin/Đồng tiền/Tác động/Nguồn;
        # dòng 2 = Trạng thái/Khoảng ngày/nút "Tìm kiếm" — lưới đầy 4×2 đủ 7 ô,
        # nút là ô cuối thay _action_cell. Fluid (vòng 7)
        # lấy SỐ CỘT LỚN NHẤT vừa bề ngang trong [4..1], nên số cột thật phụ
        # thuộc font môi trường — chỉ ghim BẤT BIẾN: 7 ô xếp theo dòng (hết
        # một dòng mới xuống dòng kế — bố cục chảy, không ô nào mất vị trí),
        # nút "Tìm kiếm" là ô chót cùng.
        controller = FakeNewsController()
        screen = _screen(controller)
        screen.resize(1280, 800)
        _app().processEvents()

        grid = screen.findChildren(ResponsiveGrid)[0]
        fitted = grid.column_count()
        assert grid.column_count() == grid._fitted_columns()
        assert 1 <= fitted <= 4

        def cell_of(widget):
            # item của lưới là Ô LỌC (widget cha chứa nhãn + ô nhập), leo cấp
            # cha cho tới widget nằm trực tiếp trong lưới.
            node = widget
            while node is not None and node.parent() is not grid:
                node = node.parent()
            assert node is not None, "widget không nằm trong lưới"
            return node

        def position_of(widget):
            cell = cell_of(widget)
            for index in range(grid._grid.count()):
                item = grid._grid.itemAt(index)
                if item is not None and item.widget() is cell:
                    return grid._grid.getItemPosition(index)
            raise AssertionError("widget không nằm trong lưới")

        cells = [
            screen.kind_combo, screen.currency_combo, screen.impact_combo,
            screen.source_combo, screen.status_combo, screen.date_from_input,
            screen.search_button,
        ]
        for order, widget in enumerate(cells):
            row, col = position_of(widget)[:2]
            assert (row, col) == (order // fitted, order % fitted), (
                f"ô {widget.objectName()} sai vị trí ({row},{col}) thay cho "
                f"({order // fitted},{order % fitted})"
            )

    def test_inputs_align_within_each_grid_column(self):
        # Owner yêu cầu 26/09/2026 ("sắp thẳng cột"): các ô CÙNG cột lưới
        # (bất kỳ chế độ fluid nào — 4, 2 hay 1 cột) phải bắt đầu tại CÙNG tọa
        # độ. Vòng 6: nút "Tìm kiếm" là ô cuối lưới (phần tử bình thường sau
        # "Khoảng ngày"); cột nhãn đồng nhất ⇒ mép phải nhãn thẳng hàng mọi dòng.
        controller = FakeNewsController()
        screen = _screen(controller)
        screen.resize(1280, 800)
        _app().processEvents()

        grid = screen.findChildren(ResponsiveGrid)[0]

        def cell_of(widget):
            node = widget
            while node is not None and node.parent() is not grid:
                node = node.parent()
            assert node is not None, "widget không nằm trong lưới"
            return node

        def column_of(widget):
            cell = cell_of(widget)
            for index in range(grid._grid.count()):
                item = grid._grid.itemAt(index)
                if item is not None and item.widget() is cell:
                    return grid._grid.getItemPosition(index)[1]
            raise AssertionError("widget không nằm trong lưới")

        def cell_x(widget):
            return widget.mapTo(grid, widget.rect().topLeft()).x()

        pairs = (
            (screen.kind_combo, screen.status_combo),
            (screen.currency_combo, screen.date_from_input),
            (screen.impact_combo, screen.search_button),
        )
        # Tại bề ngang 1280 logic (4×2 với font hẹp, 2 cột với font rộng/
        # offscreen) các cặp "dòng 1–dòng 2" nằm chung một cột lưới — mỗi cặp
        # chung cột phải khớp tọa độ bắt đầu (thẳng cột).
        for first, second in pairs:
            if column_of(first) != column_of(second):
                continue
            assert cell_x(cell_of(first)) == cell_x(cell_of(second)), (
                f"ô cùng cột lệch tọa độ: {first.objectName()} vs "
                f"{second.objectName()}"
            )
        # cột nhãn đồng nhất: mọi nhãn cùng bề rộng ⇒ mép phải nhãn thẳng hàng.
        widths = {
            combo.parent().layout().itemAt(0).widget().width()
            for combo in (
                screen.kind_combo, screen.currency_combo, screen.impact_combo,
                screen.source_combo, screen.status_combo, screen.date_from_input,
            )
        }
        assert len(widths) == 1, f"bề rộng nhãn không đồng nhất: {widths}"


# ---- 13. dirty state của nút Tìm kiếm (vòng 6, 26/09/2026) ----

class TestFilterDirtyState:
    def test_search_button_marks_dirty_until_search_is_applied(self):
        controller = FakeNewsController()
        screen = _screen(controller)
        assert not screen.search_button.property("filterDirty")

        screen.kind_combo.setCurrentIndex(screen.kind_combo.findData("user_note"))
        _app().processEvents()
        assert screen.search_button.property("filterDirty") is True

        screen.search_button.click()
        assert _wait_until(lambda: len(controller.event_calls) == 2)
        _app().processEvents()
        assert not screen.search_button.property("filterDirty")

    def test_date_change_marks_dirty_because_the_window_changed(self):
        controller = FakeNewsController()
        screen = _screen(controller)
        assert not screen.search_button.property("filterDirty")

        screen.date_from_input.setDate(screen.date_from_input.date().addDays(-30))
        _app().processEvents()
        assert screen.search_button.property("filterDirty") is True
