"""Per-evaluation reuse of the work done on ONE immutable closed window.

Task 137.  The causal structural replay walks every *prefix* of a single closed
candle window: for each candle it asks for the pivots of the prefix, its ATR
distance filter and the ATR reference before the prefix's last candle.  Each of
those is a pure function of the window, so recomputing them per candle repeats
the same work over data that cannot have changed — the validation of the whole
window alone ran once per candle, and pivot/ATR scans ran quadratically.

This module holds the reuse for exactly one evaluation:

* nothing is shared between evaluations — the object is created by the caller
  for one window and dies with it, so there is no cross-run cache, no
  production caching layer and no identity that could outlive the input;
* no rule changes — the reused values are the values the per-prefix calls
  produced, because each pivot at index ``i`` is decided inside
  ``candles[i - lookback : i + lookback + 1]`` and Wilder's ATR is causal, so a
  prefix can only *see fewer* pivots and ATR samples, never different ones;
* a sequence this object does not own is never reused: :meth:`owns` verifies
  EVERY candle against the window by object identity — endpoints alone are not
  ownership, because a sequence that keeps both ends and swaps a candle in
  between would otherwise be served evidence about data it does not contain —
  and every accessor falls back to the plain computation otherwise.

``ENABLED`` exists so the optimisation can be proved equivalent against its own
replacement: with it false every accessor takes the fallback path, i.e. exactly
the recompute-per-prefix behaviour the reuse replaced.  The equivalence test
toggles it and requires byte-identical results; production never disables it,
and no behaviour depends on it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from core.market_models import Candle, validate_smc_candles
from core.smc_context import (
    _confirmed_swing_points,
    _filter_swings_by_atr,
    _ATR_FILTER_MIN_CANDLES,
    _ATR_DISTANCE_MULT,
    _ATR_PERIOD,
)

# See the module docstring: the equivalence test toggles this to run the
# pre-optimisation recompute-per-prefix path against the reused one.  Nothing in
# production reads it as anything but True.
ENABLED = True


@dataclass(frozen=True, slots=True)
class WindowHistory:
    """The window-only part of a history assessment.

    Everything here is a function of the candle window and the symbol alone;
    only the origin/lifetime arguments of ``assess_smc_history`` vary per zone,
    and those are applied by the caller on top of these values.
    """

    issues: tuple[Any, ...]
    first_open: Any
    last_open: Any
    missing_slots: tuple[str, ...]
    closed_session_slots: int
    session_status: str


class StructureWindowReuse:
    """Validation, pivots and ATR series of one closed window, computed once."""

    def __init__(
        self,
        window: Sequence[Candle],
        timeframe: str,
        *,
        symbol: str = "",
    ) -> None:
        self._timeframe = str(timeframe or "").strip().upper()
        self._symbol = str(symbol or "")
        # The window is the *validated* closed set the replay owns; nothing here
        # re-orders, repairs or filters it.
        self._window: tuple[Candle, ...] = tuple(window)
        self._swings: dict[tuple[Any, ...], dict[str, list[dict[str, Any]]]] = {}
        self._atr: dict[int, list[float | None]] = {}
        self._history: dict[tuple[str, str], WindowHistory] = {}

    # -- ownership ---------------------------------------------------------

    def owns(self, prefix: Sequence[Candle]) -> bool:
        """Whether *prefix* is a leading slice of the window this object holds.

        Every candle is checked by object identity.  Checking only the two ends
        is NOT ownership: a sequence that keeps the first and last candle but
        swaps a candle in between would pass an endpoint check and then be
        served this window's pivots, ATR and coverage — evidence about data it
        does not contain.  Identity (not equality) is required because a rebuilt
        sequence holding equal-valued candles is a different input.
        """

        if not ENABLED:
            return False
        length = len(prefix)
        if length == 0 or length > len(self._window):
            return False
        window = self._window
        for index in range(length):
            if prefix[index] is not window[index]:
                return False
        return True

    def is_window(self, candles: Sequence[Candle]) -> bool:
        """Whether *candles* IS the whole window, not a shorter leading slice.

        Work that is a function of the complete window (the coverage scan) must
        not be read from a prefix, so those call sites use this stricter check.
        """

        return len(candles) == len(self._window) and self.owns(candles)

    # -- pivots ------------------------------------------------------------

    def swings(
        self,
        prefix: Sequence[Candle],
        *,
        symbol: str,
        lookback: int,
        provisional: bool,
        scope: str,
        equal_tolerance: float,
    ) -> dict[str, list[dict[str, Any]]]:
        """The pivots of *prefix*, read from the window-wide detection."""

        if not self.owns(prefix):
            return _confirmed_swing_points(
                prefix,
                symbol=symbol,
                timeframe=self._timeframe,
                lookback=lookback,
                provisional=provisional,
                scope=scope,
                equal_tolerance=equal_tolerance,
            )
        key = (lookback, provisional, scope, float(equal_tolerance), symbol)
        full = self._swings.get(key)
        if full is None:
            full = _confirmed_swing_points(
                self._window,
                symbol=symbol,
                timeframe=self._timeframe,
                lookback=lookback,
                provisional=provisional,
                scope=scope,
                equal_tolerance=equal_tolerance,
            )
            self._swings[key] = full
        # A pivot at index ``i`` is decided by the slice
        # ``[i - lookback, i + lookback]``, so a prefix of ``length`` can only
        # hold pivots whose right-hand window already fits inside it.
        last_index = len(prefix) - lookback - 1
        return {
            kind: [pivot for pivot in items if int(pivot["index"]) <= last_index]
            for kind, items in full.items()
        }

    # -- history coverage --------------------------------------------------

    def history_window(self, timeframe: str, symbol: str | None) -> WindowHistory:
        """The window-only history assessment, computed once per window.

        Every field is a pure function of the window, the timeframe and the
        symbol, so each zone of a timeframe reads the values it would otherwise
        have recomputed for itself.  The validation is still performed — once
        per window instead of once per zone — so ``issues`` is measured, never
        assumed.
        """

        key = (str(timeframe or "").strip().upper(), str(symbol or ""))
        cached = self._history.get(key)
        if cached is not None:
            return cached
        from core.smc_history import _find_coverage_gaps
        from core.smc_history import _is_utc_aware, _utc

        timeframe_name = key[0]
        issues = tuple(validate_smc_candles(self._window, timeframe_name))
        timestamps = [
            _utc(candle.time) for candle in self._window if _is_utc_aware(candle.time)
        ]
        missing_slots: tuple[str, ...] = ()
        closed_session_slots = 0
        session_status = "known"
        if not issues and len(self._window) > 1:
            missing, closed_slots, status = _find_coverage_gaps(
                self._window,
                timeframe_name,
                symbol,
            )
            missing_slots = tuple(missing)
            closed_session_slots = closed_slots
            session_status = status
        cached = WindowHistory(
            issues=issues,
            first_open=timestamps[0] if timestamps else None,
            last_open=timestamps[-1] if timestamps else None,
            missing_slots=missing_slots,
            closed_session_slots=closed_session_slots,
            session_status=session_status,
        )
        self._history[key] = cached
        return cached

    # -- ATR ---------------------------------------------------------------

    def atr_series(self, period: int = _ATR_PERIOD) -> list[float | None]:
        """Wilder's ATR over the whole window, computed once per period."""

        series = self._atr.get(period)
        if series is None:
            from core.indicators import atr

            series = atr(
                [candle.high for candle in self._window],
                [candle.low for candle in self._window],
                [candle.close for candle in self._window],
                period,
            )
            self._atr[period] = series
        return series

    def atr_before_index(
        self,
        prefix: Sequence[Candle],
        index: int,
        *,
        period: int = _ATR_PERIOD,
    ) -> float | None:
        """ATR of ``prefix[:index]``, i.e. the value strictly before *index*."""

        if not self.owns(prefix):
            return None
        series = self.atr_series(period)
        if index <= 0 or index > len(prefix) or index > len(series):
            return None
        return series[index - 1]

    def atr_last(self, prefix: Sequence[Candle], *, period: int = _ATR_PERIOD) -> float:
        """The same value ``_filter_swings_by_atr`` derives from the prefix."""

        if len(prefix) < _ATR_FILTER_MIN_CANDLES:
            return 0.0
        value = self.atr_before_index(prefix, len(prefix), period=period)
        return float(value) if value is not None else 0.0

    def filter_swings_by_atr(
        self,
        prefix: Sequence[Candle],
        swings: dict[str, list[dict[str, Any]]],
    ) -> dict[str, list[dict[str, Any]]]:
        """``_filter_swings_by_atr`` with the prefix's ATR read from the series."""

        if not self.owns(prefix):
            # Not this window: the plain function owns the answer.  Returning
            # the unfiltered swings here would silently drop a rule.
            return _filter_swings_by_atr(list(prefix), swings)
        if len(prefix) < _ATR_FILTER_MIN_CANDLES:
            return swings
        atr_now = self.atr_last(prefix)
        if atr_now <= 0:
            return swings
        min_distance = atr_now * _ATR_DISTANCE_MULT
        filtered_highs: list[dict[str, Any]] = []
        filtered_lows: list[dict[str, Any]] = []
        for high in swings["highs"]:
            if not filtered_highs or abs(high["level"] - filtered_highs[-1]["level"]) >= min_distance:
                filtered_highs.append(high)
        for low in swings["lows"]:
            if not filtered_lows or abs(low["level"] - filtered_lows[-1]["level"]) >= min_distance:
                filtered_lows.append(low)
        return {"highs": filtered_highs, "lows": filtered_lows}


__all__ = ["StructureWindowReuse"]
