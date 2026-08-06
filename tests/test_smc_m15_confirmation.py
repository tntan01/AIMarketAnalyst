"""M15 confirmation at the selected SMC zone.

The evaluator checks the M15 window for a small-timeframe CHoCH or a clear
price reaction at the zone; the scorer turns the outcome into penalty points
(only for a tested-but-unconfirmed zone) and reason codes for every status.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.analysis_engine import analyze_symbol
from core.market_models import Candle
from core.smc_m15_confirmation import (
    M15_CONFIRMATION_REASON,
    M15_INSUFFICIENT_DATA_REASON,
    M15_NO_CONFIRMATION_REASON,
    M15_ZONE_NOT_TESTED_REASON,
    evaluate_m15_confirmation,
)
from core.smc_prefilter import (
    NO_ACTIONABLE_SMC_ZONE,
    evaluate_post_context_prefilter,
)
from core.smc_scorer import score_smc
from tests.test_analysis_pipeline_integration import (
    _build_candles_by_timeframe,
    _default_input,
)
from tests.test_smc_scorer import _smc, _technical


_REGIME = {"primary": "trend_up"}
_TIME0 = datetime(2026, 8, 6, tzinfo=timezone.utc)

# The shared scorer fixtures select the buy zone [90, 95] and the sell
# zone [105, 110].
_BUY_ZONE = (90.0, 95.0)
_SELL_ZONE = (105.0, 110.0)


def _candle(index: int, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        time=_TIME0 + timedelta(minutes=15 * index),
        open=open_,
        high=high,
        low=low,
        close=close,
    )


def _descent(count: int, start: float, step: float) -> list[Candle]:
    candles: list[Candle] = []
    price = start
    for index in range(count):
        open_ = price
        close = price - step
        candles.append(_candle(index, open_, open_ + 0.05, close - 0.05, close))
        price = close
    return candles


def _ascent(count: int, start: float, step: float) -> list[Candle]:
    candles: list[Candle] = []
    price = start
    for index in range(count):
        open_ = price
        close = price + step
        candles.append(_candle(index, open_, close + 0.05, open_ - 0.05, close))
        price = close
    return candles


def _candles_from_lows(
    start_index: int,
    lows: list[float],
    *,
    bullish: bool = True,
    body: float = 0.15,
) -> list[Candle]:
    candles: list[Candle] = []
    for offset, low in enumerate(lows):
        index = start_index + offset
        if bullish:
            open_ = low
            close = low + body
        else:
            open_ = low + body
            close = low
        candles.append(_candle(index, open_, max(open_, close) + 0.02, low, close))
    return candles


def _stagnation_at_zone() -> list[Candle]:
    """Price drops into the demand zone and stalls without any reaction."""

    candles = _descent(30, 100.0, 0.25)
    for offset in range(18):
        index = 30 + offset
        candles.append(_candle(index, 92.52, 92.53, 92.47, 92.48))
    return candles


def _stagnation_at_supply() -> list[Candle]:
    """Price rises into the supply zone and stalls without any reaction."""

    candles = _ascent(30, 100.0, 0.25)
    for offset in range(18):
        index = 30 + offset
        candles.append(_candle(index, 107.48, 107.53, 107.47, 107.52))
    return candles


def _rejection_at_zone() -> list[Candle]:
    """Price drops into the demand zone and prints a bullish rejection wick."""

    candles = _descent(30, 100.0, 0.25)
    candles.append(_candle(30, 92.5, 93.1, 91.0, 93.0))
    candles.append(_candle(31, 93.0, 93.2, 92.8, 93.1))
    return candles


def _choch_at_zone() -> list[Candle]:
    """Zone touch followed by a higher-low micro structure shift (CHoCH).

    No rejection wick (bullish candles open at their low) and no
    displacement body in the last candles, so only the CHoCH path can fire.
    """

    candles = _descent(26, 100.0, 0.25)
    rally = [93.6, 93.8, 94.0, 94.2, 94.4, 94.6, 94.8]
    pullback = [94.5, 94.3, 94.1, 94.0]
    resume = [94.2, 94.4, 94.6, 94.7, 94.75, 94.8, 94.82, 94.85]
    tail = [94.86, 94.87, 94.88]
    candles += _candles_from_lows(26, rally, body=0.15)
    candles += _candles_from_lows(33, pullback, bullish=False, body=0.1)
    candles += _candles_from_lows(37, resume, body=0.02)
    candles += _candles_from_lows(45, tail, body=0.02)
    return candles


def _displacement_at_zone() -> list[Candle]:
    """Zone touch followed by a strong bullish displacement candle."""

    candles = _descent(44, 100.0, 0.12)
    base = candles[-1].close
    for offset in range(3):
        index = 44 + offset
        candles.append(_candle(index, base + 0.02, base + 0.03, base - 0.03, base - 0.02))
    candles.append(_candle(47, base - 0.05, base + 1.05, base - 0.05, base + 1.0))
    return candles


def _above_zone() -> list[Candle]:
    """Price stays well above the demand zone: the zone is never tested."""

    return [_candle(index, 105.1, 105.2, 104.9, 105.0) for index in range(48)]


# -- Evaluator statuses ------------------------------------------------------


def test_insufficient_m15_data_is_warning_only():
    assert evaluate_m15_confirmation("buy", *_BUY_ZONE, None)["status"] == "insufficient_data"
    assert evaluate_m15_confirmation("buy", *_BUY_ZONE, [])["status"] == "insufficient_data"

    short = _descent(10, 100.0, 0.25)
    result = evaluate_m15_confirmation("buy", *_BUY_ZONE, short)
    assert result["status"] == "insufficient_data"
    assert result["confirmed"] is False
    assert result["penalty"] == 0
    assert result["reason_codes"] == [M15_INSUFFICIENT_DATA_REASON]

    invalid_zone = evaluate_m15_confirmation("buy", 95.0, 90.0, _stagnation_at_zone())
    assert invalid_zone["status"] == "insufficient_data"
    invalid_side = evaluate_m15_confirmation("hold", *_BUY_ZONE, _stagnation_at_zone())
    assert invalid_side["status"] == "insufficient_data"


def test_zone_not_tested_traces_warning_without_penalty():
    result = evaluate_m15_confirmation("buy", *_BUY_ZONE, _above_zone())

    assert result["status"] == "zone_not_tested"
    assert result["confirmed"] is False
    assert result["penalty"] == 0
    assert result["reason_codes"] == [M15_ZONE_NOT_TESTED_REASON]


def test_tested_zone_without_confirmation_penalizes():
    result = evaluate_m15_confirmation("buy", *_BUY_ZONE, _stagnation_at_zone())

    assert result["status"] == "not_confirmed"
    assert result["confirmed"] is False
    assert result["penalty"] == 2
    assert result["reason_codes"] == [M15_NO_CONFIRMATION_REASON]
    assert result["choch"] is False
    assert result["reaction"] is False


def test_rejection_at_zone_confirms():
    result = evaluate_m15_confirmation("buy", *_BUY_ZONE, _rejection_at_zone())

    assert result["status"] == "confirmed"
    assert result["confirmed"] is True
    assert result["penalty"] == 0
    assert result["reason_codes"] == [M15_CONFIRMATION_REASON]
    assert result["reaction"] is True


def test_choch_after_zone_touch_confirms():
    result = evaluate_m15_confirmation("buy", *_BUY_ZONE, _choch_at_zone())

    assert result["status"] == "confirmed"
    assert result["choch"] is True
    assert result["reaction"] is False
    assert result["penalty"] == 0


def test_displacement_away_from_zone_confirms():
    result = evaluate_m15_confirmation("buy", *_BUY_ZONE, _displacement_at_zone())

    assert result["status"] == "confirmed"
    assert result["choch"] is False
    assert result["reaction"] is True


def test_sell_side_confirmation_is_mirrored():
    candles = _ascent(30, 100.0, 0.25)
    # Bearish rejection wick at the supply zone.
    candles.append(_candle(30, 107.5, 109.0, 107.4, 107.0))
    candles.append(_candle(31, 107.0, 107.2, 106.6, 106.8))

    result = evaluate_m15_confirmation("sell", *_SELL_ZONE, candles)

    assert result["status"] == "confirmed"
    assert result["reaction"] is True

    unconfirmed = evaluate_m15_confirmation("sell", *_SELL_ZONE, _stagnation_at_supply())
    assert unconfirmed["status"] == "not_confirmed"
    assert unconfirmed["penalty"] == 2


# -- Scorer integration ------------------------------------------------------


def test_score_smc_without_m15_is_unchanged():
    baseline = score_smc(_smc("buy"), _technical("buy"), _REGIME).side("buy")

    explicit_none = score_smc(
        _smc("buy"),
        _technical("buy"),
        _REGIME,
        m15_candles=None,
    ).side("buy")

    assert explicit_none.score == baseline.score
    assert explicit_none.breakdown == baseline.breakdown


def test_missing_m15_confirmation_deducts_points():
    baseline = score_smc(_smc("buy"), _technical("buy"), _REGIME).side("buy")

    side = score_smc(
        _smc("buy"),
        _technical("buy"),
        _REGIME,
        m15_candles=_stagnation_at_zone(),
    ).side("buy")

    assert side.score == baseline.score - 2
    assert side.breakdown["subtotal"] == baseline.breakdown["subtotal"]
    assert (
        side.breakdown["penalty_points"]
        == baseline.breakdown["penalty_points"] + 2
    )
    assert M15_NO_CONFIRMATION_REASON in side.breakdown["penalties"]
    assert M15_NO_CONFIRMATION_REASON in side.breakdown["reason_codes"]


def test_m15_confirmation_never_adds_points():
    baseline = score_smc(_smc("buy"), _technical("buy"), _REGIME).side("buy")

    side = score_smc(
        _smc("buy"),
        _technical("buy"),
        _REGIME,
        m15_candles=_choch_at_zone(),
    ).side("buy")

    assert side.score == baseline.score
    assert (
        side.breakdown["penalty_points"]
        == baseline.breakdown["penalty_points"]
    )
    assert M15_CONFIRMATION_REASON in side.breakdown["reason_codes"]
    assert M15_CONFIRMATION_REASON not in side.breakdown["penalties"]


def test_zone_not_tested_and_insufficient_trace_warning_only():
    baseline = score_smc(_smc("buy"), _technical("buy"), _REGIME).side("buy")

    cases = (
        (_above_zone(), M15_ZONE_NOT_TESTED_REASON),
        (_descent(10, 100.0, 0.25), M15_INSUFFICIENT_DATA_REASON),
    )
    for candles, expected_code in cases:
        side = score_smc(
            _smc("buy"),
            _technical("buy"),
            _REGIME,
            m15_candles=candles,
        ).side("buy")
        assert side.score == baseline.score
        assert (
            side.breakdown["penalty_points"]
            == baseline.breakdown["penalty_points"]
        )
        assert expected_code in side.breakdown["reason_codes"]
        assert expected_code not in side.breakdown["penalties"]


def test_sell_side_missing_confirmation_deducts_points():
    baseline = score_smc(_smc("sell"), _technical("sell"), _REGIME).side("sell")

    side = score_smc(
        _smc("sell"),
        _technical("sell"),
        _REGIME,
        m15_candles=_stagnation_at_supply(),
    ).side("sell")

    assert side.score == baseline.score - 2
    assert M15_NO_CONFIRMATION_REASON in side.breakdown["penalties"]


def test_side_without_selected_zone_skips_m15():
    baseline = score_smc(_smc("buy"), _technical("buy"), _REGIME).side("sell")

    sell_side = score_smc(
        _smc("buy"),
        _technical("buy"),
        _REGIME,
        m15_candles=_stagnation_at_zone(),
    ).side("sell")

    assert sell_side.score == baseline.score
    assert sell_side.breakdown == baseline.breakdown
    assert M15_NO_CONFIRMATION_REASON not in sell_side.breakdown["reason_codes"]
    assert M15_CONFIRMATION_REASON not in sell_side.breakdown["reason_codes"]


def test_m15_penalty_keeps_existing_caps():
    context = _smc("buy", h4_choch_against=True)
    baseline = score_smc(context, _technical("buy"), _REGIME).side("buy")

    side = score_smc(
        context,
        _technical("buy"),
        _REGIME,
        m15_candles=_stagnation_at_zone(),
    ).side("buy")

    assert baseline.breakdown["applied_cap"] == 4
    assert side.breakdown["applied_cap"] == 4
    assert side.score <= 4
    assert M15_NO_CONFIRMATION_REASON in side.breakdown["penalties"]


# -- Wiring (prefilter + pipeline) -------------------------------------------


def test_prefilter_forwards_m15_candles_to_scorer():
    smc = _smc("buy")
    technical = _technical("buy")
    candles = _stagnation_at_zone()

    decision = evaluate_post_context_prefilter(
        smc=smc,
        technical=technical,
        market_regime=_REGIME,
        m15_candles=candles,
    )
    direct = score_smc(smc, technical, _REGIME, m15_candles=candles)

    assert decision["should_reject"] is False
    precomputed = decision["precomputed_smc"].side("buy")
    assert precomputed.score == direct.side("buy").score
    assert precomputed.breakdown == direct.side("buy").breakdown
    assert M15_NO_CONFIRMATION_REASON in precomputed.breakdown["reason_codes"]


def test_prefilter_without_m15_matches_plain_scorer():
    smc = _smc("buy")
    technical = _technical("buy")

    decision = evaluate_post_context_prefilter(
        smc=smc,
        technical=technical,
        market_regime=_REGIME,
    )
    plain = score_smc(smc, technical, _REGIME)

    assert (
        decision["precomputed_smc"].side("buy").breakdown
        == plain.side("buy").breakdown
    )


def test_prefilter_reject_decision_ignores_m15():
    empty_smc = {"symbol": "TEST", "H4": {}, "H1": {}}

    decision = evaluate_post_context_prefilter(
        smc=empty_smc,
        technical=_technical("buy"),
        m15_candles=_stagnation_at_zone(),
    )

    assert decision["should_reject"] is True
    assert decision["reason_code"] == NO_ACTIONABLE_SMC_ZONE


def test_pipeline_forwards_m15_candles_to_scorer(monkeypatch):
    from core import analysis_pipeline

    seen: dict[str, object] = {}
    real_score_smc = analysis_pipeline.score_smc

    def spy(smc, technical, market_regime=None, **kwargs):
        seen["m15_candles"] = kwargs.get("m15_candles")
        return real_score_smc(smc, technical, market_regime, **kwargs)

    monkeypatch.setattr(analysis_pipeline, "score_smc", spy)
    candles = _build_candles_by_timeframe(regime="trending_up")

    result = analyze_symbol(
        _default_input(),
        candles,
        m15_candles=candles["M15"],
    )

    assert result["analysis_status"] == "completed"
    assert seen["m15_candles"] is candles["M15"]
