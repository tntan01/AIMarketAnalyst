from __future__ import annotations

import pytest

from core.risk_engine import build_trade_plan
from core.smc_context import zone_matches_direction
from tests.test_entry_tp_quality_diagnostics import (
    _base_smc,
    _base_tech,
    _req,
    _swing,
    _zone,
    candles,
    m15,
)


def _order_block(
    zone_type: str,
    low: float,
    high: float,
    score: int,
) -> dict[str, object]:
    return {
        "type": zone_type,
        "low": low,
        "high": high,
        "zone_score": score,
        "strength": "strong",
        "stale": False,
        "mitigated": False,
        "broken": False,
        "test_count": 0,
        "freshness_bars": 1,
        "displacement_multiple": 1.5,
        "liquidity_sweep": False,
        "zone_location": (
            "discount" if zone_type.startswith("bullish") else "premium"
        ),
    }


def _build_fallback_plan(
    side: str,
    order_blocks: list[dict[str, object]],
    *,
    preferred_zone: dict[str, object] | None = None,
):
    if side == "buy":
        technical = _base_tech(
            1.1000,
            0.0020,
            [],
            [_zone(1.1060, 1.1050, 1.1070, "strong", 75)],
        )
        regime = "trend_up"
    else:
        technical = _base_tech(
            1.1000,
            0.0020,
            [_zone(1.0940, 1.0930, 1.0950, "strong", 75)],
            [],
        )
        regime = "trend_down"

    smc = _base_smc()
    smc["H4"]["order_blocks"] = order_blocks
    smc["H4"]["swings"] = {
        "highs": [_swing(1.1080, 10)],
        "lows": [_swing(1.0920, 5)],
    }
    return build_trade_plan(
        side,
        _req(),
        technical,
        smc,
        candles,
        m15_candles=m15,
        preferred_zone=preferred_zone,
        market_regime={"primary": regime},
    )


@pytest.mark.parametrize(
    ("side", "allowed", "rejected"),
    [
        (
            "buy",
            ("demand_zone", "bullish_order_block", "bullish_fvg"),
            ("supply_zone", "bearish_order_block", "bearish_fvg"),
        ),
        (
            "sell",
            ("supply_zone", "bearish_order_block", "bearish_fvg"),
            ("demand_zone", "bullish_order_block", "bullish_fvg"),
        ),
    ],
)
def test_directional_zone_family_contract(
    side: str,
    allowed: tuple[str, ...],
    rejected: tuple[str, ...],
) -> None:
    for zone_type in allowed:
        assert zone_matches_direction({"type": zone_type}, side)
    for zone_type in rejected:
        assert not zone_matches_direction({"type": zone_type}, side)


def test_usdcad_buy_repro_cannot_fallback_to_bearish_order_block() -> None:
    bearish = _order_block(
        "bearish_order_block",
        1.40801,
        1.40891,
        100,
    )
    distant_bullish_fvg = {
        **_order_block("bullish_fvg", 1.3900, 1.3910, 78),
        "level": 1.3905,
        "source": "smc_selected",
    }

    plan = _build_fallback_plan(
        "buy",
        [bearish],
        preferred_zone=distant_bullish_fvg,
    )

    assert plan is None


def test_fallback_selects_compatible_order_block_for_buy_and_sell() -> None:
    bullish = _order_block(
        "bullish_order_block",
        1.0960,
        1.0980,
        75,
    )
    bearish_below = _order_block(
        "bearish_order_block",
        1.0970,
        1.0990,
        100,
    )
    buy_plan = _build_fallback_plan(
        "buy",
        [bearish_below, bullish],
    )

    assert buy_plan is not None
    assert buy_plan["source_zone"]["zone_type"] == "bullish_order_block"

    bearish = _order_block(
        "bearish_order_block",
        1.1020,
        1.1040,
        75,
    )
    bullish_above = _order_block(
        "bullish_order_block",
        1.1010,
        1.1030,
        100,
    )
    sell_plan = _build_fallback_plan(
        "sell",
        [bullish_above, bearish],
    )

    assert sell_plan is not None
    assert sell_plan["source_zone"]["zone_type"] == "bearish_order_block"


def test_no_compatible_fallback_zone_returns_no_plan() -> None:
    buy_plan = _build_fallback_plan(
        "buy",
        [_order_block("bearish_order_block", 1.0970, 1.0990, 100)],
    )
    sell_plan = _build_fallback_plan(
        "sell",
        [_order_block("bullish_order_block", 1.1010, 1.1030, 100)],
    )

    assert buy_plan is None
    assert sell_plan is None
