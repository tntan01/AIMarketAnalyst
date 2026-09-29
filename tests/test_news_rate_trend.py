"""Pure tests for the rate-path derivation (contract §8, wave 6, plan lô C2).

``core/rate_trend.derive_rate_path`` is the registered single owner of the
6-month rate path (contract §11b).  Its contract, verified here:

* ``rate_now`` is the newest observation; ``rate_then`` the observation nearest
  the mark ``now - months * 30`` days whose date differs from the latest one;
* fewer than two dated observations (or no distinct older date) -> both
  ``rate_then`` and ``change`` are ``None`` (B4 - never a guessed zero);
* the result is a typed ``RatePath`` and the function is pure/deterministic;
* the module stays layer-clean: stdlib + ``core.news_models`` only, ASCII.
"""

from __future__ import annotations

import ast
import inspect
import typing
from datetime import datetime, timezone
from pathlib import Path

from core.news_models import RateObservation, RateSource
from core.rate_trend import RatePath, derive_rate_path

_RATE_TREND_PY = Path(__file__).resolve().parents[1] / "core" / "rate_trend.py"

_NOW = datetime(2026, 9, 21, 12, 0, 0, tzinfo=timezone.utc)
# 6-month mark: 2026-03-25; 3-month mark: 2026-06-23.


def _obs(
    rate: float,
    observed_at: str,
    *,
    row_id: int | None = None,
    source: RateSource = RateSource.FRED,
) -> RateObservation:
    return RateObservation(
        currency="USD",
        rate=rate,
        observed_at=observed_at,
        source=source,
        fetched_at="2026-09-21T01:00:00Z",
        id=row_id,
    )


class TestDeriveRatePath:
    def test_two_observations_around_the_mark_give_the_change(self):
        path = derive_rate_path(
            [
                _obs(5.50, "2026-09-21"),
                _obs(5.00, "2026-03-25"),  # exactly the 6-month mark
            ],
            now=_NOW,
        )

        assert isinstance(path, RatePath)
        assert path.rate_now == 5.50
        assert path.rate_then == 5.00
        assert path.change == 5.50 - 5.00

    def test_only_one_observation_leaves_the_path_none(self):
        path = derive_rate_path([_obs(5.50, "2026-09-21")], now=_NOW)

        assert path.rate_now == 5.50
        assert path.rate_then is None
        assert path.change is None

    def test_no_observation_is_all_none(self):
        path = derive_rate_path([], now=_NOW)

        assert (path.rate_now, path.rate_then, path.change) == (None, None, None)

    def test_reference_is_the_observation_nearest_the_mark(self):
        path = derive_rate_path(
            [
                _obs(5.50, "2026-09-21"),
                _obs(4.00, "2026-03-20"),  # 5 days before the mark
                _obs(3.00, "2026-04-05"),  # 11 days after -> not chosen
            ],
            now=_NOW,
        )

        assert path.rate_then == 4.00
        assert path.change == 5.50 - 4.00

    def test_reference_after_the_mark_is_used_when_nearest(self):
        path = derive_rate_path(
            [
                _obs(5.50, "2026-09-21"),
                _obs(3.00, "2026-02-01"),  # far before
                _obs(4.00, "2026-04-01"),  # 7 days after -> nearest
            ],
            now=_NOW,
        )

        assert path.rate_then == 4.00

    def test_a_reference_on_the_latest_date_does_not_count(self):
        # Two rows share the newest date -> no distinct older date -> None (B4).
        path = derive_rate_path(
            [
                _obs(5.50, "2026-09-21", row_id=1),
                _obs(5.40, "2026-09-21", row_id=2),
            ],
            now=_NOW,
        )

        assert path.rate_then is None
        assert path.change is None

    def test_months_parameter_moves_the_mark(self):
        observations = [
            _obs(5.50, "2026-09-21"),
            _obs(5.00, "2026-06-23"),  # exactly the 3-month mark
        ]

        assert derive_rate_path(observations, now=_NOW, months=3).change == 0.50
        # the 6-month mark (2026-03-25) is nearer the latest than 2026-06-23?
        # no: 2026-06-23 is 90 days from now, 2026-03-25 is 180 -> 6m picks 06-23
        assert derive_rate_path(observations, now=_NOW, months=6).rate_then == 5.00

    def test_is_deterministic_and_independent_of_input_order(self):
        observations = [
            _obs(5.50, "2026-09-21", row_id=3),
            _obs(5.00, "2026-03-25", row_id=1),
            _obs(4.00, "2026-01-01", row_id=2),
        ]
        assert derive_rate_path(observations, now=_NOW) == derive_rate_path(
            list(reversed(observations)), now=_NOW
        )


class TestRateTrendLayerBoundary:
    @classmethod
    def _source(cls) -> str:
        return _RATE_TREND_PY.read_text(encoding="utf-8")

    def test_derive_rate_path_signature(self):
        sig = inspect.signature(derive_rate_path)
        assert list(sig.parameters) == ["observations", "now", "months"]
        assert sig.parameters["months"].default == 6
        assert typing.get_type_hints(derive_rate_path)["return"] is RatePath

    def test_module_source_is_ascii(self):
        assert self._source().isascii()

    def test_module_imports_only_stdlib_and_core_news_models(self):
        tree = ast.parse(self._source())
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
            elif isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
        modules.discard("__future__")
        assert modules <= {"enum", "dataclasses", "datetime", "core.news_models"}
