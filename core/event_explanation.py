"""event_explanation - prompt for the AI explanation of one calendar event (pure).

Owner requirement (30/09/2026): in the news-screen row dialog the user presses
"Explain" and the AI explains the indicator behind a ForexFactory event, paying
special attention to how that event affects the event's currency.

Advisory only (contract section 9.2): the answer is shown to the user, is never
stored and never feeds scoring, gates, execution guards or alerts - it is not a
verdict, so nothing about it reaches ``ai_trend_verdicts``.

Pure (L2): no I/O, no network, no clock, no policy read - the frame is built from
the typed event alone and the caller owns the AI call and its token budget.  The
source stays ASCII; the frame asks for Vietnamese prose because the answer has no
machine consumer (it is read by the user, never parsed).
"""

from __future__ import annotations

from core.news_models import CalendarEvent

__all__ = ["build_explanation_prompt"]

_MISSING = "-"

_FRAME_TEMPLATE = """You are a macro analyst for the foreign-exchange market.

Explain ONE economic indicator release to a Vietnamese-speaking trader.

Event:
- currency: {currency}
- indicator: {title}
- impact level: {impact}
- time (UTC): {event_time_utc}
- previous: {previous}
- forecast: {forecast}
- actual: {actual}

Answer in Vietnamese as plain prose - no markdown, no JSON, no headings - in four
to six sentences, in this order:
1. what the indicator measures and how it is read: which direction is good for
   the economy and why traders watch it;
2. what the numbers above say: compare actual with forecast and with previous;
   when actual is missing, say the figure has not been released yet and explain
   what the forecast means instead;
3. above all, how this release affects {currency}: the direction a surprise
   usually moves that currency, the channel it works through (rate expectations,
   growth, risk appetite) and how strong the effect is at impact level
   "{impact}".

Rules:
- Use only the numbers printed above. Never invent, estimate or extrapolate a
  figure that is not there; write "{missing}" for a missing value and say so.
- Explain the indicator and its typical effect - never tell the reader to buy or
  sell, and never claim certainty about the market reaction.
"""


def _text(value: str | None) -> str:
    """Normalize a value for the frame: empty/None -> a dash (never guessed)."""
    if value is None:
        return _MISSING
    text = str(value).strip()
    return text if text else _MISSING


def build_explanation_prompt(event: CalendarEvent) -> str:
    """The prompt that explains one calendar event (pure; contract section 9.2).

    The frame prints exactly the event's own facts (currency, indicator, impact
    level, UTC time, previous/forecast/actual) and asks the model to pay special
    attention to how the release affects THE EVENT'S CURRENCY; it forbids
    inventing figures and forbids buy/sell advice.  This function never calls the
    AI, never reads policy and never touches the database."""
    return _FRAME_TEMPLATE.format(
        currency=_text(event.currency),
        title=_text(event.title),
        impact=event.impact.value,
        event_time_utc=_text(event.event_time_utc),
        previous=_text(event.previous),
        forecast=_text(event.forecast),
        actual=_text(event.actual),
        missing=_MISSING,
    )
