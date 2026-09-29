"""Pure tests for the bond-yield context derivation (contract §4.7, plan lô B2).

``core/yield_context.py`` is the registered single owner of the delta/spread/
real-yield derivation (§11b).  Its contract, verified here:

* per maturity the newest observation supplies value + ``observed_at``;
* ``delta_2y``/``delta_10y`` measure ``latest - reference`` where the reference
  is the nearest observation at or before the inclusive window edge
  ``now - window_days``; without an older observation the delta is ``None``
  (B4 - nothing is guessed);
* ``spread_2y10y = 10y - 2y`` and ``real_yield_10y = 10y - be10y``; either is
  ``None`` when an input is missing (a missing ``be10y`` never fabricates a
  real yield);
* wave 6: the 3-month/6-month delta sets (marks 90/180 days) of 2y/10y/spread/
  real yield are derived from the reference pair nearest each mark (never a
  difference of deltas taken at different marks), ``None`` when a reference leg
  is missing;
* the function is deterministic and pure: two calls with the same input return
  equal results, and the module imports no I/O / policy / (L1/L2) upstream.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.news_models import BondYieldMaturity, BondYieldObservation, BondYieldSource
from core.yield_context import YieldContext, derive_yield_context

_YIELD_CONTEXT_PY = (
    Path(__file__).resolve().parents[1] / "core" / "yield_context.py"
)

_TWO_YEAR = BondYieldMaturity.TWO_YEAR
_TEN_YEAR = BondYieldMaturity.TEN_YEAR
_BE10Y = BondYieldMaturity.BREAKEVEN_10Y

_NOW = datetime(2026, 9, 21, 12, 0, 0, tzinfo=timezone.utc)
_WINDOW = 7  # cutoff = 2026-09-14 (inclusive)


def _obs(
    maturity: BondYieldMaturity,
    observed_at: str,
    value: float,
    *,
    source: BondYieldSource = BondYieldSource.FRED,
    row_id: int | None = None,
) -> BondYieldObservation:
    return BondYieldObservation(
        currency="USD",
        maturity=maturity,
        value=value,
        observed_at=observed_at,
        source=source,
        fetched_at="2026-09-21T01:00:00Z",
        id=row_id,
    )


class TestDeriveYieldContext:
    def test_full_context_values_deltas_spread_and_real_yield(self):
        context = derive_yield_context(
            [
                _obs(_TWO_YEAR, "2026-09-21", 4.50),
                _obs(_TWO_YEAR, "2026-09-14", 4.00),  # exactly at the edge
                _obs(_TEN_YEAR, "2026-09-21", 4.20),
                _obs(_TEN_YEAR, "2026-09-13", 3.90),
                _obs(_BE10Y, "2026-09-21", 2.30),
                _obs(_BE10Y, "2026-09-13", 2.00),
            ],
            now=_NOW,
            window_days=_WINDOW,
        )
        assert isinstance(context, YieldContext)
        assert (context.yield_2y, context.observed_at_2y) == (4.50, "2026-09-21")
        assert (context.yield_10y, context.observed_at_10y) == (4.20, "2026-09-21")
        assert (context.be10y, context.observed_at_be10y) == (2.30, "2026-09-21")
        assert context.delta_2y == pytest.approx(0.50)
        assert context.delta_10y == pytest.approx(0.30)
        assert context.spread_2y10y == pytest.approx(-0.30)
        assert context.real_yield_10y == pytest.approx(1.90)

    def test_newest_observation_wins_for_each_maturity(self):
        context = derive_yield_context(
            [
                _obs(_TWO_YEAR, "2026-09-10", 4.00),
                _obs(_TWO_YEAR, "2026-09-20", 4.40),
                _obs(_TWO_YEAR, "2026-09-21", 4.50),
            ],
            now=_NOW,
            window_days=_WINDOW,
        )
        assert context.yield_2y == 4.50
        assert context.observed_at_2y == "2026-09-21"

    def test_reference_just_after_the_window_edge_is_not_used(self):
        # 09-15 is after the cutoff (09-14); only 09-14 qualifies -> delta uses it.
        context = derive_yield_context(
            [
                _obs(_TWO_YEAR, "2026-09-21", 4.50),
                _obs(_TWO_YEAR, "2026-09-15", 4.45),
                _obs(_TWO_YEAR, "2026-09-14", 4.00),
            ],
            now=_NOW,
            window_days=_WINDOW,
        )
        assert context.delta_2y == pytest.approx(0.50)

    def test_no_older_observation_leaves_delta_none(self):
        context = derive_yield_context(
            [_obs(_TWO_YEAR, "2026-09-21", 4.50)],
            now=_NOW,
            window_days=_WINDOW,
        )
        assert context.yield_2y == 4.50
        assert context.delta_2y is None

    def test_only_observation_older_than_window_leaves_delta_none(self):
        # The newest reading is itself at/before the window edge -> no window
        # change can be measured, so the delta is None (not a fabricated zero).
        context = derive_yield_context(
            [_obs(_TWO_YEAR, "2026-09-01", 4.00)],
            now=_NOW,
            window_days=_WINDOW,
        )
        assert context.yield_2y == 4.00
        assert context.delta_2y is None

    def test_missing_breakeven_leaves_real_yield_none(self):
        context = derive_yield_context(
            [
                _obs(_TWO_YEAR, "2026-09-21", 4.50),
                _obs(_TEN_YEAR, "2026-09-21", 4.20),
            ],
            now=_NOW,
            window_days=_WINDOW,
        )
        assert context.be10y is None
        assert context.observed_at_be10y is None
        assert context.real_yield_10y is None
        assert context.spread_2y10y == pytest.approx(-0.30)

    def test_missing_a_spread_leg_leaves_spread_none(self):
        context = derive_yield_context(
            [_obs(_TEN_YEAR, "2026-09-21", 4.20)],
            now=_NOW,
            window_days=_WINDOW,
        )
        assert context.yield_2y is None
        assert context.spread_2y10y is None
        assert context.real_yield_10y is None

    def test_empty_input_is_all_none(self):
        context = derive_yield_context([], now=_NOW, window_days=_WINDOW)
        assert context == YieldContext(
            yield_2y=None,
            observed_at_2y=None,
            yield_10y=None,
            observed_at_10y=None,
            be10y=None,
            observed_at_be10y=None,
            delta_2y=None,
            delta_10y=None,
            spread_2y10y=None,
            real_yield_10y=None,
        )

    def test_fred_source_wins_when_two_sources_share_a_date(self):
        context = derive_yield_context(
            [
                _obs(_TEN_YEAR, "2026-09-21", 4.20, source=BondYieldSource.FRED),
                _obs(_TEN_YEAR, "2026-09-21", 9.99, source=BondYieldSource.YAHOO),
            ],
            now=_NOW,
            window_days=_WINDOW,
        )
        assert context.yield_10y == 4.20

    def test_is_deterministic(self):
        observations = [
            _obs(_TWO_YEAR, "2026-09-21", 4.50),
            _obs(_TWO_YEAR, "2026-09-14", 4.00),
        ]
        assert derive_yield_context(
            observations, now=_NOW, window_days=_WINDOW
        ) == derive_yield_context(observations, now=_NOW, window_days=_WINDOW)


class TestThreeAndSixMonthDeltas:
    """Wave 6 (contract §4.7): the 3-month/6-month delta sets.

    Fixed marks: ``_NOW`` 2026-09-21 -> 3-month mark 2026-06-23,
    6-month mark 2026-03-25 (90/180 days)."""

    def _context(self, observations):
        return derive_yield_context(observations, now=_NOW, window_days=_WINDOW)

    def test_three_and_six_month_deltas_of_all_four_quantities(self):
        observations = [
            _obs(_TWO_YEAR, "2026-09-21", 4.50),
            _obs(_TWO_YEAR, "2026-06-23", 4.00),
            _obs(_TWO_YEAR, "2026-03-25", 3.50),
            _obs(_TEN_YEAR, "2026-09-21", 4.20),
            _obs(_TEN_YEAR, "2026-06-23", 4.10),
            _obs(_TEN_YEAR, "2026-03-25", 4.00),
            _obs(_BE10Y, "2026-09-21", 2.30),
            _obs(_BE10Y, "2026-06-23", 2.10),
            _obs(_BE10Y, "2026-03-25", 2.00),
        ]
        context = self._context(observations)

        assert context.delta_3m.delta_2y == pytest.approx(0.50)
        assert context.delta_3m.delta_10y == pytest.approx(0.10)
        # spread_then = 10y_then - 2y_then = 4.10 - 4.00, so delta = -0.30 - 0.10
        assert context.delta_3m.delta_spread == pytest.approx(-0.40)
        # real_then = 10y_then - be10y_then = 4.10 - 2.10 -> delta = 1.90 - 2.00
        assert context.delta_3m.delta_real == pytest.approx(-0.10)

        assert context.delta_6m.delta_2y == pytest.approx(1.00)
        assert context.delta_6m.delta_10y == pytest.approx(0.20)
        assert context.delta_6m.delta_spread == pytest.approx(-0.80)
        assert context.delta_6m.delta_real == pytest.approx(-0.10)

    def test_reference_is_the_observation_nearest_the_mark(self):
        observations = [
            _obs(_TWO_YEAR, "2026-09-21", 4.50),
            _obs(_TWO_YEAR, "2026-06-20", 4.00),  # 3 days before the 3m mark
            _obs(_TWO_YEAR, "2026-07-01", 3.00),  # 8 days after -> not chosen
        ]
        context = self._context(observations)

        assert context.delta_3m.delta_2y == pytest.approx(0.50)

    def test_reference_after_the_mark_is_used_when_nearest(self):
        observations = [
            _obs(_TWO_YEAR, "2026-09-21", 4.50),
            _obs(_TWO_YEAR, "2026-05-01", 3.00),  # far before
            _obs(_TWO_YEAR, "2026-07-01", 4.00),  # 8 days after -> nearest
        ]
        context = self._context(observations)

        assert context.delta_3m.delta_2y == pytest.approx(0.50)

    def test_missing_reference_leaves_the_mark_delta_none(self):
        context = self._context([_obs(_TWO_YEAR, "2026-09-21", 4.50)])

        assert context.delta_3m.delta_2y is None
        assert context.delta_6m.delta_2y is None

    def test_spread_delta_uses_the_reference_pair_and_real_needs_both_legs(self):
        observations = [
            _obs(_TWO_YEAR, "2026-09-21", 4.50),
            _obs(_TWO_YEAR, "2026-06-23", 4.00),
            _obs(_TEN_YEAR, "2026-09-21", 4.20),
            _obs(_TEN_YEAR, "2026-06-23", 4.10),
            _obs(_BE10Y, "2026-09-21", 2.30),  # no breakeven reference at the mark
        ]
        context = self._context(observations)

        # spread delta from the pair at the same mark: (4.20-4.50)-(4.10-4.00)
        assert context.delta_3m.delta_spread == pytest.approx(-0.40)
        # real yield lacks a mark reference -> None (never a one-sided guess)
        assert context.delta_3m.delta_real is None

    def test_window_deltas_are_unchanged_by_the_mark_extension(self):
        observations = [
            _obs(_TWO_YEAR, "2026-09-21", 4.50),
            _obs(_TWO_YEAR, "2026-09-14", 4.00),
        ]
        context = self._context(observations)

        assert context.delta_2y == pytest.approx(0.50)
        assert context.delta_10y is None


class TestCoreLayerBoundary:
    def test_module_source_is_ascii(self):
        assert _YIELD_CONTEXT_PY.read_text(encoding="utf-8").isascii()

    def test_module_imports_nothing_from_services_policy_or_qt(self):
        source = _YIELD_CONTEXT_PY.read_text(encoding="utf-8")
        statements = [
            line.strip()
            for line in source.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        assert statements
        for stmt in statements:
            for marker in ("news_policy", "services", "PyQt6", "controllers", " ui"):
                assert marker not in stmt, f"{marker!r} must not appear in {stmt!r}"
