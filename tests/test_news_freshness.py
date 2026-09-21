"""Pure tests for the News data-status classifier (contract §6.5, plan lô L1.4).

``core/news_freshness.py`` is the registered single owner of the status
classification (contract §11b).  Its contract, verified here:

* ``classify_event_status`` walks the time/grace boundary table of §6.5: an
  impact-relevant event strictly past ``event_time_utc + grace`` with a NULL
  actual is ``stale``; at/before the deadline it stays ``scheduled`` (only
  "passed" events are stale); an event with an actual is always ``released``;
  an ``impact == non`` event with a NULL actual is never ``stale``;
* ``classify_store_state`` reports one ``StoreStatus`` per signal in a single
  call - ``fresh`` (last success within ``max_age``, boundary included),
  ``degraded`` (had a success but past ``max_age``), ``unavailable`` (never
  had one - missing producer key) - with the ``*_last_success_at`` fields
  carrying the exact last successful ingest time (``None`` only when never);
* the producer-only signal registry of §6 is honored: ``ff_crawler`` →
  ``events``, ``rss`` → ``items``, ``fred`` → ``rates``; any other producer
  key (``user``, ``on_demand_lookup``) in the mapping is ignored;
* return values are the existing frozen enum members / typed ``StoreState``
  of ``core/news_models.py`` - never bare strings (C3, L3);
* the module stays pure and layer-clean (L2/L1): ``now``/``grace``/``max_age``
  are parameters with no defaults (B5 - no fabricated number), and the source
  imports nothing outside stdlib + ``core.news_models``.
"""

from __future__ import annotations

import ast
import inspect
import typing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.news_freshness import classify_event_status, classify_store_state
from core.news_models import (
    CalendarEvent,
    EventImpact,
    EventSource,
    EventStatus,
    IngestProducer,
    StoreState,
    StoreStatus,
)

_GRACE = timedelta(minutes=15)
_MAX_AGE = timedelta(hours=2)
_NOW = datetime(2026, 9, 21, 12, 0, 0, tzinfo=timezone.utc)
_NEWS_FRESHNESS_PY = (
    Path(__file__).resolve().parents[1] / "core" / "news_freshness.py"
)

# Event at 08:00Z -> grace deadline 08:15Z (now is irrelevant to the classifier).
_EVENT_TIME = "2026-09-21T08:00:00Z"
_DEADLINE = datetime(2026, 9, 21, 8, 15, 0, tzinfo=timezone.utc)


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _event(
    *,
    impact: EventImpact = EventImpact.HIGH,
    actual: str | None = None,
    event_time: str = _EVENT_TIME,
) -> CalendarEvent:
    return CalendarEvent(
        day_key="2026-09-21",
        event_time_utc=event_time,
        currency="USD",
        title="FOMC Statement",
        impact=impact,
        status=EventStatus.SCHEDULED,
        source=EventSource.FF_JSON,
        dedupe_key="evt-test",
        fetched_at="2026-09-21T01:00:00Z",
        actual=actual,
    )


class TestClassifyEventStatus:
    """Time/grace boundary table of §6.5 - pinned against the deadline 08:15Z."""

    @pytest.mark.parametrize(
        ("now_iso", "actual", "impact", "expected"),
        [
            # Before the grace deadline with a NULL actual -> scheduled.
            ("2026-09-21T08:10:00Z", None, EventImpact.HIGH, EventStatus.SCHEDULED),
            # Exactly AT the deadline is NOT "passed" -> still scheduled.
            ("2026-09-21T08:15:00Z", None, EventImpact.HIGH, EventStatus.SCHEDULED),
            # Strictly past the deadline with a NULL actual -> stale.
            ("2026-09-21T08:15:01Z", None, EventImpact.HIGH, EventStatus.STALE),
            ("2026-09-21T09:00:00Z", None, EventImpact.HIGH, EventStatus.STALE),
            # An actual makes the event released regardless of the deadline.
            ("2026-09-21T09:00:00Z", "1.2%", EventImpact.HIGH, EventStatus.RELEASED),
            ("2026-09-21T08:10:00Z", "1.2%", EventImpact.HIGH, EventStatus.RELEASED),
            # impact == non is never stale, even past the deadline with NULL.
            ("2026-09-21T09:00:00Z", None, EventImpact.NON, EventStatus.SCHEDULED),
            ("2026-09-21T08:10:00Z", None, EventImpact.NON, EventStatus.SCHEDULED),
            ("2026-09-21T09:00:00Z", "1.2%", EventImpact.NON, EventStatus.RELEASED),
        ],
    )
    def test_time_grace_boundary_table(self, now_iso, actual, impact, expected):
        result = classify_event_status(
            _event(impact=impact, actual=actual),
            now=_utc(now_iso),
            grace=_GRACE,
        )
        assert result is expected  # identity: exact enum member, not a string
        assert isinstance(result, EventStatus)

    def test_exactly_at_grace_deadline_is_not_yet_passed(self):
        result = classify_event_status(_event(), now=_DEADLINE, grace=_GRACE)
        assert result is EventStatus.SCHEDULED
        assert result.value == "scheduled"

    def test_one_second_past_grace_deadline_is_stale(self):
        past = _DEADLINE + timedelta(seconds=1)
        result = classify_event_status(_event(), now=past, grace=_GRACE)
        assert result is EventStatus.STALE
        assert result.value == "stale"

    def test_actual_present_is_released_and_never_stale(self):
        event = _event(actual="0.8%")
        assert (
            classify_event_status(event, now=_DEADLINE + timedelta(hours=2), grace=_GRACE)
            is EventStatus.RELEASED
        )

    def test_non_impact_event_never_classified_stale(self):
        zero_impact = _event(impact=EventImpact.NON)
        far_past = _utc("2026-09-21T23:59:59Z")
        result = classify_event_status(zero_impact, now=far_past, grace=_GRACE)
        assert result is EventStatus.SCHEDULED
        assert result is not EventStatus.STALE

    def test_accepts_iso_with_explicit_utc_offset(self):
        event = _event(event_time="2026-09-21T08:00:00+00:00")
        result = classify_event_status(
            event, now=_DEADLINE + timedelta(seconds=1), grace=_GRACE
        )
        assert result is EventStatus.STALE

    def test_is_deterministic(self):
        now = _DEADLINE + timedelta(minutes=5)
        assert classify_event_status(_event(), now=now, grace=_GRACE) is EventStatus.STALE
        assert classify_event_status(_event(), now=now, grace=_GRACE) is EventStatus.STALE


class TestClassifyStoreState:
    """Fresh/degraded/unavailable per signal - one call covers all three.

    ``_NOW`` = 12:00Z, ``_MAX_AGE`` = 2h  ->  freshness window edge 10:00Z.
    """

    def test_three_signals_are_classified_independently_in_one_call(self):
        state = classify_store_state(
            {
                IngestProducer.FF_CRAWLER: _utc("2026-09-21T11:30:00Z"),  # fresh
                IngestProducer.RSS: _utc("2026-09-21T07:00:00Z"),  # degraded
                # no FRED key -> unavailable
            },
            now=_NOW,
            max_age=_MAX_AGE,
        )
        assert isinstance(state, StoreState)
        assert state.events_state is StoreStatus.FRESH
        assert state.items_state is StoreStatus.DEGRADED
        assert state.rates_state is StoreStatus.UNAVAILABLE
        assert state.events_last_success_at == _utc("2026-09-21T11:30:00Z").isoformat()
        assert state.items_last_success_at == _utc("2026-09-21T07:00:00Z").isoformat()
        assert state.rates_last_success_at is None

    def test_all_signals_fresh(self):
        state = classify_store_state(
            {
                IngestProducer.FF_CRAWLER: _utc("2026-09-21T11:30:00Z"),
                IngestProducer.RSS: _utc("2026-09-21T11:15:00Z"),
                IngestProducer.FRED: _utc("2026-09-21T11:00:00Z"),
            },
            now=_NOW,
            max_age=_MAX_AGE,
        )
        assert (state.events_state, state.items_state, state.rates_state) == (
            StoreStatus.FRESH,
            StoreStatus.FRESH,
            StoreStatus.FRESH,
        )

    def test_all_signals_degraded_keep_their_last_success_time(self):
        state = classify_store_state(
            {
                IngestProducer.FF_CRAWLER: _utc("2026-09-21T08:00:00Z"),
                IngestProducer.RSS: _utc("2026-09-21T08:00:00Z"),
                IngestProducer.FRED: _utc("2026-09-21T08:00:00Z"),
            },
            now=_NOW,
            max_age=_MAX_AGE,
        )
        assert (state.events_state, state.items_state, state.rates_state) == (
            StoreStatus.DEGRADED,
            StoreStatus.DEGRADED,
            StoreStatus.DEGRADED,
        )
        assert state.events_last_success_at == _utc("2026-09-21T08:00:00Z").isoformat()
        assert state.items_last_success_at == _utc("2026-09-21T08:00:00Z").isoformat()
        assert state.rates_last_success_at == _utc("2026-09-21T08:00:00Z").isoformat()

    def test_empty_mapping_is_unavailable_with_none_times(self):
        state = classify_store_state({}, now=_NOW, max_age=_MAX_AGE)
        assert state.events_state is StoreStatus.UNAVAILABLE
        assert state.items_state is StoreStatus.UNAVAILABLE
        assert state.rates_state is StoreStatus.UNAVAILABLE
        assert state.events_last_success_at is None
        assert state.items_last_success_at is None
        assert state.rates_last_success_at is None

    def test_success_exactly_at_max_age_boundary_is_still_fresh(self):
        state = classify_store_state(
            {IngestProducer.FRED: _utc("2026-09-21T10:00:00Z")},
            now=_NOW,
            max_age=_MAX_AGE,
        )
        assert state.rates_state is StoreStatus.FRESH
        assert state.events_state is StoreStatus.UNAVAILABLE
        assert state.items_state is StoreStatus.UNAVAILABLE

    def test_success_just_past_max_age_is_degraded(self):
        state = classify_store_state(
            {IngestProducer.RSS: _utc("2026-09-21T09:59:59Z")},
            now=_NOW,
            max_age=_MAX_AGE,
        )
        assert state.items_state is StoreStatus.DEGRADED

    def test_producer_keys_outside_the_signal_registry_are_ignored(self):
        # ``user`` / ``on_demand_lookup`` feed no signal (§6.5 has no clause
        # for them); they must not turn a missing signal fresh.
        state = classify_store_state(
            {
                IngestProducer.USER: _utc("2026-09-21T11:59:00Z"),
                IngestProducer.ON_DEMAND_LOOKUP: _utc("2026-09-21T11:59:00Z"),
            },
            now=_NOW,
            max_age=_MAX_AGE,
        )
        assert state.events_state is StoreStatus.UNAVAILABLE
        assert state.items_state is StoreStatus.UNAVAILABLE
        assert state.rates_state is StoreStatus.UNAVAILABLE

    def test_signal_key_still_wins_when_ignored_keys_are_also_present(self):
        state = classify_store_state(
            {
                IngestProducer.FF_CRAWLER: _utc("2026-09-21T11:30:00Z"),
                IngestProducer.USER: _utc("2026-09-21T11:59:00Z"),
                IngestProducer.ON_DEMAND_LOOKUP: _utc("2026-09-21T11:59:00Z"),
            },
            now=_NOW,
            max_age=_MAX_AGE,
        )
        assert state.events_state is StoreStatus.FRESH
        assert state.items_state is StoreStatus.UNAVAILABLE
        assert state.rates_state is StoreStatus.UNAVAILABLE

    def test_status_fields_are_store_status_members(self):
        state = classify_store_state({}, now=_NOW, max_age=_MAX_AGE)
        for field in (
            state.events_state,
            state.items_state,
            state.rates_state,
        ):
            assert isinstance(field, StoreStatus)


class TestContractShape:
    """Exact §6.5 signature + typed results only (C3/L3, B5 — no defaults)."""

    def test_classify_event_status_signature_without_defaults(self):
        sig = inspect.signature(classify_event_status)
        assert list(sig.parameters) == ["event", "now", "grace"]
        for name in ("now", "grace"):
            assert sig.parameters[name].default is inspect.Parameter.empty
        assert typing.get_type_hints(classify_event_status)["return"] is EventStatus

    def test_classify_store_state_signature_without_defaults(self):
        sig = inspect.signature(classify_store_state)
        assert list(sig.parameters) == ["last_success_by_producer", "now", "max_age"]
        for name in ("now", "max_age"):
            assert sig.parameters[name].default is inspect.Parameter.empty
        assert typing.get_type_hints(classify_store_state)["return"] is StoreState

    def test_grace_and_max_age_are_timedeltas_not_magic_numbers(self):
        assert isinstance(_GRACE, timedelta)
        assert isinstance(_MAX_AGE, timedelta)
        # The classifier receives actor-chosen intervals; it must not encode a
        # unit conversion (minutes/hours) - B5 forbids fabricated numbers.
        assert "news_policy" not in inspect.getsource(classify_event_status)
        assert "news_policy" not in inspect.getsource(classify_store_state)

    def test_results_are_enum_members_not_bare_strings(self):
        event_result = classify_event_status(
            _event(), now=_DEADLINE + timedelta(minutes=1), grace=_GRACE
        )
        assert type(event_result) is EventStatus
        state_result = classify_store_state({}, now=_NOW, max_age=_MAX_AGE)
        assert type(state_result) is StoreState
        assert type(state_result.events_state) is StoreStatus

    def test_stale_result_surfaces_the_persisted_string(self):
        result = classify_event_status(
            _event(), now=_DEADLINE + timedelta(seconds=1), grace=_GRACE
        )
        assert result == "stale"
        assert str(result) == "stale"


class TestCoreLayerBoundary:
    """core/news_freshness.py: pure + stdlib only (L2/L1 — điểm review của lô)."""

    @classmethod
    def _source(cls) -> str:
        return _NEWS_FRESHNESS_PY.read_text(encoding="utf-8")

    @classmethod
    def _imported_modules(cls) -> set[str]:
        tree = ast.parse(cls._source())
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                modules.add(node.module or "")
            elif isinstance(node, ast.Import):
                modules.update(alias.name.split(".")[0] for alias in node.names)
        return modules

    def test_imports_are_stdlib_plus_core_news_models_only(self):
        # The DoD review point: the pure module imports policy at no point, nor
        # any services/ui/controllers/Qt dependency.
        allowed = {"__future__", "collections.abc", "datetime", "core.news_models"}
        imported = self._imported_modules()
        assert imported <= allowed, f"unexpected imports: {imported - allowed}"
        assert "core.news_models" in imported

    def test_module_imports_nothing_from_policy_services_ui_controllers_or_qt(self):
        # Scan only the actual import statements (not prose/docstrings): a
        # ``news_policy``/``services``/``ui``/``controllers``/Qt module must
        # never appear as an import of this pure core module.
        forbidden_markers = (
            "news_policy",
            "services",
            "ui",
            "controllers",
            "PyQt6",
            "tkinter",
        )
        statements = [
            line.strip()
            for line in self._source().splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        assert statements, "expected at least the __future__ import"
        for stmt in statements:
            for marker in forbidden_markers:
                assert marker not in stmt, f"{marker!r} must not appear in {stmt!r}"

    def test_module_source_is_ascii_no_vietnamese_display_strings(self):
        # A core module carries no display strings (L2/L3): the whole source
        # stays ASCII, so a Vietnamese label or any non-ASCII glyph cannot hide.
        assert self._source().isascii()

    def test_classify_returns_no_display_text_anywhere(self):
        # No Vietnamese/English human-facing string is ever produced - the
        # classifier emits struct enum members only (L3).
        result = classify_event_status(
            _event(), now=_DEADLINE + timedelta(minutes=1), grace=_GRACE
        )
        assert result.value == "stale"
        state = classify_store_state({}, now=_NOW, max_age=_MAX_AGE)
        assert state.rates_state.value == "unavailable"