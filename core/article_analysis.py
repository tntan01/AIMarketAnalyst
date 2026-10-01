"""article_analysis - prompt for the AI analysis of one text news item (pure).

Owner requirement (30/09/2026): in the news-screen row dialog the user presses
"Analyse" and the AI gives a SHORT analysis of the article - what it says, which
currencies it concerns and how it could move them.

Advisory only (contract section 9.2): the answer is shown to the user, is never
stored and never feeds scoring, gates, execution guards or alerts - it is not a
verdict, so nothing about it reaches ``ai_trend_verdicts``.

Pure (L2): no I/O, no network, no clock, no policy read - the frame is built from
the typed item alone and the caller owns the AI call and its token budget.  The
source stays ASCII; the frame asks for Vietnamese prose because the answer is
read by the user and never parsed.
"""

from __future__ import annotations

from core.news_models import NewsItem

__all__ = ["build_analysis_prompt"]

_MISSING = "-"

_FRAME_TEMPLATE = """You are a macro analyst for the foreign-exchange market.

Analyse ONE news article for a Vietnamese-speaking trader.

Article:
- time (UTC): {published_utc}
- source: {source}
- kind: {kind}
- headline: {title}
- currencies named by the outlet: {currencies}
- body: {content}

Answer in Vietnamese as plain prose - no markdown, no JSON, no headings - in
three to five sentences, in this order:
1. what the article says, in one sentence;
2. which currencies it concerns and how it could move them - the likely
   direction, the channel (rate expectations, growth, risk appetite) and how
   strong the signal looks;
3. what the reader should watch next for this story to develop.

Rules:
- Use only what the article says. Never invent figures, dates or quotations that
  are not in it; write "{missing}" for a missing field and say so.
- This is a general read of the article, never investment advice: do not tell
  the reader to buy or sell, and do not claim certainty about the market.
"""


def _text(value: str | None) -> str:
    """Normalize a value for the frame: empty/None -> a dash (never guessed)."""
    if value is None:
        return _MISSING
    text = str(value).strip()
    return text if text else _MISSING


def build_analysis_prompt(item: NewsItem) -> str:
    """The prompt that analyses one text news item (pure; contract section 9.2).

    The frame prints exactly the item's own fields (time, source, kind, headline,
    currencies, body) and asks for a SHORT Vietnamese read of the story, always
    naming the currencies it concerns and how it could move them; it forbids
    inventing figures and forbids buy/sell advice.  This function never calls the
    AI, never reads policy and never touches the database."""
    currencies = ", ".join(item.currencies) if item.currencies else _MISSING
    return _FRAME_TEMPLATE.format(
        published_utc=_text(item.published_utc),
        source=item.source.value,
        kind=item.kind.value,
        title=_text(item.title),
        currencies=currencies,
        content=_text(item.content),
        missing=_MISSING,
    )
