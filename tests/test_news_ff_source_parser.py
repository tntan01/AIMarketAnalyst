"""Parser mã nguồn trang ForexFactory (plan lô F2, QĐ-F3/QD-8 — contract §6.1/§5/§11b/§14).

Parser được kiểm như **hàm thuần** (không I/O, không Qt, không mạng, không DB):
đọc source từ fixture rồi truyền text vào ``services/ff_source_parser``.

* **Fixture thật** ``ff_homepage_source.html`` = mã nguồn trang chủ FF Owner dán
  24/09/2026 (PO cấp — QĐ-F5); bản cắt hợp lệ, khối ``calendarComponentStates``
  đóng trọn, đủ 25 sự kiện.
* **Hai fixture biến thể** ``ff_day_source.html`` / ``ff_week_source.html`` là
  **constructed** — dựng theo cấu trúc fixture thật (đa ngày, sự kiện ``holiday``,
  actual rỗng), nhãn ghi rõ trong ``TestConstructedVariants`` (B5 — không phải
  dữ liệu gốc).

Đối chiếu sổ tay plan: JN Flash Manufacturing PMI actual 54.1 / revision 54.9;
AU Employment Change actual 39.5K high; SZ SNB Policy Rate actual 0.00% → đúng 1
``RateObservation`` CHF.
"""

from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

from core.news_models import (
    CalendarEvent,
    EventImpact,
    EventSource,
    EventStatus,
    RateObservation,
    RateSource,
    calendar_event_dedupe_key,
)
from services import ff_source_parser as fsp
from services.ff_source_parser import (
    ParseErrorKind,
    RowDisposition,
    SourceParseOutcome,
    classify_incoming_events,
    finalize_edited_batch,
    parse_calendar_source,
)

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
REAL_SOURCE = (FIXTURES / "ff_homepage_source.html").read_text(
    encoding="utf-8", errors="replace"
)
FETCHED_AT = "2026-09-24T22:00:00Z"


def _real() -> SourceParseOutcome:
    return parse_calendar_source(REAL_SOURCE, fetched_at=FETCHED_AT)


def _by_title(events, title: str) -> CalendarEvent:
    return next(event for event in events if event.title == title)


# ---- 1. Fixture THẬT: ánh xạ §6.1 bước 3 + đối chiếu sổ tay -------------------


class TestRealFixtureMapping:
    def test_real_source_yields_25_events_and_typed_models(self):
        out = _real()
        assert out.error is None
        assert len(out.events) == 25
        assert all(isinstance(event, CalendarEvent) for event in out.events)

    def test_jn_pmi_maps_every_field(self):
        out = _real()
        jn = _by_title(out.events, "JN Flash Manufacturing PMI")
        assert jn.currency == "JPY"
        assert jn.impact is EventImpact.LOW
        assert (jn.forecast, jn.previous, jn.actual) == ("55.0", "55.1", "54.1")
        assert jn.event_time_utc == "2026-09-24T00:30:00Z"  # dateline epoch → UTC
        assert jn.day_key == "2026-09-24"
        assert jn.source is EventSource.FF_HTML  # stamp từ mã nguồn trang dán
        assert jn.status is EventStatus.SCHEDULED  # repository tái phân loại khi ghi
        assert jn.fetched_at == FETCHED_AT

    def test_au_employment_maps_high_impact_and_actual(self):
        out = _real()
        au = _by_title(out.events, "AU Employment Change")
        assert au.impact is EventImpact.HIGH
        assert au.actual == "39.5K"

    def test_empty_actual_yields_null(self):
        out = _real()
        claims = _by_title(out.events, "US Unemployment Claims")
        assert claims.actual is None
        assert claims.forecast is not None  # dự báo vẫn có, chỉ actual rỗng → NULL

    def test_raw_json_carries_provenance_and_original_actual(self):
        out = _real()
        jn = _by_title(out.events, "JN Flash Manufacturing PMI")
        raw = json.loads(jn.raw_json)
        assert raw["revision"] == "54.9"  # sổ tay: actual 54.1 revision 54.9
        assert raw["actual"] == "54.1"  # actual FF gốc giữ cho đợt 4
        assert raw["prefixedName"] == "JN Flash Manufacturing PMI"
        assert isinstance(raw["ebaseId"], int)
        assert raw["soloUrl"].startswith("/calendar/")
        lon = _by_title(out.events, "UK MPC Member Lombardelli Speaks")
        assert json.loads(lon.raw_json)["notice"]  # notice được lưu

    def test_every_dedupe_key_calls_only_the_core_function(self):
        out = _real()
        for event in out.events:
            assert event.dedupe_key == calendar_event_dedupe_key(
                event_time_utc=event.event_time_utc,
                currency=event.currency,
                title=event.title,
            )


# ---- 2. Fixture THẬT: bóc lãi suất §6.1 bước 4 (danh mục kế thừa, B5) -------


class TestRealRateExtraction:
    def test_snb_policy_rate_yields_exactly_one_chf_observation(self):
        out = _real()
        assert len(out.rates) == 1
        obs = out.rates[0]
        assert isinstance(obs, RateObservation)
        assert (obs.currency, obs.rate, obs.observed_at, obs.source) == (
            "CHF", 0.0, "2026-09-24", RateSource.FF_HTML,
        )
        assert obs.fetched_at == FETCHED_AT
        snb = _by_title(out.events, "SZ SNB Policy Rate")
        assert obs.observed_at == snb.day_key  # observed_at = day_key

    def test_no_extra_or_missing_rate_observations(self):
        # "không thừa không thiếu": chỉ sự kiện lãi suất trong danh mục kế thừa
        # có actual đọc được sinh quan sát — fixture thật cho đúng 1 (SNB CHF).
        out = _real()
        snb = _by_title(out.events, "SZ SNB Policy Rate")
        assert len(out.rates) == 1
        assert out.rates[0].currency == snb.currency
        assert out.rates[0].observed_at == snb.day_key


# ---- 3. Biến thể constructed (nhãn rõ — B5): holiday / đa ngày / actual rỗng ---


class TestConstructedVariants:
    # Cả hai fixture là CONSTRUCTED — dựng theo cấu trúc fixture thật (QĐ-F5),
    # không phải dữ liệu gốc.

    def test_day_variant_maps_holiday_to_non_and_empty_actual_to_null(self):
        src = (FIXTURES / "ff_day_source.html").read_text(encoding="utf-8", errors="replace")
        out = parse_calendar_source(src, fetched_at=FETCHED_AT)
        assert out.error is None
        assert len(out.events) == 3
        holiday = _by_title(out.events, "JP Market Holiday")
        assert holiday.impact is EventImpact.NON  # holiday → non (§6.1 bước 3)
        assert holiday.actual is None
        empty = _by_title(out.events, "US New Home Sales")
        assert empty.actual is None  # actual rỗng → NULL
        normal = _by_title(out.events, "DE Ifo Business Climate")
        assert (normal.impact, normal.actual) == (EventImpact.MEDIUM, "87.4")

    def test_week_variant_merges_all_days_and_extracts_rate(self):
        src = (FIXTURES / "ff_week_source.html").read_text(encoding="utf-8", errors="replace")
        out = parse_calendar_source(src, fetched_at=FETCHED_AT)
        assert out.error is None
        # đa ngày: mọi ngày của days[] đều được gom
        assert {event.day_key for event in out.events} == {
            "2026-09-21", "2026-09-22", "2026-09-23",
        }
        assert len(out.events) == 5
        assert len(out.rates) == 1
        aud = out.rates[0]
        assert (aud.currency, aud.rate, aud.observed_at, aud.source) == (
            "AUD", 4.35, "2026-09-22", RateSource.FF_HTML,
        )


# ---- 4. Lỗi fail-closed (B4 — all-or-nothing, lỗi có kiểu, L3) ----------------


class TestParseErrors:
    def test_source_without_calendar_json_is_typed_not_found(self):
        out = parse_calendar_source("<html>no calendar here</html>", fetched_at=FETCHED_AT)
        assert out.error is not None and out.error.kind is ParseErrorKind.NOT_FOUND
        assert out.events == [] and out.rates == []  # không trả nửa vời

    def test_component_without_days_array_is_not_found(self):
        src = (
            "<script>"
            "window.calendarComponentStates[100000] = {"
            " settings: { default_view: 'day' }"
            "};"
            "</script>"
        )
        out = parse_calendar_source(src, fetched_at=FETCHED_AT)
        assert out.error is not None and out.error.kind is ParseErrorKind.NOT_FOUND
        assert out.events == [] and out.rates == []

    def test_cut_off_calendar_json_is_typed_malformed_and_nothing_returned(self):
        src = (
            '<script>'
            'window.calendarComponentStates[100000] = {\n'
            'days: [{"date":"d","events":[{"id":1,"name":"cut"'
        )  # mảng days cắt giữa chừng — JSON hỏng
        out = parse_calendar_source(src, fetched_at=FETCHED_AT)
        assert out.error is not None and out.error.kind is ParseErrorKind.MALFORMED
        assert out.events == [] and out.rates == []


# ---- 5. Phân loại dòng §6.1 bước 5 đợt 4 — 3 nhánh ----------------------------


class TestClassifyIncomingEvents:
    def test_empty_database_marks_every_row_new(self):
        events = _real().events
        assert classify_incoming_events(events, []) == [
            RowDisposition.NEW
        ] * len(events)

    def _existing(self, event: CalendarEvent, *, source=None, actual=None) -> CalendarEvent:
        return CalendarEvent(
            day_key=event.day_key,
            event_time_utc=event.event_time_utc,
            currency=event.currency,
            title=event.title,
            impact=event.impact,
            status=event.status,
            source=source if source is not None else event.source,
            dedupe_key=event.dedupe_key,
            fetched_at=event.fetched_at,
            actual=actual,
        )

    def test_existing_key_is_will_update(self):
        first = _real().events[0]
        existing = [self._existing(first, source=EventSource.FF_HTML, actual=None)]
        assert classify_incoming_events([first], existing) == [RowDisposition.WILL_UPDATE]

    def test_existing_manual_row_with_different_actual_is_conflict(self):
        jn = _by_title(_real().events, "JN Flash Manufacturing PMI")
        existing_manual = self._existing(jn, source=EventSource.USER, actual="99.9")
        assert classify_incoming_events([jn], [existing_manual]) == [
            RowDisposition.CONFLICT_KEEP_MANUAL
        ]

    def test_existing_manual_row_with_same_actual_is_will_update(self):
        jn = _by_title(_real().events, "JN Flash Manufacturing PMI")
        existing_manual = self._existing(jn, source=EventSource.USER, actual=jn.actual)
        assert classify_incoming_events([jn], [existing_manual]) == [RowDisposition.WILL_UPDATE]


# ---- 6. Chung thiện lô đã chỉnh sửa §6.1 bước 6 đợt 4 (QĐ-F6) -----------------


class TestFinalizeEditedBatch:
    def test_without_edits_every_row_keeps_ff_html_and_rates_unchanged(self):
        out = _real()
        batch = finalize_edited_batch(out.events, edited_actuals={}, fetched_at=FETCHED_AT)
        assert all(event.source is EventSource.FF_HTML for event in batch.events)
        assert batch.rates == out.rates
        assert len(batch.rates) == 1

    def test_edited_row_becomes_user_and_keeps_original_actual_in_raw_json(self):
        out = _real()
        jn = _by_title(out.events, "JN Flash Manufacturing PMI")
        batch = finalize_edited_batch(
            out.events, edited_actuals={jn.dedupe_key: "54.5"}, fetched_at=FETCHED_AT,
        )
        edited = next(e for e in batch.events if e.dedupe_key == jn.dedupe_key)
        assert edited.source is EventSource.USER  # dòng sửa → source=user
        assert edited.actual == "54.5"
        assert edited.dedupe_key == jn.dedupe_key  # BẤT BIẾN
        assert json.loads(edited.raw_json)["actual"] == "54.1"  # actual FF gốc giữ
        untouched = _by_title(batch.events, "AU Employment Change")
        assert untouched.source is EventSource.FF_HTML  # dòng không sửa → ff_html
        assert untouched.actual == "39.5K"

    def test_edited_rate_event_resyncs_the_observation_with_ff_html(self):
        out = _real()
        snb = _by_title(out.events, "SZ SNB Policy Rate")
        batch = finalize_edited_batch(
            out.events, edited_actuals={snb.dedupe_key: "0.25%"}, fetched_at=FETCHED_AT,
        )
        edited = next(e for e in batch.events if e.dedupe_key == snb.dedupe_key)
        assert edited.source is EventSource.USER and edited.actual == "0.25%"
        assert len(batch.rates) == 1
        obs = batch.rates[0]
        assert obs.rate == 0.25  # quan sát theo actual ĐÃ SỬA
        assert obs.source is RateSource.FF_HTML  # stamp lãi suất giữ ff_html
        assert obs.observed_at == snb.day_key

    def test_unknown_edit_key_is_ignored(self):
        out = _real()
        batch = finalize_edited_batch(
            out.events, edited_actuals={"no-such-key": "1.0"}, fetched_at=FETCHED_AT,
        )
        assert all(event.source is EventSource.FF_HTML for event in batch.events)


# ---- 7. Ranh giới module (R8, L2, QD-8 — thuần, không bản sao công thức) ------


class TestParserBoundary:
    def test_parser_imports_no_qt_no_network_no_db(self):
        """AST ghim (khuôn test_worker_carries_no_domain_logic): parser chỉ dùng
        stdlib + ``core.news_models`` — cấm services/ui/controllers/Qt/mạng/DB."""
        tree = ast.parse(inspect.getsource(fsp))
        roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
            elif isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
        banned_roots = {
            "PyQt6", "requests", "urllib", "sqlite3", "http", "socket",
            "time", "os", "pathlib", "services", "ui", "controllers",
        }
        assert roots.isdisjoint(banned_roots), sorted(roots & banned_roots)

    def test_parser_defines_no_copy_of_the_dedupe_formula(self):
        """QD-8/R4: công thức §4.2 chỉ MỘT định nghĩa (core/news_models.py) —
        parser chỉ import/gọi, không defin lại sha256 hash."""
        source = inspect.getsource(fsp)
        assert "hashlib" not in source
        assert "calendar_event_dedupe_key(" in source  # đang GỌI hàm core