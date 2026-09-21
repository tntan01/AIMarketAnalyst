"""NewsRepository READ covenant - contract test C4 (plan lô L2.2, contract §8/§14).

This is the contract test that the two wiring batches (Dashboard, macro) will
reuse (contract §14: "kiểm thử hợp đồng (C4) ... xanh nguyên trạng khi nội bộ
repository thay đổi").  It therefore pins only the *signature* and the
observable *output semantics* of the seven read methods of contract §8 —
never an internal intermediate (SQL text, private helpers, row mappings).
Any direct SQL below is fixture *setup* only, never an assertion target.

Coverage required by the batch: signatures of all 7 read methods; events window
bounds/currency/include_non_impact/order/read-time status; pending-actual set +
grace boundary; the four branches of ``event_actual_or_lookup`` with a typed
fake lookup; items window/open-upper/kinds/currencies/excluded/decode/order;
``latest_rates`` cross-checked against ``core/rate_trend`` (no threshold copied
into the test); ``store_state`` fresh/degraded/unavailable incl. ``partial``
counts and ``failed`` does not; verdicts filter/order/limit + JSON decode; and
the no-network-import scan of the module.
"""

from __future__ import annotations

import ast
import inspect
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import services.news_repository as news_repository_module
from config.paths import PROJECT_ROOT
from core.news_freshness import classify_event_status
from core.news_models import (
    CalendarEvent,
    EventImpact,
    EventSource,
    EventStatus,
    ImpactHint,
    IngestProducer,
    IngestRun,
    IngestRunStatus,
    NewsItem,
    NewsItemKind,
    NewsItemSource,
    RateObservation,
    RateSource,
    StoreStatus,
    TrendVerdict,
    VerdictConfidence,
    VerdictDirection,
    VerdictHorizon,
    VerdictScopeType,
)
from core.news_policy import load_news_policy
from core.rate_trend import RateTrend, derive_rate_trend
from services.news_repository import CurrencyRateTrend, NewsRepository

NEWS_MIGRATIONS_DIR = PROJECT_ROOT / "data" / "migrations" / "news"


# ---- fixture scaffolding (setup only - temp DB, never %APPDATA%) ---------------


def _repo(tmp_path: Path, lookup=None) -> NewsRepository:
    return NewsRepository(
        db_path=tmp_path / "news.db",
        migrations_dir=NEWS_MIGRATIONS_DIR,
        lookup=lookup,
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def _grace_and_max_age():
    policy = load_news_policy()
    return (
        timedelta(minutes=policy.event_stale_grace_minutes),
        timedelta(hours=policy.ingest_freshness_hours),
    )


def _event(
    dedupe: str,
    *,
    actual: str | None = None,
    source: EventSource = EventSource.FF_JSON,
    impact: EventImpact = EventImpact.HIGH,
    event_time: str = "2026-09-21T08:00:00Z",
    title: str = "CPI press conference",
    currency: str = "USD",
) -> CalendarEvent:
    return CalendarEvent(
        day_key=event_time[:10],
        event_time_utc=event_time,
        currency=currency,
        title=title,
        impact=impact,
        status=EventStatus.SCHEDULED,
        source=source,
        dedupe_key=dedupe,
        fetched_at="2026-09-21T01:00:00Z",
        forecast="0.3%",
        previous="0.2%",
        actual=actual,
    )


def _item(
    dedupe: str,
    *,
    kind: NewsItemKind = NewsItemKind.HEADLINE,
    source: NewsItemSource = NewsItemSource.GOOGLE_NEWS_RSS,
    title: str = "Fed holds rates steady",
    currencies: list[str] | None = None,
    published_utc: str = "2026-09-21T07:00:00Z",
) -> NewsItem:
    return NewsItem(
        kind=kind,
        source=source,
        title=title,
        published_utc=published_utc,
        currencies=currencies if currencies is not None else ["USD"],
        dedupe_key=dedupe,
        fetched_at="2026-09-21T01:00:00Z",
        content="body" if kind == NewsItemKind.USER_NOTE else None,
        impact_hint=ImpactHint.HIGH if kind == NewsItemKind.USER_NOTE else None,
    )


def _rate(
    currency: str,
    observed_at: str,
    source: RateSource = RateSource.FRED,
    rate: float = 5.25,
) -> RateObservation:
    return RateObservation(
        currency=currency,
        rate=rate,
        observed_at=observed_at,
        source=source,
        fetched_at="2026-09-21T01:00:00Z",
    )


def _verdict(
    created_at: str,
    *,
    scope_type: VerdictScopeType = VerdictScopeType.PAIR,
    scope_value: str = "EUR/USD",
) -> TrendVerdict:
    return TrendVerdict(
        created_at=created_at,
        scope_type=scope_type,
        scope_value=scope_value,
        horizon=VerdictHorizon.SHORT,
        direction=VerdictDirection.BULLISH,
        confidence=VerdictConfidence.MEDIUM,
        rationale="Đà tăng ngắn hạn",
        evidence_item_ids=[3, 7],
        input_snapshot={"window_days": 7, "events": 2, "items": 1},
        provider="sk-oracle",
        model="deepseek",
        prompt_hash="hash-1",
    )


def _run(
    finished_at: str,
    *,
    producer: IngestProducer = IngestProducer.RSS,
    status: IngestRunStatus = IngestRunStatus.OK,
) -> IngestRun:
    return IngestRun(
        producer=producer,
        started_at="2026-09-21T01:00:00Z",
        finished_at=finished_at,
        status=status,
        items_written=2,
    )


def _insert_event_raw(
    db_path: Path,
    *,
    dedupe: str,
    event_time: str,
    actual: str | None = None,
    impact: str = "high",
    status: str = "scheduled",
    currency: str = "USD",
) -> None:
    """Fixture-insert a row with an EXPLICIT stored ``status`` — used to prove
    read-time re-classification ignores the stored column."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO news_events ("
            "day_key,event_time_utc,currency,title,impact,forecast,previous,actual,"
            "actual_updated_at,status,source,dedupe_key,raw_json,fetched_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                event_time[:10],
                event_time,
                currency,
                "CPI press conference",
                impact,
                None,
                None,
                actual,
                None,
                status,
                "ff_json",
                dedupe,
                None,
                "2026-09-21T01:00:00Z",
            ),
        )
        conn.commit()
    finally:
        conn.close()


# ---- 1. pinned signatures (contract §8 — consumers compile against these) -------


class TestContractSignatures:
    def test_events_in_range_signature(self):
        sig = inspect.signature(NewsRepository.events_in_range)
        assert list(sig.parameters) == [
            "self", "from_utc", "to_utc", "currencies", "include_non_impact",
        ]
        assert sig.parameters["currencies"].default is None
        assert sig.parameters["include_non_impact"].default is True

    def test_events_pending_actual_signature(self):
        sig = inspect.signature(NewsRepository.events_pending_actual)
        assert list(sig.parameters) == ["self", "now"]
        assert sig.parameters["now"].default is inspect.Parameter.empty

    def test_event_actual_or_lookup_signature(self):
        sig = inspect.signature(NewsRepository.event_actual_or_lookup)
        assert list(sig.parameters) == ["self", "event_id"]

    def test_items_in_range_signature(self):
        sig = inspect.signature(NewsRepository.items_in_range)
        assert list(sig.parameters) == [
            "self", "from_utc", "to_utc", "kinds", "currencies", "exclude_flagged",
        ]
        assert sig.parameters["to_utc"].default is None
        assert sig.parameters["kinds"].default is None
        assert sig.parameters["currencies"].default is None
        assert sig.parameters["exclude_flagged"].default is True

    def test_latest_rates_signature(self):
        sig = inspect.signature(NewsRepository.latest_rates)
        assert list(sig.parameters) == ["self", "currencies"]

    def test_store_state_signature(self):
        assert list(inspect.signature(NewsRepository.store_state).parameters) == ["self"]

    def test_verdicts_for_signature(self):
        sig = inspect.signature(NewsRepository.verdicts_for)
        assert list(sig.parameters) == ["self", "scope_type", "scope_value", "limit"]
        assert sig.parameters["limit"].default is inspect.Parameter.empty


# ---- 2. events_in_range --------------------------------------------------------


class TestEventsInRange:
    def test_closed_bounds_and_ascending_order(self, tmp_path):
        repo = _repo(tmp_path)
        repo.upsert_events([
            _event("e1", event_time="2026-09-20T08:00:00Z"),
            _event("e2", event_time="2026-09-21T08:00:00Z"),
            _event("e3", event_time="2026-09-22T08:00:00Z"),
            _event("e0", event_time="2026-09-19T08:00:00Z"),
            _event("e4", event_time="2026-09-23T08:00:00Z"),
        ])
        result = repo.events_in_range(
            "2026-09-20T08:00:00Z", "2026-09-22T08:00:00Z"
        )
        assert isinstance(result, list)
        assert all(isinstance(e, CalendarEvent) for e in result)
        assert [e.dedupe_key for e in result] == ["e1", "e2", "e3"]
        times = [e.event_time_utc for e in result]
        assert times == sorted(times)

    def test_currency_filter_matches_any_currency(self, tmp_path):
        repo = _repo(tmp_path)
        repo.upsert_events([
            _event("usd", currency="USD"),
            _event("jpy", currency="JPY"),
        ])
        assert [e.dedupe_key for e in repo.events_in_range(
            "2026-09-21T00:00:00Z", "2026-09-21T23:59:59Z",
            currencies=["USD"],
        )] == ["usd"]
        assert [e.dedupe_key for e in repo.events_in_range(
            "2026-09-21T00:00:00Z", "2026-09-21T23:59:59Z",
            currencies=["JPY", "GBP"],
        )] == ["jpy"]
        assert len(repo.events_in_range(
            "2026-09-21T00:00:00Z", "2026-09-21T23:59:59Z", currencies=None
        )) == 2

    def test_include_non_impact_flag(self, tmp_path):
        repo = _repo(tmp_path)
        repo.upsert_events([
            _event("high", impact=EventImpact.HIGH),
            _event("non", impact=EventImpact.NON),
        ])
        window = ("2026-09-21T00:00:00Z", "2026-09-21T23:59:59Z")
        assert {e.dedupe_key for e in repo.events_in_range(*window)} == {"high", "non"}
        assert {e.dedupe_key for e in repo.events_in_range(
            *window, include_non_impact=False
        )} == {"high"}

    def test_status_reclassified_at_read_not_the_stored_column(self, tmp_path):
        # A row stored as 'scheduled' but already past grace+actual-less must be
        # returned as 'stale' — status is classified at read time (§6.5, B4).
        repo = _repo(tmp_path)
        _insert_event_raw(
            repo_db_file(tmp_path),
            dedupe="past",
            event_time="2020-01-01T08:00:00Z",
            actual=None,
            status="scheduled",
        )
        _insert_event_raw(
            repo_db_file(tmp_path),
            dedupe="with-actual",
            event_time="2020-01-01T08:00:00Z",
            actual="1.2",
            status="scheduled",
        )
        _insert_event_raw(
            repo_db_file(tmp_path),
            dedupe="future",
            event_time="2100-01-01T08:00:00Z",
            actual=None,
            status="scheduled",
        )
        result = repo.events_in_range("2020-01-01T00:00:00Z", "2100-01-01T23:59:59Z")
        by_key = {e.dedupe_key: e.status.value for e in result}
        assert by_key["past"] == "stale"
        assert by_key["with-actual"] == "released"
        assert by_key["future"] == "scheduled"


def repo_db_file(tmp_path) -> Path:
    return tmp_path / "news.db"


# ---- 3. events_pending_actual ---------------------------------------------------


class TestEventsPendingActual:
    def test_pending_actual_set_and_grace_boundary(self, tmp_path):
        repo = _repo(tmp_path)
        now = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
        grace, _ = _grace_and_max_age()

        repo.upsert_events([
            _event("overdue", event_time=_iso(now - grace - timedelta(minutes=5))),
            _event("at-boundary", event_time=_iso(now - grace)),
            _event("future", event_time=_iso(now + timedelta(days=1))),
            _event(
                "has-actual",
                event_time=_iso(now - grace - timedelta(minutes=5)),
                actual="1.2",
            ),
            _event(
                "non-impact",
                event_time=_iso(now - grace - timedelta(minutes=5)),
                impact=EventImpact.NON,
            ),
        ])

        pending = repo.events_pending_actual(now)
        assert isinstance(pending, list)
        assert all(isinstance(e, CalendarEvent) for e in pending)
        assert [e.dedupe_key for e in pending] == ["overdue"]
        assert pending[0].status == EventStatus.STALE

    def test_boundary_is_strictly_past(self, tmp_path):
        repo = _repo(tmp_path)
        now = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
        grace, _ = _grace_and_max_age()
        past = _event("past", event_time=_iso(now - grace - timedelta(seconds=60)))
        at = _event("at", event_time=_iso(now - grace))
        repo.upsert_events([past, at])
        # đối chiếu chính classify_event_status (repo không tự chứa logic)
        assert classify_event_status(past, now, grace) == EventStatus.STALE
        assert classify_event_status(at, now, grace) == EventStatus.SCHEDULED
        assert [e.dedupe_key for e in repo.events_pending_actual(now)] == ["past"]


# ---- 4. event_actual_or_lookup --------------------------------------------------


class TestEventActualOrLookup:
    def _fake_lookup(self, result: CalendarEvent | None):
        calls: list[int] = []

        def lookup(event_id: int) -> CalendarEvent | None:
            calls.append(event_id)
            return result

        return lookup, calls

    def test_unknown_id_returns_none(self, tmp_path):
        repo = _repo(tmp_path)
        assert repo.event_actual_or_lookup(999_999) is None

    def test_non_stale_event_never_triggers_lookup(self, tmp_path):
        lookup, calls = self._fake_lookup(
            _event("fresh", actual="1.2", event_time="2020-01-01T08:00:00Z")
        )
        repo = _repo(tmp_path, lookup=lookup)
        repo.upsert_events([_event("e1", event_time="2100-01-01T08:00:00Z")])
        event = repo.event_actual_or_lookup(event_id_for(repo, "e1"))
        assert event.dedupe_key == "e1"
        assert calls == []

    def test_stale_event_triggers_lookup_exactly_once(self, tmp_path):
        fresh_result = _event("e1", event_time="2100-01-01T08:00:00Z", actual="9.9")
        lookup, calls = self._fake_lookup(fresh_result)
        repo = _repo(tmp_path, lookup=lookup)
        _insert_event_raw(
            repo_db_file(tmp_path), dedupe="e1", event_time="2020-01-01T08:00:00Z"
        )
        result = repo.event_actual_or_lookup(event_id_for(repo, "e1"))
        assert calls == [event_id_for(repo, "e1")]
        assert result == fresh_result

    def test_lookup_unplugged_returns_stored_event(self, tmp_path):
        repo = _repo(tmp_path)  # no lookup wired
        _insert_event_raw(
            repo_db_file(tmp_path), dedupe="e1", event_time="2020-01-01T08:00:00Z"
        )
        event = repo.event_actual_or_lookup(event_id_for(repo, "e1"))
        assert event is not None
        assert event.dedupe_key == "e1"

    def test_module_has_no_network_imports(self):
        source = Path(news_repository_module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        banned = {"urllib", "requests", "http", "socket", "aiohttp", "httpx"}
        assert not (imported & banned), sorted(imported & banned)


def event_id_for(repo: NewsRepository, dedupe: str) -> int:
    conn = sqlite3.connect(repo.db_path)
    try:
        return int(conn.execute(
            "SELECT id FROM news_events WHERE dedupe_key = ?", (dedupe,)
        ).fetchone()[0])
    finally:
        conn.close()


# ---- 5. items_in_range ----------------------------------------------------------


class TestItemsInRange:
    def _seed(self, repo: NewsRepository) -> None:
        repo.upsert_items([
            _item("i1", published_utc="2026-09-20T07:00:00Z"),
            _item(
                "i2",
                kind=NewsItemKind.STATEMENT,
                source=NewsItemSource.FXSTREET_RSS,
                currencies=["JPY", "EUR"],
                published_utc="2026-09-21T07:00:00Z",
            ),
            _item("i3", published_utc="2026-09-22T07:00:00Z"),
            _item("i4", currencies=["GBP"], published_utc="2026-08-10T07:00:00Z"),
        ])
        # exclude i3 via the public write path (§6.4)
        conn = sqlite3.connect(repo.db_path)
        try:
            i3_id = conn.execute(
                "SELECT id FROM news_items WHERE dedupe_key='i3'"
            ).fetchone()[0]
        finally:
            conn.close()
        repo.set_excluded(i3_id, True)

    def test_open_upper_bound_and_flagged_excluded_by_default(self, tmp_path):
        repo = _repo(tmp_path)
        self._seed(repo)
        result = repo.items_in_range("2026-09-20T00:00:00Z")
        assert isinstance(result, list)
        assert all(isinstance(i, NewsItem) for i in result)
        assert [i.dedupe_key for i in result] == ["i1", "i2"]
        times = [i.published_utc for i in result]
        assert times == sorted(times)

    def test_exclude_flagged_false_includes_excluded(self, tmp_path):
        repo = _repo(tmp_path)
        self._seed(repo)
        result = repo.items_in_range(
            "2026-09-20T00:00:00Z", exclude_flagged=False
        )
        assert {i.dedupe_key for i in result} == {"i1", "i2", "i3"}

    def test_kinds_filter_matches_any(self, tmp_path):
        repo = _repo(tmp_path)
        self._seed(repo)
        result = repo.items_in_range(
            "2026-09-01T00:00:00Z", kinds=["statement"]
        )
        assert [i.dedupe_key for i in result] == ["i2"]

    def test_currencies_filter_on_decoded_list(self, tmp_path):
        repo = _repo(tmp_path)
        self._seed(repo)
        result = repo.items_in_range(
            "2026-09-01T00:00:00Z", currencies=["JPY"]
        )
        assert [i.dedupe_key for i in result] == ["i2"]
        assert result[0].currencies == ["JPY", "EUR"]
        both = repo.items_in_range(
            "2026-09-01T00:00:00Z", currencies=["USD", "EUR"]
        )
        assert {i.dedupe_key for i in both} == {"i1", "i2"}

    def test_window_excludes_out_of_range(self, tmp_path):
        repo = _repo(tmp_path)
        self._seed(repo)
        result = repo.items_in_range("2026-09-20T00:00:00Z", "2026-09-21T23:59:59Z")
        assert [i.dedupe_key for i in result] == ["i1", "i2"]


# ---- 6. latest_rates ------------------------------------------------------------


class TestLatestRates:
    def _seed(self, repo: NewsRepository) -> None:
        repo.add_rate_observations([
            _rate("USD", "2026-09-19", rate=5.25),
            _rate("USD", "2026-09-20", rate=5.50),
            _rate("JPY", "2026-09-20", rate=0.50),
            _rate("AUD", "2026-09-19", rate=5.50),
            _rate("AUD", "2026-09-20", rate=5.25),
            _rate("CAD", "2026-09-19", rate=5.25),
            _rate("CAD", "2026-09-20", rate=5.30),
            _rate(
                "EUR", "2026-09-19", source=RateSource.CONFIG_FALLBACK, rate=5.00
            ),
            _rate(
                "EUR", "2026-09-20", source=RateSource.CONFIG_FALLBACK, rate=6.00
            ),
        ])

    def test_trend_matches_core_derive_for_every_currency(self, tmp_path):
        repo = _repo(tmp_path)
        self._seed(repo)
        entries = repo.latest_rates(["USD", "JPY", "AUD", "CAD", "EUR", "GBP"])
        assert isinstance(entries, list)
        assert all(isinstance(e, CurrencyRateTrend) for e in entries)
        assert [e.currency for e in entries] == ["USD", "JPY", "AUD", "CAD", "EUR"]

        # Counter-part computed straight from the core function with the SAME
        # observations the test seeded — no threshold is copied into the test.
        expected = {
            "USD": derive_rate_trend(_rate("USD", "2026-09-20", rate=5.50), _rate("USD", "2026-09-19", rate=5.25)),
            "JPY": derive_rate_trend(_rate("JPY", "2026-09-20", rate=0.50), None),
            "AUD": derive_rate_trend(_rate("AUD", "2026-09-20", rate=5.25), _rate("AUD", "2026-09-19", rate=5.50)),
            "CAD": derive_rate_trend(_rate("CAD", "2026-09-20", rate=5.30), _rate("CAD", "2026-09-19", rate=5.25)),
            "EUR": derive_rate_trend(_rate("EUR", "2026-09-20", source=RateSource.CONFIG_FALLBACK, rate=6.00), _rate("EUR", "2026-09-19", source=RateSource.CONFIG_FALLBACK, rate=5.00)),
        }
        for entry in entries:
            assert entry.trend == expected[entry.currency]
            assert isinstance(entry.latest, RateObservation)
            if entry.currency == "JPY":
                assert entry.previous is None

        # config_fallback never leaves HOLD (its represented behavior)
        eur = next(e for e in entries if e.currency == "EUR")
        assert eur.trend == RateTrend.HOLD
        # no observation at all -> no entry (B4)
        assert all(e.currency != "GBP" for e in entries)
        # latest is the newest observation
        usd = next(e for e in entries if e.currency == "USD")
        assert usd.latest.rate == 5.50
        assert usd.previous.rate == 5.25


# ---- 7. store_state -------------------------------------------------------------


class TestStoreState:
    def test_never_ingested_is_unavailable(self, tmp_path):
        state = _repo(tmp_path).store_state()
        from core.news_models import StoreState
        assert isinstance(state, StoreState)
        assert state.events_state == StoreStatus.UNAVAILABLE
        assert state.items_state == StoreStatus.UNAVAILABLE
        assert state.rates_state == StoreStatus.UNAVAILABLE
        assert state.events_last_success_at is None
        assert state.items_last_success_at is None
        assert state.rates_last_success_at is None

    def test_ok_and_partial_count_failed_does_not(self, tmp_path):
        repo = _repo(tmp_path)
        repo.record_run(_run(_utc_now(), producer=IngestProducer.FF_CRAWLER, status=IngestRunStatus.OK))
        repo.record_run(_run(_utc_now(), producer=IngestProducer.RSS, status=IngestRunStatus.PARTIAL))
        repo.record_run(_run(_utc_now(), producer=IngestProducer.FRED, status=IngestRunStatus.FAILED))
        state = repo.store_state()
        assert state.events_state == StoreStatus.FRESH
        assert state.items_state == StoreStatus.FRESH
        assert state.rates_state == StoreStatus.UNAVAILABLE
        assert state.events_last_success_at is not None
        assert state.items_last_success_at is not None
        assert state.rates_last_success_at is None

    def test_past_freshness_window_is_degraded(self, tmp_path):
        _, max_age = _grace_and_max_age()
        now = datetime.now(timezone.utc)
        overdue = _iso(now - max_age - timedelta(minutes=30))
        repo = _repo(tmp_path)
        repo.record_run(_run(overdue, producer=IngestProducer.FF_CRAWLER))
        state = repo.store_state()
        assert state.events_state == StoreStatus.DEGRADED
        assert state.events_last_success_at is not None


# ---- 8. verdicts_for ------------------------------------------------------------


class TestVerdictsFor:
    def test_newest_first_limit_and_scope(self, tmp_path):
        repo = _repo(tmp_path)
        repo.add_verdicts([
            _verdict("2026-09-21T10:00:00Z"),
            _verdict("2026-09-22T10:00:00Z"),
            _verdict(
                "2026-09-23T10:00:00Z",
                scope_type=VerdictScopeType.CURRENCY,
                scope_value="JPY",
            ),
        ])
        result = repo.verdicts_for(VerdictScopeType.PAIR, "EUR/USD", 10)
        assert isinstance(result, list)
        assert all(isinstance(v, TrendVerdict) for v in result)
        assert [v.created_at for v in result] == [
            "2026-09-22T10:00:00Z", "2026-09-21T10:00:00Z",
        ]
        # JSON columns decoded into typed values
        assert all(isinstance(v.evidence_item_ids, list) for v in result)
        assert result[0].evidence_item_ids == [3, 7]
        assert result[0].input_snapshot == {"window_days": 7, "events": 2, "items": 1}

    def test_limit_caps_rows(self, tmp_path):
        repo = _repo(tmp_path)
        repo.add_verdicts([
            _verdict("2026-09-21T10:00:00Z"),
            _verdict("2026-09-22T10:00:00Z"),
        ])
        limited = repo.verdicts_for(VerdictScopeType.PAIR, "EUR/USD", 1)
        assert len(limited) == 1
        assert limited[0].created_at == "2026-09-22T10:00:00Z"

    def test_scope_is_exact(self, tmp_path):
        repo = _repo(tmp_path)
        repo.add_verdicts([_verdict("2026-09-21T10:00:00Z")])
        assert repo.verdicts_for(VerdictScopeType.PAIR, "GBP/USD", 10) == []
        assert len(repo.verdicts_for(VerdictScopeType.CURRENCY, "EUR/USD", 10)) == 0