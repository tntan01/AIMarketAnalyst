"""News domain models - the typed seam of the News domain (contract section 5).

This module declares the six domain models of the News domain plus the frozen
string enums (V3(a) - machine-read closed value sets, section 2) they use:

* ``CalendarEvent``    -> ``news_events`` (section 4.2)
* ``NewsItem``         -> ``news_items`` (section 4.3)
* ``RateObservation``  -> ``interest_rates`` (section 4.4)
* ``TrendVerdict``     -> ``ai_trend_verdicts`` (section 4.5)
* ``IngestRun``        -> ``ingest_runs`` (section 4.6)
* ``StoreState``       -> derived, never a table row (sections 5, 6.5, 8)

Field names follow the columns of the L1.2 migration
(``data/migrations/news/001_create_news_db.sql``) one-to-one, so the schema is
the single machine-read source of names.  Three columns are domain-ified on
purpose - multi-valued columns whose JSON encoding/decoding belongs to the
repository layer (L2.1), never to the model: ``currencies_json`` ->
``currencies``, ``evidence_item_ids_json`` -> ``evidence_item_ids``,
``input_snapshot_json`` -> ``input_snapshot``.

Governance:

* **Data only.** No business logic (state classification lives in
  ``core/news_freshness.py``, batch L1.4; rate-trend derivation lives in
  ``core/rate_trend.py``, batch L1.5), no I/O, no display strings (L2/L3).
  A ``core/`` module never imports services/ui/Qt and never touches the
  network or the filesystem.
* **Enums are frozen strings.** Every closed value set of sections 4.2-4.6 is
  one ``str``-mixin enum whose members equal the persisted string exactly -
  the same sets the L1.2 CHECK constraints pin, so a member change here fails
  the test battery in both directions.
* **Nullability mirrors the schema.** Fields are ``Optional`` with ``None``
  exactly where the L1.2 column is nullable; fields are mandatory where the
  column is ``NOT NULL``.  ``id`` is optional (assigned by the database on
  insert, present on read); ``excluded`` defaults to ``False`` in the same
  spirit as the column's ``DEFAULT 0``.  A NULL-carrier default is a data
  structure decision, not a policy default - B4 does not apply to model fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class _StringEnum(str, Enum):
    """str-mixin enum: compare/participate as its frozen persisted string."""

    def __str__(self) -> str:
        return self.value


# --- news_events enums (section 4.2) ---------------------------------------


class EventImpact(_StringEnum):
    """How strongly a calendar event can move its currency (section 4.2)."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NON = "non"


class EventStatus(_StringEnum):
    """Lifecycle of a calendar event (vocabulary, section 2 + 4.2) -
    ``scheduled`` before its time, ``released`` once an actual is known,
    ``stale`` when it passed its grace window without an actual
    (classification is core/news_freshness.py, batch L1.4)."""

    SCHEDULED = "scheduled"
    RELEASED = "released"
    STALE = "stale"


class EventSource(_StringEnum):
    """Provenance of a calendar event (section 4.2)."""

    FF_JSON = "ff_json"
    FF_HTML = "ff_html"
    USER = "user"
    IMPORT = "import"


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    """One calibrated calendar event from ForexFactory (section 4.2).

    ``forecast``/``previous``/``actual``/``actual_updated_at``/``raw_json``
    are nullable because the SQL columns are: a scheduled event has no
    actual yet and ``raw_json`` is provenance payload available only from
    producers.
    """

    day_key: str
    event_time_utc: str
    currency: str
    title: str
    impact: EventImpact
    status: EventStatus
    source: EventSource
    dedupe_key: str
    fetched_at: str
    forecast: str | None = None
    previous: str | None = None
    actual: str | None = None
    actual_updated_at: str | None = None
    raw_json: str | None = None
    id: int | None = None


# --- news_items enums (section 4.3) ----------------------------------------


class NewsItemKind(_StringEnum):
    """Kind of a text news item (section 4.3)."""

    HEADLINE = "headline"
    STATEMENT = "statement"
    USER_NOTE = "user_note"


class NewsItemSource(_StringEnum):
    """Provenance of a text news item (section 4.3)."""

    GOOGLE_NEWS_RSS = "google_news_rss"
    FXSTREET_RSS = "fxstreet_rss"
    INVESTING_RSS = "investing_rss"
    USER = "user"
    IMPORT = "import"


class ImpactHint(_StringEnum):
    """Manual impact hint, only on ``user_note`` items (section 4.3)."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True, slots=True)
class NewsItem:
    """One text news item - headline, statement or manual note (section 4.3).

    ``currencies`` is the typed list behind the ``currencies_json`` column;
    JSON serialization is the repository's job (L2.1).  ``excluded`` mirrors
    the column's ``DEFAULT 0`` - a fresh item is never flagged.  ``content``
    is mandatory for ``user_note`` but nullable in the schema, so it stays a
    plain NULL-carrier here with no business-level rule (section 6.4).
    """

    kind: NewsItemKind
    source: NewsItemSource
    title: str
    published_utc: str
    currencies: list[str]
    dedupe_key: str
    fetched_at: str
    content: str | None = None
    url: str | None = None
    impact_hint: ImpactHint | None = None
    speaker_role: str | None = None
    excluded: bool = False
    id: int | None = None


# --- interest_rates enums (section 4.4) ------------------------------------


class RateSource(_StringEnum):
    """Provenance of a rate observation (section 4.4)."""

    FRED = "fred"
    FF_HTML = "ff_html"
    CONFIG_FALLBACK = "config_fallback"


@dataclass(frozen=True, slots=True)
class RateObservation:
    """One recorded policy-rate reading of a currency (section 4.4).

    Trend (hike/cut/hold) is never stored - it is derived at read time from
    the two nearest observations by ``core/rate_trend.py`` (batch L1.5).
    """

    currency: str
    rate: float
    observed_at: str
    source: RateSource
    fetched_at: str
    id: int | None = None


# --- ai_trend_verdicts enums (section 4.5) ---------------------------------


class VerdictScopeType(_StringEnum):
    """What a trend verdict is about (section 4.5)."""

    PAIR = "pair"
    CURRENCY = "currency"


class VerdictHorizon(_StringEnum):
    """The three fixed AI horizons (sections 4.5 and 7)."""

    SHORT = "short"
    MID = "mid"
    LONG = "long"


class VerdictDirection(_StringEnum):
    """AI judgement of a scope under a horizon (section 4.5)."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    INSUFFICIENT_DATA = "insufficient_data"


class VerdictConfidence(_StringEnum):
    """AI confidence on a verdict (section 4.5)."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class TrendVerdict:
    """One AI trend verdict row - advisory only, never an input to any
    automated process (section 9.2).

    ``evidence_item_ids`` and ``input_snapshot`` are the typed values behind
    the ``evidence_item_ids_json``/``input_snapshot_json`` columns; JSON
    serialization belongs to the repository (L2.1).  ``rationale`` is the
    Vietnamese reasoning produced by the AI (the contract requires it); this
    module only carries it - display strings are a UI concern and none are
    declared here.
    """

    created_at: str
    scope_type: VerdictScopeType
    scope_value: str
    horizon: VerdictHorizon
    direction: VerdictDirection
    confidence: VerdictConfidence
    rationale: str
    evidence_item_ids: list[int]
    input_snapshot: dict[str, object]
    provider: str
    model: str
    prompt_hash: str
    id: int | None = None


# --- ingest_runs enums (section 4.6) ---------------------------------------


class IngestProducer(_StringEnum):
    """The producer identity logging an ingest run (section 4.6)."""

    FF_CRAWLER = "ff_crawler"
    RSS = "rss"
    FRED = "fred"
    USER = "user"
    ON_DEMAND_LOOKUP = "on_demand_lookup"


class IngestRunStatus(_StringEnum):
    """Outcome of one ingest run (section 4.6)."""

    OK = "ok"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class IngestRun:
    """Operational log of one producer run (section 4.6).

    ``error_type``/``error_detail`` are nullable - a successful run has no
    error to record.
    """

    producer: IngestProducer
    started_at: str
    finished_at: str
    status: IngestRunStatus
    items_written: int
    error_type: str | None = None
    error_detail: str | None = None
    id: int | None = None


# --- StoreState (sections 5, 6.5, 8 - derived, no table) -------------------


class StoreStatus(_StringEnum):
    """Freshness of one signal's data feed (sections 5, 6.5, 8):
    ``fresh`` while a successful ingest is recent enough, ``degraded`` once
    it aged past the freshness window, ``unavailable`` when no successful
    ingest ever happened (classification is core/news_freshness.py, L1.4)."""

    FRESH = "fresh"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class StoreState:
    """Freshness summary of the whole store (section 8, ``store_state()``).

    Reports one ``StoreStatus`` per signal (``events``, ``items``, ``rates``)
    plus the last successful ingest time of each signal (from ``ingest_runs``;
    ``None`` when the signal never had a successful run).  Two explicitly
    typed components, field by field - never a bare dict across the boundary
    (C3).
    """

    events_state: StoreStatus
    items_state: StoreStatus
    rates_state: StoreStatus
    events_last_success_at: str | None = None
    items_last_success_at: str | None = None
    rates_last_success_at: str | None = None