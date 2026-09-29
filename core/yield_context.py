"""Owns the derivation of the bond-yield context (deltas, 2y-10y spread and the
10-year real yield) from a set of ``BondYieldObservation`` values - the single
owner registered at contract section 4.7 and the ownership registry 11b
(identity M5, batch B2).

One pure entry point, ``derive_yield_context``, maps the observations of one
currency to a ``YieldContext``:

* per maturity (``2y``/``10y``/``be10y``) the newest observation supplies the
  value and its ``observed_at``;
* ``delta_2y``/``delta_10y`` are ``latest - reference`` where ``reference`` is
  the nearest observation at or before ``now - window_days`` (the window edge
  is inclusive); no such older observation (or no observation older than the
  latest at all) yields ``None`` - nothing is invented (B4);
* ``spread_2y10y = 10y - 2y`` and ``real_yield_10y = 10y - be10y``; either is
  ``None`` when one of its two inputs is missing (section 4.7: a missing
  ``be10y`` gives no real yield, never a guess).

Wave 6 (contract section 4.7 / section 9.1): ``YieldContext`` also carries the
**3-month and 6-month deltas** of 2y/10y/spread/real yield, read at the fixed
contract marks ``90`` and ``180`` days.  The reference of a mark is the
observation nearest that mark whose date differs from the latest one; without
such an observation (or with a missing leg) the delta is ``None`` - nothing is
invented (B4).  The spread/real delta is computed from the reference pair at the
same mark (``10y_then - 2y_then``), never as a difference of two deltas taken at
different marks.

Governance:

* **Pure (L2).** No I/O, no Qt, no policy read, no network, no filesystem and
  no clock: ``now`` and ``window_days`` are parameters.  The caller (the
  repository) turns the policy key ``ai_window_days`` into ``window_days``, so
  this module never imports ``news_policy``.  A ``core/`` module imports
  nothing from services/ui/controllers and emits no display strings (L1/L3);
  the whole source is ASCII.
* **Read-model, not a table row.** ``YieldContext`` is declared here (like
  ``RateTrend``) because it maps no schema column and is never persisted
  (sections 4.7/5) - ``core/news_models.py`` owns only table-mapped models and
  their column enums.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from core.news_models import BondYieldMaturity, BondYieldObservation, BondYieldSource

# Fixed contract marks of the 3-month / 6-month deltas (contract section 4.7,
# wave 6): the Owner fixed them as 90 and 180 days - not section 7 policy keys,
# so they stay module constants here (no policy read in a core module).
_THREE_MONTHS_DAYS = 90
_SIX_MONTHS_DAYS = 180


@dataclass(frozen=True, slots=True)
class YieldDeltaSet:
    """Deltas of one horizon mark (3-month or 6-month) for one currency.

    Each field is ``current - reference`` at the mark, or ``None`` when no
    reference observation exists (or a leg is missing) - always B4, never a
    guessed zero.  A typed packet consumed by the prompt builder (wave C3)."""

    delta_2y: float | None = None
    delta_10y: float | None = None
    delta_spread: float | None = None
    delta_real: float | None = None


@dataclass(frozen=True, slots=True)
class YieldContext:
    """Derived bond-yield context of one currency at read time (section 4.7).

    ``yield_2y``/``yield_10y``/``be10y`` carry the newest value of each
    maturity (``None`` when that maturity was never observed) with its
    ``observed_at``; ``delta_2y``/``delta_10y`` the change over the caller's
    window; ``spread_2y10y`` and ``real_yield_10y`` the two derived spreads.
    ``delta_3m``/``delta_6m`` carry the 3-month/6-month delta sets of wave 6.
    Typed fields only - never a bare dict across the boundary (C3).
    """

    yield_2y: float | None
    observed_at_2y: str | None
    yield_10y: float | None
    observed_at_10y: str | None
    be10y: float | None
    observed_at_be10y: str | None
    delta_2y: float | None
    delta_10y: float | None
    spread_2y10y: float | None
    real_yield_10y: float | None
    delta_3m: YieldDeltaSet = field(default_factory=YieldDeltaSet)
    delta_6m: YieldDeltaSet = field(default_factory=YieldDeltaSet)


def _by_recency(
    observations: list[BondYieldObservation],
) -> list[BondYieldObservation]:
    """Observations of one maturity, newest first.

    Ordering: ``observed_at`` descending, then the primary FRED source before
    the Yahoo fallback at the same date, then the newest row id - so the
    "latest" reading is deterministic when a date was written by both channels.
    """
    return sorted(
        observations,
        key=lambda obs: (
            obs.observed_at,
            obs.source == BondYieldSource.FRED,
            obs.id or 0,
        ),
        reverse=True,
    )


def _latest(observations: list[BondYieldObservation]) -> BondYieldObservation | None:
    """The newest observation of a maturity, or ``None`` when there is none."""
    ordered = _by_recency(observations)
    return ordered[0] if ordered else None


def _delta(
    observations: list[BondYieldObservation],
    cutoff: str,
) -> float | None:
    """``latest - reference`` over the window, or ``None`` (B4).

    The reference is the nearest observation at or before the inclusive window
    edge ``cutoff`` that is not the latest one itself; without such an older
    observation the delta cannot be measured and is ``None`` - no guess.
    """
    ordered = _by_recency(observations)
    if not ordered:
        return None
    latest = ordered[0]
    for observation in ordered:
        if observation.observed_at <= cutoff:
            if observation.observed_at == latest.observed_at:
                return None
            return latest.value - observation.value
    return None


def _reference_near(
    observations: list[BondYieldObservation],
    cutoff: str,
) -> BondYieldObservation | None:
    """The observation nearest the mark ``cutoff``, or ``None`` (B4).

    The mark is the fixed contract edge (90/180 days back); the reference is the
    observation whose date is closest to it on either side, excluding any
    observation sharing the latest date (which would measure no depth).
    Deterministic: ties break on the older ``observed_at`` (section 4.7)."""
    ordered = _by_recency(observations)
    if not ordered:
        return None
    latest = ordered[0]
    candidates = [
        observation
        for observation in ordered
        if observation.observed_at != latest.observed_at
    ]
    if not candidates:
        return None
    mark = date.fromisoformat(cutoff)
    return min(
        candidates,
        key=lambda observation: (
            abs((date.fromisoformat(observation.observed_at) - mark).days),
            observation.observed_at,
        ),
    )


def _delta_set(
    by_maturity: dict[BondYieldMaturity, list[BondYieldObservation]],
    latest_2y: BondYieldObservation | None,
    latest_10y: BondYieldObservation | None,
    latest_be10y: BondYieldObservation | None,
    cutoff: str,
) -> YieldDeltaSet:
    """The 3-month/6-month delta set of one currency at ``cutoff`` (section 4.7).

    ``delta_2y``/``delta_10y`` are ``latest - reference`` for each maturity.  The
    spread/real delta is ``(10y - leg)_now - (10y - leg)_then`` from the
    reference pair at the same mark (``10y_then - 2y_then`` / ``10y_then -
    be10y_then``) - never a difference of two deltas taken at different marks.
    Any missing reference value leaves its delta ``None`` (B4)."""
    reference_2y = _reference_near(by_maturity[BondYieldMaturity.TWO_YEAR], cutoff)
    reference_10y = _reference_near(by_maturity[BondYieldMaturity.TEN_YEAR], cutoff)
    reference_be10y = _reference_near(
        by_maturity[BondYieldMaturity.BREAKEVEN_10Y], cutoff
    )

    def _difference(
        latest: BondYieldObservation | None,
        reference: BondYieldObservation | None,
    ) -> float | None:
        if latest is None or reference is None:
            return None
        return latest.value - reference.value

    spread_now = (
        latest_10y.value - latest_2y.value
        if latest_10y is not None and latest_2y is not None
        else None
    )
    spread_then = (
        reference_10y.value - reference_2y.value
        if reference_10y is not None and reference_2y is not None
        else None
    )
    real_now = (
        latest_10y.value - latest_be10y.value
        if latest_10y is not None and latest_be10y is not None
        else None
    )
    real_then = (
        reference_10y.value - reference_be10y.value
        if reference_10y is not None and reference_be10y is not None
        else None
    )

    return YieldDeltaSet(
        delta_2y=_difference(latest_2y, reference_2y),
        delta_10y=_difference(latest_10y, reference_10y),
        delta_spread=(
            spread_now - spread_then
            if spread_now is not None and spread_then is not None
            else None
        ),
        delta_real=(
            real_now - real_then
            if real_now is not None and real_then is not None
            else None
        ),
    )


def derive_yield_context(
    observations: list[BondYieldObservation],
    now: datetime,
    window_days: int,
) -> YieldContext:
    """Derive the bond-yield context of one currency (contract section 4.7).

    ``observations`` holds every observation of that currency (any maturity);
    ``now`` is the read-time instant and ``window_days`` the caller's window
    (the repository passes the ``ai_window_days`` policy value).  A maturity
    with no observation resolves to ``None`` for its value and ``observed_at``;
    the two spreads follow the section 4.7 rules (missing input -> ``None``).
    """
    by_maturity: dict[BondYieldMaturity, list[BondYieldObservation]] = {
        maturity: [] for maturity in BondYieldMaturity
    }
    for observation in observations:
        by_maturity.setdefault(observation.maturity, []).append(observation)

    cutoff = (now - timedelta(days=window_days)).date().isoformat()
    cutoff_3m = (now - timedelta(days=_THREE_MONTHS_DAYS)).date().isoformat()
    cutoff_6m = (now - timedelta(days=_SIX_MONTHS_DAYS)).date().isoformat()

    latest_2y = _latest(by_maturity[BondYieldMaturity.TWO_YEAR])
    latest_10y = _latest(by_maturity[BondYieldMaturity.TEN_YEAR])
    latest_be10y = _latest(by_maturity[BondYieldMaturity.BREAKEVEN_10Y])

    yield_2y = latest_2y.value if latest_2y is not None else None
    yield_10y = latest_10y.value if latest_10y is not None else None
    be10y = latest_be10y.value if latest_be10y is not None else None

    spread_2y10y = (
        yield_10y - yield_2y
        if yield_2y is not None and yield_10y is not None
        else None
    )
    real_yield_10y = (
        yield_10y - be10y if yield_10y is not None and be10y is not None else None
    )

    return YieldContext(
        yield_2y=yield_2y,
        observed_at_2y=latest_2y.observed_at if latest_2y is not None else None,
        yield_10y=yield_10y,
        observed_at_10y=latest_10y.observed_at if latest_10y is not None else None,
        be10y=be10y,
        observed_at_be10y=(
            latest_be10y.observed_at if latest_be10y is not None else None
        ),
        delta_2y=_delta(by_maturity[BondYieldMaturity.TWO_YEAR], cutoff),
        delta_10y=_delta(by_maturity[BondYieldMaturity.TEN_YEAR], cutoff),
        spread_2y10y=spread_2y10y,
        real_yield_10y=real_yield_10y,
        delta_3m=_delta_set(
            by_maturity, latest_2y, latest_10y, latest_be10y, cutoff_3m
        ),
        delta_6m=_delta_set(
            by_maturity, latest_2y, latest_10y, latest_be10y, cutoff_6m
        ),
    )
