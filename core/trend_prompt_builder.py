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

Purity and layering (the review point of this batch):

* **Pure (L2).**  No I/O, no network, no clock beyond the ``now`` parameter, no
  policy read.  The three AI keys of contract section 7 - ``ai_window_days``,
  ``ai_min_items``, ``ai_horizons`` - arrive as parameters (R4: no operational
  number is hard-coded here, and the module never loads the policy itself).  The
  horizon frame renders each definition exactly as the Owner wrote it, **keeping
  its unit** (day/week/month, L1.1 decision) instead of converting it to days.
* **Layer-clean (L1).**  Imports only stdlib + ``core.news_models`` +
  ``core.news_policy`` (the typed ``HorizonDefinition`` the caller already
  holds); never services/ui/controllers/Qt.
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

from core.news_models import (
    CalendarEvent,
    NewsItem,
    VerdictConfidence,
    VerdictDirection,
)
from core.news_policy import HorizonDefinition

__all__ = ["TrendPrompt", "TrendPromptOutcome", "build_trend_prompt"]


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
    prompt at all (fail-closed, B4) and the AI is never called.

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
