"""Owns the derivation of a forex pair bias from two single-asset verdicts
(contract section 9.3 khoan 2, batch B4).

One pure entry point, ``derive_pair_bias``, maps the two ``TrendVerdict`` rows of
a pair's legs (same horizon) to a ``PairBias``.  It is **not** an AI verdict and
is never persisted (contract section 9.3 khoan 2 / A4): it is a display-only
derivation over the two component verdicts the news screen already read.

Deterministic matrix (contract section 9.3 / plan B4):

| Condition                                              | Result          |
|--------------------------------------------------------|-----------------|
| either leg missing, or a leg ``insufficient_data``     | ``UNCLEAR``     |
| both legs the same direction                           | that direction  |
| one leg ``neutral``, the other bullish/bearish         | the other side  |
| both legs ``neutral``                                  | ``NEUTRAL``     |
| opposite directions, different confidence              | higher-confidence side (high > medium > low) |
| opposite directions, equal confidence                  | ``NEUTRAL``     |

"Which side wins" follows the direction of the winning leg: a bullish base wins
-> pair ``BULLISH``; a bearish base wins -> pair ``BEARISH``.

Governance:

* **Pure (L2).**  No I/O, no Qt, no policy read, no network, no clock.  A
  ``core/`` module imports nothing from services/ui/controllers and emits no
  display strings (L1/L3); the whole source is ASCII and returns enum members.
* **Read-model, not a table row.**  ``PairBias`` is declared here (like
  ``RateTrend``/``YieldContext``) because it maps no schema column and is never
  persisted.
"""

from __future__ import annotations

from enum import Enum

from core.news_models import TrendVerdict, VerdictConfidence, VerdictDirection


class PairBias(str, Enum):
    """Derived direction of a forex pair (contract section 9.3 khoan 2).

    Frozen machine-read strings: ``str(member) == member.value`` so a bias can
    be compared to its persisted-string equivalent.  Never stored (A4)."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    UNCLEAR = "unclear"

    def __str__(self) -> str:
        return self.value


# Confidence ordering for the "opposite directions" tie-break: ``high`` beats
# ``medium`` beats ``low``.  ``none`` never takes part (it only accompanies
# ``insufficient_data``, already resolved to ``UNCLEAR``) and ranks lowest.
_CONFIDENCE_RANK: dict[VerdictConfidence, int] = {
    VerdictConfidence.HIGH: 3,
    VerdictConfidence.MEDIUM: 2,
    VerdictConfidence.LOW: 1,
    VerdictConfidence.NONE: 0,
}


def derive_pair_bias(
    base: TrendVerdict | None,
    quote: TrendVerdict | None,
) -> PairBias:
    """Derive the pair bias from the two same-horizon component verdicts
    (contract section 9.3 khoan 2; the matrix is documented at module level).

    ``base``/``quote`` are the newest verdicts of the pair's legs for one
    horizon, or ``None`` when a leg has none.  A missing leg or an
    ``insufficient_data`` leg yields ``UNCLEAR`` - nothing is invented (B4).
    """
    if base is None or quote is None:
        return PairBias.UNCLEAR
    if (
        base.direction is VerdictDirection.INSUFFICIENT_DATA
        or quote.direction is VerdictDirection.INSUFFICIENT_DATA
    ):
        return PairBias.UNCLEAR

    if base.direction is quote.direction:
        # Same direction (bullish/bearish/neutral) - the direction wins.
        return PairBias(base.direction.value)
    if base.direction is VerdictDirection.NEUTRAL:
        return PairBias(quote.direction.value)
    if quote.direction is VerdictDirection.NEUTRAL:
        return PairBias(base.direction.value)

    # Opposite directions (bullish vs bearish): the higher-confidence leg wins;
    # equal confidence is neutral.
    base_rank = _CONFIDENCE_RANK.get(base.confidence, 0)
    quote_rank = _CONFIDENCE_RANK.get(quote.confidence, 0)
    if base_rank == quote_rank:
        return PairBias.NEUTRAL
    winner = base.direction if base_rank > quote_rank else quote.direction
    return PairBias(winner.value)
