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

from dataclasses import dataclass
from datetime import datetime, timedelta

from core.news_models import BondYieldMaturity, BondYieldObservation, BondYieldSource


@dataclass(frozen=True, slots=True)
class YieldContext:
    """Derived bond-yield context of one currency at read time (section 4.7).

    ``yield_2y``/``yield_10y``/``be10y`` carry the newest value of each
    maturity (``None`` when that maturity was never observed) with its
    ``observed_at``; ``delta_2y``/``delta_10y`` the change over the caller's
    window; ``spread_2y10y`` and ``real_yield_10y`` the two derived spreads.
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
    )
