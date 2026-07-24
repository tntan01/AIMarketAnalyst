"""Phase-4 contracts for side-aware multi-timeframe SMC confluence."""

from __future__ import annotations

import core.smc_context as smc_context_module
from core.smc_confluence import build_directional_confluence
from core.smc_context import _cross_validate_structure, build_smc_context
from core.smc_models import DirectionalConfluence
from core.smc_versions import SMC_CONFLUENCE_VERSION


def _tf(
    structure: str,
    *,
    bos: bool = False,
    choch: bool = False,
    choch_confirmed: bool = False,
    displacement: str = "neutral",
) -> dict:
    return {
        "structure": structure,
        "bos": bos,
        "choch": choch,
        "choch_confirmed": choch_confirmed,
        "displacement": displacement,
    }


def _build(d1: dict, h4: dict, h1: dict) -> DirectionalConfluence:
    legacy = _cross_validate_structure(d1, h4, h1)
    return build_directional_confluence(
        d1,
        h4,
        h1,
        legacy_score=legacy["confluence_score"],
    )


def test_all_bullish_only_rewards_buy_side():
    result = _build(
        _tf("HH/HL"),
        _tf("HH/HL", bos=True, displacement="bullish"),
        _tf("HH/HL", bos=True, displacement="bullish"),
    )
    payload = result.to_dict()

    assert result.direction == "bullish"
    assert result.buy_score == 5
    assert result.sell_score == 0
    assert result.all_aligned is True
    assert result.h1_relationship == "aligned"
    assert "BUY_ALL_TIMEFRAMES_ALIGNED" in result.buy_reason_codes
    assert result.sell_reason_codes == ()
    assert payload["timeframe_evidence"]["D1"]["direction"] == "buy"
    assert payload["timeframe_evidence"]["H4"]["bos"] is True


def test_all_bearish_only_rewards_sell_side():
    result = _build(
        _tf("LH/LL"),
        _tf("LH/LL", bos=True, displacement="bearish"),
        _tf("LH/LL", bos=True, displacement="bearish"),
    )

    assert result.direction == "bearish"
    assert result.buy_score == 0
    assert result.sell_score == 5
    assert result.all_aligned is True
    assert "SELL_ALL_TIMEFRAMES_ALIGNED" in result.sell_reason_codes
    assert result.buy_reason_codes == ()


def test_mirrored_structure_produces_mirrored_scores():
    bullish = _build(
        _tf("HH/HL"),
        _tf("HH/HL"),
        _tf("LH/LL"),
    )
    bearish = _build(
        _tf("LH/LL"),
        _tf("LH/LL"),
        _tf("HH/HL"),
    )

    assert bullish.buy_score == bearish.sell_score
    assert bullish.sell_score == bearish.buy_score
    assert bullish.direction == "bullish"
    assert bearish.direction == "bearish"
    assert bullish.h1_relationship == bearish.h1_relationship == "pullback"


def test_unknown_timeframes_do_not_generate_points():
    result = _build(
        _tf("insufficient_data"),
        _tf("unknown"),
        _tf("insufficient_data"),
    )

    assert result.direction == "unknown"
    assert result.buy_score == 0
    assert result.sell_score == 0
    assert result.data_status == "insufficient"
    assert "INSUFFICIENT_TIMEFRAME_DATA" in result.reason_codes


def test_h1_pullback_does_not_reward_counter_side():
    result = _build(
        _tf("HH/HL"),
        _tf("HH/HL", bos=True, displacement="bullish"),
        _tf("LH/LL", displacement="neutral"),
    )

    assert result.buy_score == 2
    assert result.sell_score == 0
    assert result.h1_against_h4 is True
    assert result.h1_relationship == "pullback"
    assert "BUY_H1_PULLBACK_AGAINST_H4" in result.buy_reason_codes


def test_confirmed_h1_reversal_is_side_specific_early_evidence():
    result = _build(
        _tf("HH/HL"),
        _tf("HH/HL", bos=True, displacement="bullish"),
        _tf(
            "LH/LL",
            choch=True,
            choch_confirmed=True,
            displacement="bearish",
        ),
    )

    assert result.buy_score == 2
    assert result.sell_score == 1
    assert result.h1_relationship == "reversal"
    assert "BUY_H1_REVERSAL_RISK" in result.buy_reason_codes
    assert "SELL_H1_REVERSAL_SIGNAL" in result.sell_reason_codes


def test_partial_data_scores_only_observed_alignment():
    result = _build(
        _tf("insufficient_data"),
        _tf("HH/HL"),
        _tf("HH/HL"),
    )

    assert result.buy_score == 2
    assert result.sell_score == 0
    assert result.data_status == "partial"
    assert result.d1_h4_aligned is False
    assert result.h4_h1_aligned is True


def test_legacy_score_and_canonical_evidence_round_trip():
    result = _build(
        _tf("LH/LL"),
        _tf("LH/LL"),
        _tf("LH/LL"),
    )
    payload = result.to_dict(include_compatibility=True)
    restored = DirectionalConfluence.from_legacy_dict(payload)

    assert payload["confluence_score"] == 5
    assert result.legacy_score == 5
    assert restored == result
    assert restored.confluence_version == SMC_CONFLUENCE_VERSION
    assert [item.timeframe for item in restored.timeframe_evidence] == [
        "D1",
        "H4",
        "H1",
    ]


def test_build_smc_context_exposes_directional_and_legacy_contracts(
    monkeypatch,
):
    timeframe_results = iter([
        _tf("HH/HL"),
        _tf("HH/HL", bos=True, displacement="bullish"),
        _tf("HH/HL", bos=True, displacement="bullish"),
    ])
    monkeypatch.setattr(
        smc_context_module,
        "_smc_for_timeframe",
        lambda *args, **kwargs: next(timeframe_results),
    )

    context = build_smc_context([], [], [], symbol="EUR/USD")
    confluence = context["confluence"]

    assert confluence["buy_score"] == 5
    assert confluence["sell_score"] == 0
    assert confluence["direction"] == "bullish"
    assert confluence["confluence_score"] == 5
    assert set(confluence["timeframe_evidence"]) == {"D1", "H4", "H1"}
