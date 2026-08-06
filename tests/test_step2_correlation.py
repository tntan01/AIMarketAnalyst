"""Test script for Step 2 — Expand correlation to EUR/GBP/AUD/NZD/CAD USD pairs.

Usage: python tests/test_step2_correlation.py
"""

from __future__ import annotations

from unittest.mock import patch

from core.correlation_check import _us10y_score, _us2y_score, _dxy_score, compute_correlation_adjustment
from core.market_models import Candle


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _candles(closes: list[float]) -> list[Candle]:
    """Build candles with given closes."""
    return [Candle(time=None, open=c, high=c, low=c, close=c, volume=0) for c in closes]


# ---------------------------------------------------------------------------
# _us10y_score — existing behavior preserved
# ---------------------------------------------------------------------------


def test_us10y_xau_sell_when_yield_up_positive():
    """XAU/USD SELL + yield up -> directional +2 (existing behavior)."""
    score = _us10y_score("sell", "XAU/USD", _candles([4.0, 4.5]))
    # directional=2 * 0.6 + level=0 + momentum=0 = 1.2
    assert score > 0


def test_us10y_xau_buy_when_yield_up_negative():
    """XAU/USD BUY + yield up -> directional -3 (existing behavior)."""
    score = _us10y_score("buy", "XAU/USD", _candles([4.0, 4.5]))
    # directional=-3 * 0.6 + ... = -1.8
    assert score < 0


def test_us10y_none_candles_returns_zero():
    assert _us10y_score("buy", "EUR/USD", None) == 0.0


def test_us10y_empty_candles_returns_zero():
    assert _us10y_score("buy", "EUR/USD", []) == 0.0


def test_us10y_single_candle_returns_zero():
    assert _us10y_score("buy", "EUR/USD", _candles([4.0])) == 0.0


def test_us10y_non_usd_pair_returns_zero():
    """EUR/GBP has no USD -> returns 0."""
    assert _us10y_score("buy", "EUR/GBP", _candles([4.0, 4.5])) == 0.0


# ---------------------------------------------------------------------------
# _us10y_score — NEW: XXX/USD pairs
# ---------------------------------------------------------------------------


def test_eurusd_us10y_tang_sell_duoc_thuong():
    """SELL EUR/USD when US10Y rising = favorable -> +1.5."""
    score = _us10y_score("sell", "EUR/USD", _candles([4.0, 4.5]))
    assert score == 1.5


def test_eurusd_us10y_giam_buy_duoc_thuong():
    """BUY EUR/USD when US10Y falling = favorable -> +1.5."""
    score = _us10y_score("buy", "EUR/USD", _candles([4.5, 4.0]))
    assert score == 1.5


def test_eurusd_us10y_tang_buy_bi_phat():
    """BUY EUR/USD when US10Y rising = against -> -1.5."""
    score = _us10y_score("buy", "EUR/USD", _candles([4.0, 4.5]))
    assert score == -1.5


def test_eurusd_us10y_giam_sell_bi_phat():
    """SELL EUR/USD when US10Y falling = against -> -1.5."""
    score = _us10y_score("sell", "EUR/USD", _candles([4.5, 4.0]))
    assert score == -1.5


def test_gbpusd_us10y_tang_sell_duoc_thuong():
    score = _us10y_score("sell", "GBP/USD", _candles([4.0, 4.5]))
    assert score == 1.5


def test_audusd_us10y_giam_buy_duoc_thuong():
    score = _us10y_score("buy", "AUD/USD", _candles([4.5, 4.0]))
    assert score > 0


def test_nzdusd_us10y_tang_sell_duoc_thuong():
    score = _us10y_score("sell", "NZD/USD", _candles([4.0, 4.5]))
    assert score == 1.5


def test_cadusd_us10y_giam_buy_duoc_thuong():
    score = _us10y_score("buy", "CAD/USD", _candles([4.5, 4.0]))
    assert score == 1.5


def test_us10y_xxxusd_flat_yield_no_tiers_2_3():
    """XXX/USD pairs skip Tier 2 and 3 — return directional only (1.5 or -1.5)."""
    # 5 candles with large weekly change — but for XXX/USD, only Tier 1 applies
    score = _us10y_score("sell", "EUR/USD", _candles([4.0, 4.5, 5.0, 5.5, 6.0]))
    assert score == 1.5  # not affected by absolute level or momentum


def test_us10y_absolute_level_dung_loi_suat_phan_tram():
    """Tier 2 so sánh trực tiếp trên giá trị close (^TNX đã là lợi suất %)."""
    # 4.4%: dưới ngưỡng 4.5 -> không phạt
    assert _us10y_score("sell", "XAU/USD", _candles([4.0, 4.4])) == 1.2
    # 5.6%: trên 5.5 -> phạt -2 * 0.25
    assert _us10y_score("sell", "XAU/USD", _candles([4.0, 5.6])) == 0.7


def test_us10y_momentum_dung_loi_suat_phan_tram():
    """Tier 3 tính biến động 5 ngày trên giá trị close (^TNX đã là lợi suất %)."""
    # change 0.3%: không vượt 0.3 -> momentum 0
    assert _us10y_score("sell", "XAU/USD", _candles([4.0, 4.1, 4.2, 4.2, 4.3])) == 1.2
    # change 0.6%: vượt 0.5 -> momentum -2 * 0.15
    assert _us10y_score("sell", "XAU/USD", _candles([3.8, 4.0, 4.1, 4.2, 4.4])) == 0.9


# ---------------------------------------------------------------------------
# _us2y_score — NEW: XXX/USD pairs
# ---------------------------------------------------------------------------


def test_eurusd_us2y_tang_sell_duoc_thuong():
    """SELL EUR/USD when US2Y rising = favorable -> +1.0 (weaker than US10Y)."""
    score = _us2y_score("sell", "EUR/USD", _candles([3.0, 3.5]))
    assert score == 1.0


def test_eurusd_us2y_giam_buy_duoc_thuong():
    score = _us2y_score("buy", "EUR/USD", _candles([3.5, 3.0]))
    assert score == 1.0


def test_eurusd_us2y_tang_buy_bi_phat():
    score = _us2y_score("buy", "EUR/USD", _candles([3.0, 3.5]))
    assert score == -1.0


def test_audusd_us2y_giam_buy_duoc_thuong():
    score = _us2y_score("buy", "AUD/USD", _candles([3.5, 3.0]))
    assert score == 1.0


def test_us2y_xxxusd_no_tiers_2_3():
    """XXX/USD pairs skip Tier 2 and 3 for US2Y as well."""
    score = _us2y_score("sell", "GBP/USD", _candles([3.0, 3.5, 4.0, 4.5, 5.0]))
    assert score == 1.0


def test_us2y_non_usd_pair_returns_zero():
    assert _us2y_score("buy", "EUR/GBP", _candles([3.0, 3.5])) == 0.0


def test_us2y_none_candles_returns_zero():
    assert _us2y_score("buy", "EUR/USD", None) == 0.0


# ---------------------------------------------------------------------------
# _dxy_score — verify existing logic unchanged
# ---------------------------------------------------------------------------


def test_dxy_eurusd_sell_buy_usd_true():
    """SELL EUR/USD = buy USD -> usd_bullish. DXY up -> aligned."""
    score = _dxy_score("sell", "EUR/USD", _candles([100.0, 101.0]))
    assert score > 0


def test_dxy_eurusd_buy_buy_usd_false():
    """BUY EUR/USD = sell USD -> not usd_bullish. DXY up -> against."""
    score = _dxy_score("buy", "EUR/USD", _candles([100.0, 101.0]))
    assert score < 0


def test_dxy_change_below_01_percent_returns_zero():
    """Dead zone: biến động < 0.1% chỉ là nhiễu -> 0 điểm, không thưởng không phạt."""
    # 0.05% change (100.0 -> 100.05), aligned hướng nhưng vẫn bị triệt điểm
    assert _dxy_score("sell", "EUR/USD", _candles([100.0, 100.05])) == 0.0
    # 0.05% change, ngược hướng -> cũng không phạt
    assert _dxy_score("buy", "EUR/USD", _candles([100.0, 100.05])) == 0.0
    # 0.2% change: trên dead zone -> vẫn chấm điểm (+1)
    assert _dxy_score("sell", "EUR/USD", _candles([100.0, 100.2])) > 0


# ---------------------------------------------------------------------------
# compute_correlation_adjustment — nhóm USD kẹp trong [-6, +5], VIX ngoài
# ---------------------------------------------------------------------------


def test_corr_adj_usd_group_clamped_at_minus_6():
    """Cả DXY + US10Y + US2Y phạt nặng cùng lúc -> tổng USD không vượt quá -6."""
    # DXY down ~2%: -5; US10Y down: -1.5; US2Y down: -1.0 -> raw -7.5, kẹp -6
    result = compute_correlation_adjustment(
        "EUR/USD", "sell",
        dxy_candles=_candles([101.0, 99.0]),
        us10y_candles=_candles([4.5, 4.0]),
        us2y_candles=_candles([4.0, 3.5]),
    )
    assert result == -6.0


def test_corr_adj_usd_group_clamped_at_plus_5():
    """Cả DXY + US10Y + US2Y thưởng cùng lúc -> tổng USD không vượt quá +5."""
    # DXY up ~2%: +3; US10Y up: +1.5; US2Y up: +1.0 -> raw +5.5, kẹp +5
    result = compute_correlation_adjustment(
        "EUR/USD", "sell",
        dxy_candles=_candles([99.0, 101.0]),
        us10y_candles=_candles([4.0, 4.5]),
        us2y_candles=_candles([3.5, 4.0]),
    )
    assert result == 5.0


def test_corr_adj_vix_not_affected_by_usd_clamp():
    """VIX nằm ngoài giới hạn: vẫn cộng thêm ngoài khoảng [-6, +5]."""
    # USD nhóm kẹp -6, VIX > 25 = -5 -> tổng -11 (dưới -6 vẫn được)
    result = compute_correlation_adjustment(
        "EUR/USD", "sell",
        dxy_candles=_candles([101.0, 99.0]),
        us10y_candles=_candles([4.5, 4.0]),
        us2y_candles=_candles([4.0, 3.5]),
        vix_candles=_candles([30.0]),
    )
    assert result == -11.0
    # USD nhóm kẹp +5, VIX < 15 = +2 -> tổng +7 (trên +5 vẫn được)
    result = compute_correlation_adjustment(
        "EUR/USD", "sell",
        dxy_candles=_candles([99.0, 101.0]),
        us10y_candles=_candles([4.0, 4.5]),
        us2y_candles=_candles([3.5, 4.0]),
        vix_candles=_candles([10.0]),
    )
    assert result == 7.0


# ---------------------------------------------------------------------------
# edge cases
# ---------------------------------------------------------------------------


def test_us10y_case_insensitive():
    score = _us10y_score("sell", "eur/usd", _candles([4.0, 4.5]))
    assert score == 1.5


def test_us2y_case_insensitive():
    score = _us2y_score("buy", "gbp/usd", _candles([3.5, 3.0]))
    assert score == 1.0


def test_us10y_xau_usd_still_uses_original_logic():
    """XAU/USD still goes through precious metals path, not the generic /USD path."""
    # SELL XAU/USD + yield up -> favorable (original logic, directional=2)
    score = _us10y_score("sell", "XAU/USD", _candles([4.0, 4.5]))
    # directional=2 * 0.6 = 1.2 (not 1.5 from the generic /USD block)
    assert score == 1.2


def test_us10y_zero_prev_close_edge_case():
    """prev close <= 0 should be handled safely (division by zero)."""
    # yfinance data occasionally has zero values
    candles = [Candle(time=None, open=0, high=0, low=0, close=0, volume=0),
               Candle(time=None, open=4.0, high=4.0, low=4.0, close=4.0, volume=0)]
    score = _us10y_score("sell", "EUR/USD", candles)
    # y_up = 4.0 > 0.0 = True -> SELL + y_up -> 1.5
    assert score == 1.5


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    tests = [
        # _us10y_score — existing
        test_us10y_xau_sell_when_yield_up_positive,
        test_us10y_xau_buy_when_yield_up_negative,
        test_us10y_none_candles_returns_zero,
        test_us10y_empty_candles_returns_zero,
        test_us10y_single_candle_returns_zero,
        test_us10y_non_usd_pair_returns_zero,
        # _us10y_score — new XXX/USD
        test_eurusd_us10y_tang_sell_duoc_thuong,
        test_eurusd_us10y_giam_buy_duoc_thuong,
        test_eurusd_us10y_tang_buy_bi_phat,
        test_eurusd_us10y_giam_sell_bi_phat,
        test_gbpusd_us10y_tang_sell_duoc_thuong,
        test_audusd_us10y_giam_buy_duoc_thuong,
        test_nzdusd_us10y_tang_sell_duoc_thuong,
        test_cadusd_us10y_giam_buy_duoc_thuong,
        test_us10y_xxxusd_flat_yield_no_tiers_2_3,
        test_us10y_absolute_level_dung_loi_suat_phan_tram,
        test_us10y_momentum_dung_loi_suat_phan_tram,
        # _us2y_score — new XXX/USD
        test_eurusd_us2y_tang_sell_duoc_thuong,
        test_eurusd_us2y_giam_buy_duoc_thuong,
        test_eurusd_us2y_tang_buy_bi_phat,
        test_audusd_us2y_giam_buy_duoc_thuong,
        test_us2y_xxxusd_no_tiers_2_3,
        test_us2y_non_usd_pair_returns_zero,
        test_us2y_none_candles_returns_zero,
        # _dxy_score — verify
        test_dxy_eurusd_sell_buy_usd_true,
        test_dxy_eurusd_buy_buy_usd_false,
        test_dxy_change_below_01_percent_returns_zero,
        # compute_correlation_adjustment — clamp
        test_corr_adj_usd_group_clamped_at_minus_6,
        test_corr_adj_usd_group_clamped_at_plus_5,
        test_corr_adj_vix_not_affected_by_usd_clamp,
        # edge cases
        test_us10y_case_insensitive,
        test_us2y_case_insensitive,
        test_us10y_xau_usd_still_uses_original_logic,
        test_us10y_zero_prev_close_edge_case,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"PASS  {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"FAIL  {test.__name__}: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} PASS, {failed} FAIL out of {len(tests)}")
    sys.exit(0 if failed == 0 else 1)
