"""trend_prompt_builder - the prompt of the AI trend judgement (plan batch L3.1).

Sole owner of "dung prompt nhan dinh xu huong" (contract section 11b, identity
M5).  This module turns the already-calibrated domain rows (``CalendarEvent`` /
``NewsItem`` of ``core/news_models.py``) into the prompt the AI reads on contract
section 9.1 step 3, together with the provenance values the verdict rows store:
``prompt_hash`` (section 4.5) and ``input_snapshot`` (window + counts).

Inherited doctrine (section 9.1 step 3): the AI judges **only** on the data put
into the prompt - inventing events, figures, dates or citation ids is forbidden.
The prompt therefore carries every row it may be judged on, each with its domain
id, and ``core/trend_verdict_parser.py`` refuses a verdict citing anything else.

**Market context (batch B3, section 9.1 step 3 - C1-C3):** the prompt also
renders a reasoning-aid block (policy rate + trend, treasury 2y/10y with deltas,
2y10y spread, real yield) from a typed ``MarketContext``.  The context never
counts toward the ``ai_min_items`` floor and carries no row id, so it can never
be cited as evidence (C4); it is not written to ``input_snapshot`` (section 4.5
unchanged).  Its rating types arrive through ``Protocol``s declared here, so
``core/`` still never imports ``services/`` (L1).

Purity and layering (the review point of this batch):

* **Pure (L2).**  No I/O, no network, no clock beyond the ``now`` parameter, no
  policy read.  The three AI keys of contract section 7 - ``ai_window_days``,
  ``ai_min_items``, ``ai_horizons`` - arrive as parameters (R4: no operational
  number is hard-coded here, and the module never loads the policy itself).  The
  horizon frame renders each definition exactly as the Owner wrote it, **keeping
  its unit** (day/week/month, L1.1 decision) instead of converting it to days.
* **Layer-clean (L1).**  Imports only stdlib + ``core.news_models`` +
  ``core.news_policy`` (the typed ``HorizonDefinition`` the caller already
  holds) + ``core.yield_context`` (the typed context); never
  services/ui/controllers/Qt - the rate context arrives through the ``Protocol``
  declared here, not through a ``services`` import.
* **No display string (L3).**  The source stays ASCII and English: the prompt is
  machine input for the model, never shown to the user.  The Vietnamese the
  contract requires is the model's ``rationale`` output, which the prompt asks
  for in so many words.
* **One owner for the floor** (section 9.1 step 2): below ``ai_min_items`` no
  prompt exists, so the AI cannot be called on too little data (B4, fail-closed).
  The caller only maps ``insufficient_data`` to its status/UI.

``prompt_hash`` is the hash of the prompt **frame**, never of the data (section
4.5): the frame is the fixed instruction text plus the horizon framing (keys and
their declared unit/min/max), while everything that varies per request - the
rows, their ids, the window dates, the counts and the scope value - stays out of
it.  A template edit, or a re-defined horizon, therefore changes the hash; a new
set of news rows does not.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from core.news_models import (
    CalendarEvent,
    NewsItem,
    VerdictConfidence,
    VerdictDirection,
)
from core.news_policy import HorizonDefinition
from core.yield_context import YieldContext

__all__ = [
    "MarketContext",
    "RateContextLike",
    "TrendPrompt",
    "TrendPromptOutcome",
    "build_trend_prompt",
]


# ---------------------------------------------------------------------------
# Market context (section 9.1 step 3, batch B3 - C1-C3)
# ---------------------------------------------------------------------------


class RateReadingLike(Protocol):
    """Structural view of the rate reading the prompt prints - the two fields of
    ``RateObservation`` the context line needs.

    A Protocol (not an import) because ``core/`` must never depend on
    ``services/`` (L1): the caller passes the real
    ``services.news_repository.CurrencyRateTrend`` and the type checker accepts
    it structurally."""

    rate: float
    observed_at: str


class TrendValueLike(Protocol):
    """Structural view of the derived trend enum (``core/rate_trend.RateTrend``):
    only its frozen ``value`` is rendered."""

    value: str


class RateContextLike(Protocol):
    """Structural view of one ``CurrencyRateTrend`` the prompt needs
    (``currency`` + ``latest`` + ``trend``).

    Declared here as a ``Protocol`` so the builder stays free of a
    ``core -> services`` import (L1, import-linter gate); the caller passes the
    real repository model."""

    currency: str
    latest: RateReadingLike
    trend: TrendValueLike


@dataclass(frozen=True, slots=True)
class MarketContext:
    """Optional market context for one prompt (section 9.1 step 3, batch B3).

    ``rates`` holds 0..2 policy-rate contexts (one for a currency scope, both
    sides for a pair); ``yields`` holds the USD bond-yield context, or ``None``
    when none is available (B4).  Context is **reasoning aid only**: it is not
    counted toward the ``ai_min_items`` floor (C4) and its values are never
    citable as evidence (they carry no row id here).  An empty instance is
    ``MarketContext()`` - the prompt then renders ``market context: none``."""

    rates: tuple[RateContextLike, ...] = ()
    yields: YieldContext | None = None


# ---------------------------------------------------------------------------
# The prompt frame (ASCII, English - machine input, never displayed)
# ---------------------------------------------------------------------------

_INSUFFICIENT = VerdictDirection.INSUFFICIENT_DATA.value
_NO_CONFIDENCE = VerdictConfidence.NONE.value

_DIRECTION_VALUES = " | ".join(member.value for member in VerdictDirection)
_CONFIDENCE_VALUES = " | ".join(member.value for member in VerdictConfidence)

# The instruction skeleton.  Every placeholder is filled per request, so the
# skeleton itself carries no data and is what ``prompt_hash`` covers.
_PROMPT_TEMPLATE = """You are a macro analyst for the foreign-exchange market.

Task: judge the trend of {scope_label} for each horizon listed below, using ONLY
the data in this prompt.

Rules:
- Use only the rows under "Data". Never invent events, numbers, dates, currency
  codes or row ids.
- Every id in "evidence_item_ids" must be a row id printed in this prompt;
  citing any other id makes the whole answer invalid.
- If the data is not enough to judge a horizon, answer that horizon with
  direction "{insufficient}" and confidence "{no_confidence}", and say why in
  the rationale.
- Write every rationale in Vietnamese.

Scope: {scope_label}
Data window: the last {window_days} day(s), {from_utc} to {to_utc} (UTC).
{market_context}

Horizons - judge each one and use these exact keys:
{horizon_frame}

Data ({event_count} calendar event(s), {item_count} news item(s)):
{data}

Answer with ONE JSON object and nothing else - no prose, no markdown fence -
holding exactly the horizon keys above, each with "direction", "confidence",
"rationale" and "evidence_item_ids":

{schema}

Allowed values:
- direction: {directions}
- confidence: {confidences}

JSON:"""

# Frame fragments: fixed text, rendered per row/horizon (placeholders only).
_HORIZON_LINE_TEMPLATE = "- {horizon}: {unit} {min_value}-{max_value}"
_EVENT_LINE_TEMPLATE = (
    "- [event #{row_id}] {event_time_utc} | {currency} | {title} | impact={impact}"
    " | actual={actual} | forecast={forecast} | previous={previous}"
)
_NEWS_LINE_TEMPLATE = (
    "- [news #{row_id}] {published_utc} | {currency} | {kind} | {title}"
    " | content={content} | source={source}"
)
_SCHEMA_LINE_TEMPLATE = (
    '  "{horizon}": {{"direction": "{directions}", "confidence": "{confidences}", '
    '"rationale": "{rationale}", "evidence_item_ids": [{evidence}]}}{comma}'
)

# Market-context fragments (section 9.1 step 3, batch B3).  The block is a
# reasoning aid; it carries no row id, so it can never be cited as evidence.
_MARKET_CONTEXT_HEADER = (
    "Market context (for reasoning only - do NOT cite as evidence):"
)
_MARKET_CONTEXT_NONE = "market context: none"
_RATE_CONTEXT_LINE_TEMPLATE = (
    "- policy rate {currency}: {rate} ({trend}), observed {observed_at}"
)
_YIELD_TREASURY_LINE_TEMPLATE = (
    "- treasury 2y: {y2} (delta {d2} in window), 10y: {y10} (delta {d10})"
)
_YIELD_SPREAD_LINE_TEMPLATE = (
    "- spread 2y10y: {spread}; real yield 10y: {real}"
)

_ABSENT = "-"
_NO_ROW_ID = "no-id"


# ---------------------------------------------------------------------------
# Typed results (C3 - no bare dict across the boundary)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TrendPrompt:
    """One built prompt plus the provenance of what went in.

    ``text`` is the whole prompt handed to the model.  ``prompt_hash`` is the
    provenance key of section 4.5 (hash of the frame).  ``snapshot`` is the
    ``input_snapshot`` value the verdict rows store - the window and the counts
    of section 4.5, nothing else (scope and provider live in their own columns).
    ``evidence_item_ids`` lists the row ids printed in the prompt, which is what
    the parser checks a citation against."""

    text: str
    prompt_hash: str
    snapshot: dict[str, object]
    evidence_item_ids: tuple[int, ...]
    event_count: int
    item_count: int


@dataclass(frozen=True, slots=True)
class TrendPromptOutcome:
    """Typed outcome of ``build_trend_prompt`` (section 9.1 step 2).

    Either a prompt, or the fail-closed report that the data set is below
    ``ai_min_items`` - in which case **no prompt exists and the AI must not be
    called** (B4).  The counts and the floor are carried either way so the caller
    can show what was considered without recomputing it."""

    prompt: TrendPrompt | None
    event_count: int
    item_count: int
    min_items: int

    @property
    def insufficient_data(self) -> bool:
        """True when the data set is below ``ai_min_items`` (no prompt built)."""
        return self.prompt is None


# ---------------------------------------------------------------------------
# Frame helpers (pure)
# ---------------------------------------------------------------------------


def _utc(value: datetime) -> datetime:
    """Read a moment as aware UTC (a naive value is UTC - the house convention)."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _iso(moment: datetime) -> str:
    """The ISO-8601 UTC form every persisted news timestamp uses."""
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _text(value: object) -> str:
    """Render one field of a row: an empty value prints as ``-``."""
    rendered = str(value).strip() if value is not None else ""
    return rendered or _ABSENT


def _scope_label(scope_type: str, scope_value: str) -> str:
    """Human-readable scope for the prompt body (``pair`` / ``currency``)."""
    return f"{scope_type} {scope_value}".strip()


def _horizon_frame(horizons: Mapping[str, HorizonDefinition]) -> str:
    """The horizon block: one line per horizon, keeping the Owner's unit."""
    return "\n".join(
        _HORIZON_LINE_TEMPLATE.format(
            horizon=key,
            unit=span.unit,
            min_value=span.min_value,
            max_value=span.max_value,
        )
        for key, span in horizons.items()
    )


def _schema_block(horizons: Mapping[str, HorizonDefinition]) -> str:
    """The JSON skeleton the model must fill, one key per horizon."""
    keys = list(horizons)
    lines = ["{"]
    for index, key in enumerate(keys):
        lines.append(
            _SCHEMA_LINE_TEMPLATE.format(
                horizon=key,
                directions=_DIRECTION_VALUES,
                confidences=_CONFIDENCE_VALUES,
                rationale="reasoning in Vietnamese",
                evidence="ids printed above",
                comma="," if index < len(keys) - 1 else "",
            )
        )
    lines.append("}")
    return "\n".join(lines)


def _event_line(event: CalendarEvent) -> str:
    """One calendar-event row, prefixed with its domain id (if it has one)."""
    return _EVENT_LINE_TEMPLATE.format(
        row_id=event.id if event.id is not None else _NO_ROW_ID,
        event_time_utc=_text(event.event_time_utc),
        currency=_text(event.currency),
        title=_text(event.title),
        impact=event.impact.value,
        actual=_text(event.actual),
        forecast=_text(event.forecast),
        previous=_text(event.previous),
    )


def _news_line(item: NewsItem) -> str:
    """One text-news row, prefixed with its domain id (if it has one)."""
    return _NEWS_LINE_TEMPLATE.format(
        row_id=item.id if item.id is not None else _NO_ROW_ID,
        published_utc=_text(item.published_utc),
        currency=",".join(item.currencies) if item.currencies else _ABSENT,
        kind=item.kind.value,
        title=_text(item.title),
        content=_text(item.content),
        source=item.source.value,
    )


def _data_block(events: Sequence[CalendarEvent], items: Sequence[NewsItem]) -> str:
    """The data section, in the order the caller supplied (events, then items)."""
    lines = [_event_line(event) for event in events]
    lines.extend(_news_line(item) for item in items)
    return "\n".join(lines) if lines else _ABSENT


def _number(value: float | None) -> str:
    """Render a context number to two decimals; a missing value prints ``-``
    (the ``_ABSENT`` form) - no figure is invented (B4)."""
    return _ABSENT if value is None else f"{value:.2f}"


def _market_context_block(context: MarketContext) -> str:
    """The market-context section (section 9.1 step 3, batch B3).

    One policy-rate line per item in ``context.rates``; the treasury/spread
    lines only when ``context.yields is not None`` (missing sub-fields print
    ``-``).  With neither rate nor yields the whole block is the single line
    ``market context: none``.  The block carries no row id, so nothing in it is
    citable as evidence (C4)."""
    lines = [
        _RATE_CONTEXT_LINE_TEMPLATE.format(
            currency=_text(rate.currency),
            rate=_number(rate.latest.rate),
            trend=_text(rate.trend.value),
            observed_at=_text(rate.latest.observed_at),
        )
        for rate in context.rates
    ]
    yields = context.yields
    if yields is not None:
        lines.append(
            _YIELD_TREASURY_LINE_TEMPLATE.format(
                y2=_number(yields.yield_2y),
                d2=_number(yields.delta_2y),
                y10=_number(yields.yield_10y),
                d10=_number(yields.delta_10y),
            )
        )
        lines.append(
            _YIELD_SPREAD_LINE_TEMPLATE.format(
                spread=_number(yields.spread_2y10y),
                real=_number(yields.real_yield_10y),
            )
        )
    if not lines:
        return _MARKET_CONTEXT_NONE
    return "\n".join([_MARKET_CONTEXT_HEADER, *lines])


def _skeleton(horizons: Mapping[str, HorizonDefinition]) -> str:
    """Canonical text of the frame - the thing ``prompt_hash`` hashes.

    In: every fixed fragment of the prompt (instructions, row shapes, schema
    shape) and the horizon framing (key + declared unit/min/max).  Out: the rows,
    their ids, the window dates, the counts and the scope value - the data of one
    request must never move the hash (section 4.5)."""
    parts = [
        _PROMPT_TEMPLATE,
        _HORIZON_LINE_TEMPLATE,
        _EVENT_LINE_TEMPLATE,
        _NEWS_LINE_TEMPLATE,
        _SCHEMA_LINE_TEMPLATE,
        _MARKET_CONTEXT_HEADER,
        _MARKET_CONTEXT_NONE,
        _RATE_CONTEXT_LINE_TEMPLATE,
        _YIELD_TREASURY_LINE_TEMPLATE,
        _YIELD_SPREAD_LINE_TEMPLATE,
    ]
    parts.extend(
        f"{key}|{span.unit}|{span.min_value}|{span.max_value}"
        for key, span in horizons.items()
    )
    return "\n".join(parts)


def _prompt_hash(horizons: Mapping[str, HorizonDefinition]) -> str:
    """Stable sha256 of the frame (the same form as the other news hashes)."""
    return hashlib.sha256(_skeleton(horizons).encode("utf-8")).hexdigest()


def _evidence_ids(
    events: Sequence[CalendarEvent], items: Sequence[NewsItem]
) -> tuple[int, ...]:
    """The row ids printed in the prompt, in print order (only rows that carry
    an id can be cited - a citation must name a row the model was shown)."""
    return tuple(
        int(row.id)
        for row in (*events, *items)
        if row.id is not None
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_trend_prompt(
    *,
    scope_type: str,
    scope_value: str,
    events: Sequence[CalendarEvent],
    items: Sequence[NewsItem],
    context: MarketContext,
    now: datetime,
    window_days: int,
    horizons: Mapping[str, HorizonDefinition],
    min_items: int,
) -> TrendPromptOutcome:
    """Build the AI prompt for one scope from the calibrated rows (section 9.1
    step 3), or report insufficient data (step 2).

    ``window_days``/``min_items``/``horizons`` are the ``ai_window_days`` /
    ``ai_min_items`` / ``ai_horizons`` keys of contract section 7, passed in by
    the caller (R4).  ``events``/``items`` are the rows the caller already read
    for the scope inside the window - this function filters nothing (the query
    is the repository's job) and only renders what it is given, so the AI is
    shown exactly the data the caller decided on.

    The floor is checked first: fewer than ``min_items`` rows in total yields no
    prompt at all (fail-closed, B4) and the AI is never called.  ``context`` is
    rendered as the reasoning-aid block of section 9.1 step 3 (batch B3): it is
    **never** counted toward the floor (C4), its values carry no row id and so
    cannot be cited, and it is not part of ``snapshot``.

    ``prompt_hash`` covers the frame only; the returned ``snapshot`` carries the
    window and the counts for the verdict rows."""
    event_count = len(events)
    item_count = len(items)
    if event_count + item_count < min_items:
        return TrendPromptOutcome(
            prompt=None,
            event_count=event_count,
            item_count=item_count,
            min_items=min_items,
        )

    moment = _utc(now)
    from_utc = _iso(moment - timedelta(days=window_days))
    to_utc = _iso(moment)
    label = _scope_label(scope_type, scope_value)
    text = _PROMPT_TEMPLATE.format(
        scope_label=label,
        insufficient=_INSUFFICIENT,
        no_confidence=_NO_CONFIDENCE,
        window_days=window_days,
        from_utc=from_utc,
        to_utc=to_utc,
        market_context=_market_context_block(context),
        horizon_frame=_horizon_frame(horizons),
        event_count=event_count,
        item_count=item_count,
        data=_data_block(events, items),
        schema=_schema_block(horizons),
        directions=_DIRECTION_VALUES,
        confidences=_CONFIDENCE_VALUES,
    )
    return TrendPromptOutcome(
        prompt=TrendPrompt(
            text=text,
            prompt_hash=_prompt_hash(horizons),
            snapshot={
                "window_days": window_days,
                "from_utc": from_utc,
                "to_utc": to_utc,
                "event_count": event_count,
                "item_count": item_count,
            },
            evidence_item_ids=_evidence_ids(events, items),
            event_count=event_count,
            item_count=item_count,
        ),
        event_count=event_count,
        item_count=item_count,
        min_items=min_items,
    )
