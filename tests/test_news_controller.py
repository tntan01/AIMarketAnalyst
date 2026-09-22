"""NewsController + NewsWorker + DI registration tests (plan lô L2.7).

Orchestration is exercised with **typed fakes** (a fake repository that records
calls and returns the domain models, fake producers that return the producers'
own typed results) plus the **real** ``NewsRepository`` on a throwaway temp DB
where the write path itself is under test (manual entry, dedupe, the kind guard)
— no deep mocking, no real network, ``%APPDATA%`` never touched.

Lô L2.7 checklist covered here: lịch producer theo chính sách (không hard-code),
điểm nối on-demand lookup, validate nhập tay đủ nhánh (thiếu trường ⇒ không ghi
DB), uỷ quyền đọc có kiểu (C3/S2), worker không chứa logic nghiệp vụ, và DI
property ``app_controller.news_controller`` lazy.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import inspect
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from config.paths import PROJECT_ROOT
from controllers import app_controller as app_controller_module
from controllers.app_controller import AppController
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
    IngestProducer,
    IngestRun,
    IngestRunStatus,
    NewsItem,
    NewsItemKind,
    NewsItemSource,
    RateObservation,
    RateSource,
    StoreState,
    StoreStatus,
)
from core.news_policy import NewsPolicy
from core.rate_trend import RateTrend
from services.news_repository import (
    CurrencyRateTrend,
    NewsRepository,
    UpsertItemsResult,
)
from workers.news_worker import NewsWorker
from workers.base_worker import WorkerState

NEWS_MIGRATIONS_DIR = PROJECT_ROOT / "data" / "migrations" / "news"


# ---- typed fakes (no deep mocks) ------------------------------------------------


class FakeRepository:
    """Typed stand-in for ``NewsRepository``: records every call and returns the
    domain models (never a bare dict) — the orchestration under test is the
    controller's, so the store itself is not exercised here."""

    def __init__(self) -> None:
        self.on_demand_lookup = None
        self.calls: list[tuple[str, tuple, dict]] = []
        self.upsert_items_calls: list[list[NewsItem]] = []
        self.upsert_items_result = UpsertItemsResult(inserted=1, updated=0)
        self.record_run_calls: list[IngestRun] = []
        self.record_run_result = 42
        self.set_excluded_result = 1
        self.delete_user_note_result = 1
        self.events: list[CalendarEvent] = []
        self.pending: list[CalendarEvent] = []
        self.event: CalendarEvent | None = None
        self.items: list[NewsItem] = []
        self.rates: list[CurrencyRateTrend] = []
        self.state = StoreState(
            events_state=StoreStatus.FRESH,
            items_state=StoreStatus.FRESH,
            rates_state=StoreStatus.FRESH,
        )

    def _record(self, name: str, args: tuple, kwargs: dict) -> None:
        self.calls.append((name, args, kwargs))

    def upsert_items(self, items: list[NewsItem]) -> UpsertItemsResult:
        self._record("upsert_items", (items,), {})
        self.upsert_items_calls.append(list(items))
        return self.upsert_items_result

    def record_run(self, run: IngestRun) -> int:
        self._record("record_run", (run,), {})
        self.record_run_calls.append(run)
        return self.record_run_result

    def set_excluded(self, item_id: int, excluded: bool) -> int:
        self._record("set_excluded", (item_id, excluded), {})
        return self.set_excluded_result

    def delete_user_note(self, item_id: int) -> int:
        self._record("delete_user_note", (item_id,), {})
        return self.delete_user_note_result

    def events_in_range(self, *args: object, **kwargs: object) -> list[CalendarEvent]:
        self._record("events_in_range", args, kwargs)
        return self.events

    def events_pending_actual(self, now: datetime) -> list[CalendarEvent]:
        self._record("events_pending_actual", (now,), {})
        return self.pending

    def event_actual_or_lookup(self, event_id: int) -> CalendarEvent | None:
        self._record("event_actual_or_lookup", (event_id,), {})
        return self.event

    def items_in_range(self, *args: object, **kwargs: object) -> list[NewsItem]:
        self._record("items_in_range", args, kwargs)
        return self.items

    def latest_rates(self, currencies: list[str]) -> list[CurrencyRateTrend]:
        self._record("latest_rates", (currencies,), {})
        return self.rates

    def store_state(self) -> StoreState:
        self._record("store_state", (), {})
        return self.state


class FakeRssProducer:
    """Typed fake of ``rss_producer``: counts rounds, returns a typed result."""

    def __init__(self, result: object | None = None) -> None:
        self.rounds = 0
        self.nows: list[datetime | None] = []
        self.result = result if result is not None else _rss_result()

    def fetch_round(self, now: datetime | None = None) -> object:
        self.rounds += 1
        self.nows.append(now)
        return self.result


class FakeRateProducer:
    """Typed fake of ``fred_rate_producer``: counts rounds, exposes the cadence."""

    def __init__(self, result: object | None = None, refresh_hours: int = 6) -> None:
        self.rounds = 0
        self.result = result if result is not None else _rates_result()
        self._refresh_hours = refresh_hours

    @property
    def refresh_hours(self) -> int:
        return self._refresh_hours

    def fetch_round(self) -> object:
        self.rounds += 1
        return self.result


class FakeFfProducer:
    """Typed fake of ``ff_calendar_producer`` — records the on-demand lookups."""

    def __init__(self, result: CalendarEvent | None = None) -> None:
        self.lookups: list[int] = []
        self.result = result

    def lookup_event_actual(self, event_id: int) -> CalendarEvent | None:
        self.lookups.append(event_id)
        return self.result


class FakeController:
    """Typed fake of ``NewsController`` for the worker tests (worker must only
    forward what the controller returns)."""

    def __init__(self, *, rss_poll_interval_minutes: int = 15, rates_refresh_hours: int = 6):
        self.rss_poll_interval_minutes = rss_poll_interval_minutes
        self.rates_refresh_hours = rates_refresh_hours
        self.news_result = _rss_result()
        self.rates_result = _rates_result()
        self.news_error: Exception | None = None
        self.rates_error: Exception | None = None
        self.poll_calls = 0
        self.refresh_calls = 0

    def poll_news(self) -> object:
        self.poll_calls += 1
        if self.news_error is not None:
            raise self.news_error
        return self.news_result

    def refresh_rates(self) -> object:
        self.refresh_calls += 1
        if self.rates_error is not None:
            raise self.rates_error
        return self.rates_result


def _rss_result() -> object:
    from services.news_producers.rss_producer import RssCollectionResult

    return RssCollectionResult(
        inserted=2,
        updated=1,
        run_status=IngestRunStatus.OK,
        run_id=11,
        attempted_sources=11,
        successful_sources=11,
        source_errors=(),
    )


def _rates_result() -> object:
    from services.news_producers.fred_rate_producer import RateFetchResult

    return RateFetchResult(
        fred_observations=16,
        ff_html_observations=0,
        config_fallback_observations=0,
        currencies_covered=("AUD", "USD"),
        run_status=IngestRunStatus.OK,
        run_id=12,
        errors=(),
    )


# ---- fixtures -------------------------------------------------------------------


def _policy(**overrides: object) -> NewsPolicy:
    data: dict[str, object] = {
        "policy_version": "news-policy",
        "rss_poll_interval_minutes": 15,
        "rss_window_hours": 24,
        "fred_refresh_hours": 6,
        "event_stale_grace_minutes": 15,
        "ingest_freshness_hours": 2,
        "ingest_runs_retention_days": 30,
        "ai_window_days": 7,
        "ai_min_items": 3,
        "ai_horizons": {
            "short": {"unit": "day", "min": 0, "max": 3},
            "mid": {"unit": "week", "min": 1, "max": 4},
            "long": {"unit": "month", "min": 1, "max": 6},
        },
    }
    data.update(overrides)
    return NewsPolicy.from_dict(data)


def _repo(tmp_path: Path) -> NewsRepository:
    return NewsRepository(db_path=tmp_path / "news.db", migrations_dir=NEWS_MIGRATIONS_DIR)


def _controller(
    *,
    repo: object | None = None,
    policy: NewsPolicy | None = None,
    rss: object | None = None,
    rates: object | None = None,
    ff: object | None = None,
) -> NewsController:
    return NewsController(
        repo=repo if repo is not None else FakeRepository(),
        policy=policy if policy is not None else _policy(),
        rss_producer=rss if rss is not None else FakeRssProducer(),
        fred_producer=rates if rates is not None else FakeRateProducer(),
        ff_producer=ff if ff is not None else FakeFfProducer(),
    )


def _rows(db_path: Path, sql: str = "SELECT * FROM news_items", params: tuple = ()) -> list[dict]:
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _auto_item(dedupe_key: str = "auto-1") -> NewsItem:
    return NewsItem(
        kind=NewsItemKind.HEADLINE,
        source=NewsItemSource.GOOGLE_NEWS_RSS,
        title="Fed signals patience",
        published_utc="2026-09-22T08:00:00Z",
        currencies=["USD"],
        dedupe_key=dedupe_key,
        fetched_at="2026-09-22T08:05:00Z",
    )


def _stale_event() -> CalendarEvent:
    past = (datetime.now(UTC) - timedelta(hours=2)).isoformat(timespec="seconds").replace("+00:00", "Z")
    return CalendarEvent(
        day_key=past[:10],
        event_time_utc=past,
        currency="USD",
        title="FOMC Meeting",
        impact=EventImpact.HIGH,
        status=EventStatus.SCHEDULED,
        source=EventSource.FF_JSON,
        dedupe_key="stale-1",
        fetched_at=past,
    )


# ---- 1. điều phối producer theo chính sách --------------------------------------


class TestProducerSchedule:
    def test_poll_news_runs_exactly_one_rss_round(self):
        rss = FakeRssProducer()
        controller = _controller(rss=rss)

        result = controller.poll_news()

        assert rss.rounds == 1
        assert rss.nows == [None]  # cửa sổ do producer đọc từ policy (R4)
        assert result is rss.result

    def test_refresh_rates_runs_exactly_one_fred_round(self):
        rates = FakeRateProducer()
        controller = _controller(rates=rates)

        result = controller.refresh_rates()

        assert rates.rounds == 1
        assert result is rates.result

    def test_rss_cadence_comes_from_the_policy_key(self):
        controller = _controller(policy=_policy(rss_poll_interval_minutes=7))
        assert controller.rss_poll_interval_minutes == 7

    def test_rates_cadence_is_read_from_the_rate_producer(self):
        rates = FakeRateProducer(refresh_hours=3)
        controller = _controller(policy=_policy(fred_refresh_hours=6), rates=rates)
        assert controller.rates_refresh_hours == 3  # nguồn: producer (khóa policy)

    def test_rates_producer_is_built_lazily_with_the_policy_cadence(self):
        # Không inject producer FRED ⇒ controller tự dựng (không gọi mạng) và
        # đọc đúng khóa ``fred_refresh_hours`` của policy.
        controller = NewsController(
            repo=FakeRepository(),
            policy=_policy(fred_refresh_hours=4),
            rss_producer=FakeRssProducer(),
            ff_producer=FakeFfProducer(),
        )

        assert controller.rates_refresh_hours == 4

    def test_construction_starts_no_round(self):
        """Plan L2.7: lượt fetch khởi động là L3.6 — dựng controller không gọi gì."""
        rss, rates = FakeRssProducer(), FakeRateProducer()
        repo = FakeRepository()
        _controller(repo=repo, rss=rss, rates=rates)

        assert (rss.rounds, rates.rounds) == (0, 0)
        assert repo.upsert_items_calls == []


# ---- 2. điểm nối on-demand lookup (§6.1 lượt 4) ---------------------------------


class TestOnDemandLookupSeam:
    def test_constructor_plugs_the_ff_producer_into_the_repository(self):
        repo, ff = FakeRepository(), FakeFfProducer()

        _controller(repo=repo, ff=ff)

        assert repo.on_demand_lookup == ff.lookup_event_actual

    def test_stale_event_triggers_the_lookup_once(self, tmp_path):
        repo = _repo(tmp_path)
        repo.upsert_events([_stale_event()])
        stored = repo.events_in_range("2000-01-01T00:00:00Z", "2100-01-01T00:00:00Z")[0]
        assert stored.status == EventStatus.STALE  # phân loại lúc đọc (§6.5)
        refreshed = dataclasses.replace(_stale_event(), actual="5.50%", id=stored.id)
        ff = FakeFfProducer(result=refreshed)
        controller = _controller(repo=repo, ff=ff)

        result = controller.event_actual_or_lookup(stored.id)

        assert ff.lookups == [stored.id]
        assert result is refreshed

    def test_future_event_does_not_trigger_the_lookup(self, tmp_path):
        repo = _repo(tmp_path)
        future = _stale_event()
        ahead = (datetime.now(UTC) + timedelta(days=1)).isoformat(timespec="seconds").replace("+00:00", "Z")
        event = CalendarEvent(
            day_key=ahead[:10],
            event_time_utc=ahead,
            currency=future.currency,
            title=future.title,
            impact=future.impact,
            status=future.status,
            source=future.source,
            dedupe_key="future-1",
            fetched_at=future.fetched_at,
        )
        repo.upsert_events([event])
        stored = repo.events_in_range("2000-01-01T00:00:00Z", "2100-01-01T00:00:00Z")[0]
        ff = FakeFfProducer()
        controller = _controller(repo=repo, ff=ff)

        result = controller.event_actual_or_lookup(stored.id)

        assert ff.lookups == []
        assert result is not None and result.id == stored.id


# ---- 3. nhập tay (§6.4) ---------------------------------------------------------


class TestManualEntryValidation:
    def test_missing_kind_is_reported_and_nothing_is_written(self):
        repo = FakeRepository()
        controller = _controller(repo=repo)

        result = controller.add_user_note(
            kind=None,
            published_utc="2026-09-22T10:00:00Z",
            content="Fed giữ nguyên lãi suất",
            currencies=["USD"],
        )

        assert result == UserNoteResult(errors=(UserNoteFieldError("kind", "missing"),))
        assert result.ok is False
        assert repo.calls == []

    def test_automatic_kind_is_rejected_not_rewritten(self):
        repo = FakeRepository()
        controller = _controller(repo=repo)

        result = controller.add_user_note(
            kind="headline",
            published_utc="2026-09-22T10:00:00Z",
            content="Tin nhập tay",
            currencies=["USD"],
        )

        assert result.errors == (UserNoteFieldError("kind", "not_manual_note"),)
        assert repo.calls == []

    def test_missing_content_is_reported(self):
        repo = FakeRepository()
        controller = _controller(repo=repo)

        result = controller.add_user_note(
            kind="user_note",
            published_utc="2026-09-22T10:00:00Z",
            content="   ",
            currencies=["USD"],
        )

        assert result.errors == (UserNoteFieldError("content", "missing"),)
        assert repo.calls == []

    def test_missing_publish_time_is_reported(self):
        repo = FakeRepository()
        controller = _controller(repo=repo)

        result = controller.add_user_note(
            kind="user_note",
            published_utc=None,
            content="Tin nhập tay",
            currencies=["USD"],
        )

        assert result.errors == (UserNoteFieldError("published_utc", "missing"),)
        assert repo.calls == []

    def test_unparsable_publish_time_is_reported(self):
        repo = FakeRepository()
        controller = _controller(repo=repo)

        result = controller.add_user_note(
            kind="user_note",
            published_utc="hôm qua lúc 3 giờ",
            content="Tin nhập tay",
            currencies=["USD"],
        )

        assert result.errors == (UserNoteFieldError("published_utc", "invalid_timestamp"),)
        assert repo.calls == []

    @pytest.mark.parametrize("currencies", [None, [], ["  "], "USD", 42])
    def test_currency_field_must_carry_at_least_one_code(self, currencies):
        repo = FakeRepository()
        controller = _controller(repo=repo)

        result = controller.add_user_note(
            kind="user_note",
            published_utc="2026-09-22T10:00:00Z",
            content="Tin nhập tay",
            currencies=currencies,
        )

        assert [error.field for error in result.errors] == ["currencies"]
        assert result.errors[0].reason in ("missing", "invalid_currency")
        assert repo.calls == []

    def test_invalid_impact_hint_is_reported(self):
        repo = FakeRepository()
        controller = _controller(repo=repo)

        result = controller.add_user_note(
            kind="user_note",
            published_utc="2026-09-22T10:00:00Z",
            content="Tin nhập tay",
            currencies=["USD"],
            impact_hint="extreme",
        )

        assert result.errors == (UserNoteFieldError("impact_hint", "invalid_impact_hint"),)
        assert repo.calls == []

    def test_every_missing_field_is_reported_together(self):
        repo = FakeRepository()
        controller = _controller(repo=repo)

        result = controller.add_user_note(
            kind=None, published_utc=None, content=None, currencies=None
        )

        assert {error.field for error in result.errors} == {
            "kind",
            "published_utc",
            "content",
            "currencies",
        }
        assert repo.calls == []


class TestManualEntryWrite:
    def test_valid_draft_writes_a_user_note(self, tmp_path):
        repo = _repo(tmp_path)
        controller = _controller(repo=repo)

        result = controller.add_user_note(
            kind="user_note",
            published_utc=datetime(2026, 9, 22, 10, 30, tzinfo=UTC),
            content="  Fed hạ lãi suất 25 điểm  ",
            currencies=["USD"],
        )

        assert result.ok and (result.inserted, result.updated) == (1, 0)
        assert result.run_id is not None
        rows = _rows(tmp_path / "news.db")
        assert len(rows) == 1
        row = rows[0]
        assert row["kind"] == NewsItemKind.USER_NOTE.value
        assert row["source"] == NewsItemSource.USER.value
        assert row["title"] == "Fed hạ lãi suất 25 điểm"  # nội dung = tiêu đề (khai báo V2)
        assert row["content"] == "Fed hạ lãi suất 25 điểm"
        assert row["published_utc"] == "2026-09-22T10:30:00Z"
        assert row["currencies_json"] == '["USD"]'
        assert row["impact_hint"] is None
        assert row["url"] is None
        assert row["excluded"] == 0
        assert row["dedupe_key"] == hashlib.sha256(
            ("Fed hạ lãi suất 25 điểm|2026-09-22T10:30:00Z").encode("utf-8")
        ).hexdigest()  # công thức §4.3 (không url)

        listed = controller.items_in_range("2000-01-01T00:00:00Z")
        assert [item.kind for item in listed] == [NewsItemKind.USER_NOTE]
        assert listed[0].currencies == ["USD"]

    def test_manual_turn_logs_one_ingest_run(self, tmp_path):
        # §3 xếp đường nhập tay vào cột bộ sản xuất, §10: mọi lượt producer có
        # ingest_runs ⇒ producer `user`, status ok, items_written = số bản ghi.
        repo = _repo(tmp_path)
        controller = _controller(repo=repo)

        result = controller.add_user_note(
            kind="user_note",
            published_utc="2026-09-22T10:00:00Z",
            content="Ghi chú",
            currencies=["USD"],
        )

        runs = _rows(tmp_path / "news.db", "SELECT * FROM ingest_runs")
        assert len(runs) == 1
        assert runs[0]["producer"] == IngestProducer.USER.value
        assert runs[0]["status"] == IngestRunStatus.OK.value
        assert runs[0]["items_written"] == 1
        assert runs[0]["error_type"] is None
        assert result.run_id == runs[0]["id"]

    def test_rejected_draft_logs_no_run(self, tmp_path):
        repo = _repo(tmp_path)
        controller = _controller(repo=repo)

        result = controller.add_user_note(
            kind=None, published_utc=None, content=None, currencies=None
        )

        assert result.ok is False and result.run_id is None
        assert _rows(tmp_path / "news.db", "SELECT * FROM ingest_runs") == []
        assert _rows(tmp_path / "news.db") == []

    def test_optional_fields_are_stored(self, tmp_path):
        repo = _repo(tmp_path)
        controller = _controller(repo=repo)

        controller.add_user_note(
            kind="user_note",
            published_utc="2026-09-22T11:00:00+07:00",
            content="ECB phát tín hiệu",
            currencies=["EUR", "USD"],
            url="https://example.com/ecb",
            impact_hint="high",
        )

        row = _rows(tmp_path / "news.db")[0]
        assert row["published_utc"] == "2026-09-22T04:00:00Z"  # quy về UTC
        assert row["currencies_json"] == '["EUR", "USD"]'
        assert row["url"] == "https://example.com/ecb"
        assert row["impact_hint"] == "high"
        assert row["dedupe_key"] == hashlib.sha256(b"https://example.com/ecb").hexdigest()

    def test_identical_note_upserts_instead_of_duplicating(self, tmp_path):
        repo = _repo(tmp_path)
        controller = _controller(repo=repo)
        draft = {
            "kind": "user_note",
            "published_utc": "2026-09-22T12:00:00Z",
            "content": "Cùng một ghi chú",
            "currencies": ["USD"],
        }

        first = controller.add_user_note(**draft)
        second = controller.add_user_note(**draft)

        assert (first.inserted, first.updated) == (1, 0)
        assert (second.inserted, second.updated) == (0, 1)
        assert len(_rows(tmp_path / "news.db")) == 1


class TestExclusionAndDeletion:
    def test_exclusion_applies_to_manual_and_automatic_items(self, tmp_path):
        repo = _repo(tmp_path)
        auto = _auto_item()
        repo.upsert_items([auto])
        auto_id = _rows(tmp_path / "news.db", "SELECT id FROM news_items WHERE kind='headline'")[0]["id"]
        controller = _controller(repo=repo)
        controller.add_user_note(
            kind="user_note",
            published_utc="2026-09-22T10:00:00Z",
            content="Ghi chú",
            currencies=["USD"],
        )
        note_id = _rows(tmp_path / "news.db", "SELECT id FROM news_items WHERE kind='user_note'")[0]["id"]

        assert controller.set_excluded(auto_id, True) == 1
        assert controller.set_excluded(note_id, True) == 1

        assert controller.items_in_range("2000-01-01T00:00:00Z") == []
        flagged = controller.items_in_range("2000-01-01T00:00:00Z", exclude_flagged=False)
        assert {item.excluded for item in flagged} == {True}
        # Tin tự động giữ nguyên provenance — chỉ cờ excluded đổi (không xóa).
        auto_rows = _rows(tmp_path / "news.db", "SELECT * FROM news_items WHERE kind='headline'")
        assert len(auto_rows) == 1 and auto_rows[0]["source"] == "google_news_rss"

    def test_delete_only_removes_manual_notes(self, tmp_path):
        repo = _repo(tmp_path)
        repo.upsert_items([_auto_item()])
        auto_id = _rows(tmp_path / "news.db")[0]["id"]
        controller = _controller(repo=repo)
        controller.add_user_note(
            kind="user_note",
            published_utc="2026-09-22T10:00:00Z",
            content="Ghi chú",
            currencies=["USD"],
        )
        note_id = _rows(tmp_path / "news.db", "SELECT id FROM news_items WHERE kind='user_note'")[0]["id"]

        assert controller.delete_user_note(auto_id) == 0  # tin tự động: giữ provenance
        assert controller.delete_user_note(note_id) == 1
        remaining = _rows(tmp_path / "news.db")
        assert [row["id"] for row in remaining] == [auto_id]


# ---- 4. uỷ quyền đọc (§3 vai trò, hợp đồng §8) ----------------------------------


class TestReadDelegation:
    def test_reads_are_delegated_verbatim(self):
        repo = FakeRepository()
        controller = _controller(repo=repo)
        now = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)

        assert controller.events_in_range("a", "b", ["USD"], False) is repo.events
        assert controller.events_pending_actual(now) is repo.pending
        assert controller.event_actual_or_lookup(7) is repo.event
        assert controller.items_in_range("a", "b", ["user_note"], ["USD"], False) is repo.items
        assert controller.latest_rates(["USD"]) is repo.rates
        assert controller.store_state() is repo.state

        assert repo.calls == [
            ("events_in_range", ("a", "b", ["USD"], False), {}),
            ("events_pending_actual", (now,), {}),
            ("event_actual_or_lookup", (7,), {}),
            ("items_in_range", ("a", "b", ["user_note"], ["USD"], False), {}),
            ("latest_rates", (["USD"],), {}),
            ("store_state", (), {}),
        ]

    def test_delegated_values_are_domain_models_not_dicts(self):
        repo = FakeRepository()
        repo.rates = [
            CurrencyRateTrend(
                currency="USD",
                latest=RateObservation(
                    currency="USD",
                    rate=5.5,
                    observed_at="2026-06-15",
                    source=RateSource.FRED,
                    fetched_at="2026-06-16T00:00:00Z",
                ),
                previous=None,
                trend=RateTrend.HOLD,
            )
        ]
        controller = _controller(repo=repo)

        rates = controller.latest_rates(["USD"])

        assert isinstance(rates[0], CurrencyRateTrend)
        assert isinstance(rates[0].latest, RateObservation)
        assert isinstance(controller.store_state(), StoreState)

    def test_verdict_history_is_not_exposed_in_this_batch(self):
        """Đường AI (kể cả lịch sử verdict) thuộc L3.5 — chưa mở ở L2.7."""
        controller = _controller()
        assert not hasattr(controller, "verdicts_for")


# ---- 5. worker (bọc concurrency, không logic nghiệp vụ) -------------------------


@pytest.fixture(scope="module", autouse=True)
def _qt_app():
    """QObject/QTimer cần một instance ứng dụng (khuôn Qt của repo: offscreen,
    tạo một lần và tái dùng nếu module khác đã tạo)."""
    from PyQt6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


class TestNewsWorker:
    def test_timer_intervals_come_from_the_controller_cadence(self):
        controller = FakeController(rss_poll_interval_minutes=15, rates_refresh_hours=6)

        worker = NewsWorker(controller)

        assert worker.news_interval_minutes == 15
        assert worker.rates_interval_hours == 6

    def test_start_and_stop_toggle_both_timers(self):
        worker = NewsWorker(FakeController())

        worker.start()
        assert worker._news_timer.isActive() and worker._rates_timer.isActive()

        worker.stop()
        assert not worker._news_timer.isActive() and not worker._rates_timer.isActive()

    def test_news_round_emits_the_result_returned_by_the_controller(self):
        controller = FakeController()
        worker = NewsWorker(controller)
        seen: list[object] = []
        worker.news_succeeded.connect(seen.append)
        worker.news_failed.connect(lambda message: seen.append(message))

        worker.run_news_round()

        assert controller.poll_calls == 1
        assert seen == [controller.news_result]
        assert worker.state == WorkerState.FINISHED

    def test_rates_round_emits_the_result_returned_by_the_controller(self):
        controller = FakeController()
        worker = NewsWorker(controller)
        seen: list[object] = []
        worker.rates_succeeded.connect(seen.append)

        worker.run_rates_round()

        assert controller.refresh_calls == 1
        assert seen == [controller.rates_result]
        assert worker.state == WorkerState.FINISHED

    def test_failing_round_reports_the_reason_and_never_succeeds(self):
        controller = FakeController()
        controller.news_error = RuntimeError("RSS không phản hồi")
        controller.rates_error = RuntimeError("FRED không phản hồi")
        worker = NewsWorker(controller)
        succeeded: list[object] = []
        failed: list[str] = []
        worker.news_succeeded.connect(succeeded.append)
        worker.news_failed.connect(failed.append)
        worker.rates_succeeded.connect(succeeded.append)
        worker.rates_failed.connect(failed.append)

        worker.run_news_round()
        assert succeeded == [] and failed == ["RSS không phản hồi"]
        assert worker.state == WorkerState.FAILED

        worker.run_rates_round()
        assert succeeded == [] and failed == ["RSS không phản hồi", "FRED không phản hồi"]
        assert worker.state == WorkerState.FAILED

    def test_worker_carries_no_domain_logic(self):
        """§3: worker chỉ bọc concurrency — chỉ import PyQt + controller + trạng
        thái worker, không chạm repository/producer/mô hình miền."""
        from workers import news_worker as worker_module

        tree = ast.parse(inspect.getsource(worker_module))
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
            elif isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
        modules.discard("__future__")

        assert modules == {"PyQt6.QtCore", "controllers.news_controller", "workers.base_worker"}


# ---- 6. đăng ký DI (điểm chạm additive app_controller) --------------------------


class TestAppControllerRegistration:
    def test_news_controller_property_is_lazy_and_cached(self, monkeypatch):
        app = AppController()
        assert app._news_controller is None  # lazy: chưa dựng khi mở app

        created: list[NewsController] = []

        def _fake_factory() -> NewsController:
            controller = NewsController.__new__(NewsController)
            created.append(controller)
            return controller

        monkeypatch.setattr(app_controller_module, "NewsController", _fake_factory)

        first = app.news_controller
        second = app.news_controller

        assert first is second
        assert created == [first]

    def test_module_binds_the_real_news_controller_class(self):
        from controllers.news_controller import NewsController as RealNewsController

        assert app_controller_module.NewsController is RealNewsController
