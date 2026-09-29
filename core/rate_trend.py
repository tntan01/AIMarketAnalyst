"""Owns the derivation of the policy-rate trend (hike/cut/hold) from the two
nearest rate observations - the single owner registered at contract section
4.4 and the ownership registry 11b (identity M5).

One pure entry point, ``derive_rate_trend``, maps two ``RateObservation``
values to a ``RateTrend`` whose members are the frozen persistence strings of
section 2 (V3(a)):

* ``previous is None`` (fewer than two observations) always yields ``HOLD`` -
  the characterization of the legacy single-observation run where ``prev``
  collapses onto ``latest`` and the delta is zero (B3, function-level);
* otherwise the threshold is selected by ``latest.source``: ``RateSource.FRED``
  uses the FRED threshold, ``RateSource.FF_HTML`` uses the ForexFactory-HTML
  threshold, ``RateSource.CONFIG_FALLBACK`` has no inherited threshold and
  never leaves ``HOLD``;
* a delta strictly above the threshold is ``HIKE``, strictly below its
  negative is ``CUT``, the rest (including a delta exactly equal to the
  threshold) is ``HOLD`` - the strict ``>``/``<`` comparisons of the original
  inline code are preserved verbatim.

Wave 6 (contract section 8 ``rate_paths``, section 11b): the same owner also
derives the **rate path** - ``derive_rate_path`` maps a currency's whole rate
history to a ``RatePath`` (rate now, rate ~``months`` months ago and their
change).  The reference is the observation nearest the mark
``now - months * 30`` days whose date differs from the latest one; fewer than
two dated observations (or no distinct older date) yields ``None`` for
``rate_then``/``change`` - nothing is guessed (B4).

Governance:

* **Pure (L2).** No I/O, no Qt, no policy read, no network, no filesystem.
  The two thresholds are existing runtime values inherited from
  ``services/interest_rate_service.py`` (B5 - evidence: in production), not
  keys of section 7, so they are module constants here and are never read via
  the ``news_policy`` loader.  The 30-day month is the fixed contract
  convention of the path mark, likewise a module constant.  A ``core/`` module
  imports nothing from services/ui/controllers and emits no display strings
  (L1/L3); the whole source is ASCII.
* **Never merged.** The FRED threshold and the ForexFactory-HTML threshold
  stay separate - no combined threshold is invented (B5).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum

from core.news_models import RateObservation, RateSource

# Inherited FRED threshold of the currently-running runtime (B5 - evidence:
# in production).  Ported verbatim from the trend block of
# ``_fetch_from_fred``, lines 182-187 of ``services/interest_rate_service.py``:
# ``latest > prev + 0.1`` -> hike; ``latest < prev - 0.1`` -> cut; else hold.
# Kept as a module constant - ``0.1`` is not one of the nine operational keys
# of contract section 7, so it is not loaded through ``news_policy``.
_FRED_THRESHOLD = 0.1

# Inherited ForexFactory-HTML threshold of the currently-running runtime (B5 -
# evidence: in production).  Ported verbatim from the trend line 123 of
# ``_update_from_forexfactory`` of ``services/interest_rate_service.py``:
# ``new > old + 0.01`` -> hike; ``new < old - 0.01`` -> cut; else hold.
# Deliberately separate from ``_FRED_THRESHOLD`` - the two are never merged.
_FF_THRESHOLD = 0.01


class RateTrend(str, Enum):
    """Direction of a policy-rate move, derived at read time (sections 2, 4.4).

    Frozen machine-read strings (V3(a)): ``str(member) == member.value ==
    "hike"/"cut"/"hold"``, and because each member is a ``str`` subclass,
    ``derive_rate_trend(...) == "hike"`` stays true - the positional
    equivalent of the legacy code returning a bare string.  This enum is
    intentionally declared here, not in ``core/news_models.py``: a trend is
    never a schema column and never persisted (section 4.4), while
    ``news_models`` owns only the six models and their column enums.
    """

    HIKE = "hike"
    CUT = "cut"
    HOLD = "hold"

    def __str__(self) -> str:
        return self.value


def derive_rate_trend(
    latest: RateObservation,
    previous: RateObservation | None,
) -> RateTrend:
    """Derive hike/cut/hold from the two nearest observations (contract 4.4).

    ``latest`` is always a real observation; ``previous is None`` means fewer
    than two observations exist and yields ``HOLD`` (the legacy
    single-observation behavior where ``prev`` defaults to ``latest`` at line
    179, delta 0).  The threshold is chosen by ``latest.source`` (FRED 0.1,
    FF_HTML 0.01); ``CONFIG_FALLBACK`` keeps ``HOLD`` - the legacy code never
    derived a trend for the fallback source, so no threshold exists to inherit
    and none is invented (B5).  Comparisons stay strict: a delta exactly equal
    to the threshold is ``HOLD``, matching the original ``>``/``<`` logic.
    """
    if previous is None:
        return RateTrend.HOLD

    if latest.source == RateSource.FRED:
        threshold = _FRED_THRESHOLD
    elif latest.source == RateSource.FF_HTML:
        threshold = _FF_THRESHOLD
    else:
        return RateTrend.HOLD

    delta = latest.rate - previous.rate
    if delta > threshold:
        return RateTrend.HIKE
    if delta < -threshold:
        return RateTrend.CUT
    return RateTrend.HOLD


# Fixed contract convention of the rate-path mark (contract section 8, wave 6):
# one month is 30 days, so six months is 180 - not a section 7 policy key, hence
# a module constant here (no policy read in a core module).
_DAYS_PER_MONTH = 30


@dataclass(frozen=True, slots=True)
class RatePath:
    """The policy-rate path of one currency over ``months`` (contract section 8).

    ``rate_now`` is the newest rate; ``rate_then`` the rate nearest the mark
    ``now - months * 30`` days ago; ``change = rate_now - rate_then``.  Each is
    ``None`` when the history has no such observation - nothing is guessed
    (B4).  A typed packet consumed by ``NewsRepository.rate_paths`` (wave C3)."""

    rate_now: float | None
    rate_then: float | None
    change: float | None


def _by_recency(
    observations: list[RateObservation],
) -> list[RateObservation]:
    """Observations newest first, tie-broken by descending row id - deterministic
    even when two sources share a date."""
    return sorted(
        observations,
        key=lambda observation: (observation.observed_at, observation.id or 0),
        reverse=True,
    )


def _reference_near(
    ordered: list[RateObservation], latest: RateObservation, mark: str
) -> RateObservation | None:
    """The observation nearest the mark whose date is not the latest date (B4).

    Ties break on the older ``observed_at`` so the result never depends on the
    input order (deterministic)."""
    candidates = [
        observation
        for observation in ordered
        if observation.observed_at != latest.observed_at
    ]
    if not candidates:
        return None
    mark_date = date.fromisoformat(mark)
    return min(
        candidates,
        key=lambda observation: (
            abs((date.fromisoformat(observation.observed_at) - mark_date).days),
            observation.observed_at,
        ),
    )


def derive_rate_path(
    observations: list[RateObservation],
    now: datetime,
    months: int = 6,
) -> RatePath:
    """Derive the rate path of one currency over ``months`` (contract section 8).

    ``observations`` holds the currency's whole rate history.  ``rate_now`` is
    the newest observation; ``rate_then`` is the observation nearest the mark
    ``now - months * 30`` days whose date differs from the latest one; with no
    such older observation (fewer than two dated observations) both
    ``rate_then`` and ``change`` are ``None`` (B4 - no guess)."""
    ordered = _by_recency(observations)
    if not ordered:
        return RatePath(rate_now=None, rate_then=None, change=None)
    latest = ordered[0]
    mark = (now - timedelta(days=months * _DAYS_PER_MONTH)).date().isoformat()
    reference = _reference_near(ordered, latest, mark)
    if reference is None:
        return RatePath(rate_now=latest.rate, rate_then=None, change=None)
    return RatePath(
        rate_now=latest.rate,
        rate_then=reference.rate,
        change=latest.rate - reference.rate,
    )