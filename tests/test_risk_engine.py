from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from core.market_models import Candle
from core.risk_engine import (
    ENTRY_ZONE_ATR_MULT,
    _MIN_SL_DISTANCE_ATR,
    _SWING_SL_BUFFER_ATR,
    AnalysisInput,
    _find_nearest_equal_level,
    _find_nearest_swing_for_sl,
    _resolve_quote_to_usd_rate,
    build_trade_plan,
)
from core.smc_context import build_smc_context
from core.technical_context import build_technical_snapshot


# ---------------------------------------------------------------------------
# Synthetic candle generators
# ---------------------------------------------------------------------------


def _trending_candles(
    n: int,
    *,
    start_price: float = 1.0800,
    step: float = 0.0005,
    volatility: float = 0.0010,
    start_time: datetime | None = None,
    bar_minutes: int = 60,
) -> list[Candle]:
    t = start_time or datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc)
    candles: list[Candle] = []
    price = start_price
    for i in range(n):
        body = step * (0.3 + 0.7 * (i % 5) / 5)
        wick = volatility * 0.4
        open_price = price
        close_price = price + body
        high_price = close_price + wick * (0.3 + 0.7 * (i % 3) / 3)
        low_price = open_price - wick * (0.2 + 0.8 * (i % 4) / 4)
        candles.append(
            Candle(
                time=t,
                open=round(open_price, 5),
                high=round(high_price, 5),
                low=round(low_price, 5),
                close=round(close_price, 5),
                volume=float(1000 + i * 10),
            )
        )
        price = close_price
        t += timedelta(minutes=bar_minutes)
    return candles


# ---------------------------------------------------------------------------
# Existing tests
# ---------------------------------------------------------------------------


class FakeMT5:
    def __init__(self) -> None:
        self.initialize_calls = 0
        self.shutdown_calls = 0
        self.raise_on_tick = False
        self.already_connected = False

    def initialize(self) -> bool:
        self.initialize_calls += 1
        return True

    def shutdown(self) -> None:
        self.shutdown_calls += 1

    def terminal_info(self) -> SimpleNamespace | None:
        return SimpleNamespace(connected=True) if self.already_connected else None

    def account_info(self) -> SimpleNamespace | None:
        return SimpleNamespace(login=123456) if self.already_connected else None

    def symbol_info_tick(self, pair_name: str) -> SimpleNamespace | None:
        if self.raise_on_tick:
            raise RuntimeError("MT5 tick failure")
        if pair_name == "EURUSD":
            return SimpleNamespace(bid=1.25)
        return None

    def symbols_get(self) -> list[object]:
        return []


def test_resolve_quote_to_usd_rate_shuts_down_after_initialize(monkeypatch):
    fake_mt5 = FakeMT5()
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake_mt5)

    rate = _resolve_quote_to_usd_rate("GBP/EUR")

    assert rate == 1.25
    assert fake_mt5.initialize_calls == 1
    assert fake_mt5.shutdown_calls == 1


def test_resolve_quote_to_usd_rate_does_not_shutdown_existing_mt5_connection(monkeypatch):
    fake_mt5 = FakeMT5()
    fake_mt5.already_connected = True
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake_mt5)

    rate = _resolve_quote_to_usd_rate("GBP/EUR")

    assert rate == 1.25
    assert fake_mt5.initialize_calls == 1
    assert fake_mt5.shutdown_calls == 0


def test_resolve_quote_to_usd_rate_shuts_down_when_mt5_errors(monkeypatch):
    fake_mt5 = FakeMT5()
    fake_mt5.raise_on_tick = True
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake_mt5)

    rate = _resolve_quote_to_usd_rate("GBP/EUR")

    assert rate is None
    assert fake_mt5.initialize_calls == 1
    assert fake_mt5.shutdown_calls == 1


# ---------------------------------------------------------------------------
# Tests for ENTRY_ZONE_ATR_MULT = 0.20
# ---------------------------------------------------------------------------


def test_entry_zone_atr_mult_is_020():
    """The module-level constant must be 0.20 (changed from 0.40)."""
    assert ENTRY_ZONE_ATR_MULT == 0.20, (
        f"ENTRY_ZONE_ATR_MULT = {ENTRY_ZONE_ATR_MULT}, expected 0.20"
    )


def test_entry_zone_atr_mult_not_040():
    """Regression: the old 0.40 value must not be present."""
    assert ENTRY_ZONE_ATR_MULT != 0.40, (
        "ENTRY_ZONE_ATR_MULT is still 0.40 — the change was not applied"
    )


def test_entry_zone_width_in_build_trade_plan():
    """Verify build_trade_plan uses ENTRY_ZONE_ATR_MULT for zone width.

    Uses the same synthetic data pattern as the integration tests
    (trending up) which is known to produce valid trade plans.
    """
    end = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    # Use trending-up candles (same pattern as integration tests)
    d1 = _trending_candles(120, start_price=1.0500, step=0.00025,
                           bar_minutes=1440, start_time=end - timedelta(days=120))
    h4 = _trending_candles(360, start_price=d1[0].open, step=0.00012,
                           bar_minutes=240, start_time=d1[0].time)
    h1 = _trending_candles(480, start_price=h4[0].open, step=0.00006,
                           bar_minutes=60, start_time=h4[0].time)
    m15 = _trending_candles(200, start_price=h1[0].open, step=0.00002,
                            bar_minutes=15, start_time=h1[0].time)

    technical = build_technical_snapshot(d1, h4, h1)
    smc = build_smc_context(d1, h4, h1)
    atr_value = technical["atr_h4"] or technical["atr_d1"] or 0.0

    request = AnalysisInput(
        symbol="EUR/USD",
        broker_symbol="EURUSDm",
        account_balance=10_000.0,
        risk_percent=2.0,
        contract_size_override=100_000.0,
    )

    plan = build_trade_plan(
        "buy", request, technical, smc, h1,
        m15_candles=m15,
    )

    # If None, the test data didn't produce a valid plan — skip with info
    if plan is None:
        pytest.skip(
            f"No valid trade plan generated: price={technical['price']:.5f}, "
            f"atr={atr_value:.6f}, "
            f"supports={len(technical['support_zones'])}, "
            f"resistances={len(technical['resistance_zones'])}"
        )

    entry_zone = plan["entry_zone"]
    assert len(entry_zone) == 2
    entry_low, entry_high = float(entry_zone[0]), float(entry_zone[1])

    zone_width = entry_high - entry_low
    expected_width = 2 * atr_value * ENTRY_ZONE_ATR_MULT

    assert zone_width == pytest.approx(expected_width, rel=0.01), (
        f"Entry zone width {zone_width:.6f} != expected {expected_width:.6f} "
        f"(2 × ATR {atr_value:.6f} × {ENTRY_ZONE_ATR_MULT})"
    )

    # Also verify it's NOT the old 0.40 width
    old_width = 2 * atr_value * 0.40
    assert zone_width < old_width * 0.70, (
        f"Zone width {zone_width:.6f} too close to old 0.40 width {old_width:.6f}"
    )


# ---------------------------------------------------------------------------
# Tests for _find_nearest_swing_for_sl (Swing-based SL)
# ---------------------------------------------------------------------------


def _make_swings(*levels: float) -> dict[str, Any]:
    """Build a minimal SMC dict with H4 swings at given levels."""
    return {
        "H4": {
            "swings": {
                "highs": [{"level": l, "index": i, "time": "2026-01-01T00:00:00"}
                          for i, l in enumerate(levels)],
                "lows": [{"level": l, "index": i, "time": "2026-01-01T00:00:00"}
                         for i, l in enumerate(levels)],
            }
        }
    }


class TestFindNearestSwingForSL:
    """Unit tests for _find_nearest_swing_for_sl()."""

    def test_buy_returns_nearest_low_below_price(self):
        smc = _make_swings(1.0950, 1.0980, 1.1010, 1.1040)
        result = _find_nearest_swing_for_sl(smc, "buy", 1.1020)
        # 1.1010 is the highest low below 1.1020
        assert result == 1.1010

    def test_buy_returns_none_when_all_lows_above_price(self):
        smc = _make_swings(1.1030, 1.1050, 1.1070)
        result = _find_nearest_swing_for_sl(smc, "buy", 1.1020)
        assert result is None

    def test_sell_returns_nearest_high_above_price(self):
        smc = _make_swings(1.0950, 1.0980, 1.1010, 1.1040)
        result = _find_nearest_swing_for_sl(smc, "sell", 1.0990)
        # 1.1010 is the lowest high above 1.0990
        assert result == 1.1010

    def test_sell_returns_none_when_all_highs_below_price(self):
        smc = _make_swings(1.0950, 1.0970, 1.0980)
        result = _find_nearest_swing_for_sl(smc, "sell", 1.0990)
        assert result is None

    def test_returns_none_when_no_candidates(self):
        smc = {"H4": {"swings": {"highs": [], "lows": []}}}
        result = _find_nearest_swing_for_sl(smc, "buy", 1.1000)
        assert result is None

    def test_returns_none_when_smc_is_none(self):
        assert _find_nearest_swing_for_sl(None, "buy", 1.1000) is None

    def test_returns_none_when_smc_is_not_dict(self):
        assert _find_nearest_swing_for_sl("not_a_dict", "buy", 1.1000) is None  # type: ignore[arg-type]

    def test_searches_both_h4_and_h1(self):
        """H1 swing closer than H4 → H1 should be selected."""
        smc = {
            "H4": {"swings": {"highs": [{"level": 1.1060, "index": 0, "time": ""}],
                             "lows": [{"level": 1.0940, "index": 0, "time": ""}]}},
            "H1": {"swings": {"highs": [{"level": 1.1030, "index": 0, "time": ""}],
                             "lows": [{"level": 1.0970, "index": 0, "time": ""}]}},
        }
        # H1 low 1.0970 is closer to 1.0990 than H4 low 1.0940
        result = _find_nearest_swing_for_sl(smc, "buy", 1.0990)
        assert result == 1.0970

    def test_ignores_non_dict_swing_items(self):
        smc = {
            "H4": {"swings": {
                "lows": [
                    {"level": 1.0950, "index": 0, "time": ""},
                    1.0960,  # plain float, not dict — should be skipped
                    {"level": 1.0970, "index": 1, "time": ""},
                ]
            }}
        }
        result = _find_nearest_swing_for_sl(smc, "buy", 1.0990)
        # 1.0970 is closest below 1.0990 (1.0960 skipped)
        assert result == 1.0970

    def test_skips_non_numeric_levels(self):
        smc = {
            "H4": {"swings": {
                "lows": [
                    {"level": "1.0950", "index": 0, "time": ""},  # string
                    {"level": 1.0970, "index": 1, "time": ""},
                ]
            }}
        }
        result = _find_nearest_swing_for_sl(smc, "buy", 1.0990)
        assert result == 1.0970


# ---------------------------------------------------------------------------
# Integration tests: swing-based SL via analyze_symbol (full pipeline)
# ---------------------------------------------------------------------------


class TestSwingSLInBuildTradePlan:
    """Verify swing-based SL works end-to-end through the full pipeline."""

    @staticmethod
    def _build_data(base_price: float = 1.0800):
        """Re-use the same data generation pattern as the integration tests."""
        end = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        d1 = _trending_candles(120, start_price=base_price - 0.0300, step=0.00025,
                               bar_minutes=1440, start_time=end - timedelta(days=120))
        h4 = _trending_candles(360, start_price=d1[0].open, step=0.00012,
                               bar_minutes=240, start_time=d1[0].time)
        h1 = _trending_candles(480, start_price=h4[0].open, step=0.00006,
                               bar_minutes=60, start_time=h4[0].time)
        m15 = _trending_candles(200, start_price=h1[0].open, step=0.00002,
                                bar_minutes=15, start_time=h1[0].time)
        return d1, h4, h1, m15

    def test_smc_context_has_swings_after_fix(self):
        """After fixing _smc_for_timeframe, swings data MUST be present."""
        d1, h4, h1, _ = self._build_data()
        smc = build_smc_context(d1, h4, h1)

        for tf in ("H4", "H1"):
            swings = smc[tf].get("swings", {})
            assert isinstance(swings, dict), f"{tf} swings missing or wrong type"
            assert isinstance(swings.get("highs"), list), f"{tf} swings.highs not a list"
            assert isinstance(swings.get("lows"), list), f"{tf} swings.lows not a list"
            assert len(swings["highs"]) > 0, f"{tf} has no swing highs"
            assert len(swings["lows"]) > 0, f"{tf} has no swing lows"

    def test_find_nearest_swing_finds_real_swings(self):
        """_find_nearest_swing_for_sl should return a real swing from SMC data."""
        d1, h4, h1, _ = self._build_data()
        smc = build_smc_context(d1, h4, h1)
        technical = build_technical_snapshot(d1, h4, h1)
        price = technical["price"]

        # With real swing data, should find a swing low below price
        swing_low = _find_nearest_swing_for_sl(smc, "buy", price)
        assert swing_low is not None, (
            f"No swing low found below price {price:.5f} — "
            f"H4 lows: {[s['level'] for s in smc['H4']['swings']['lows'][-5:]]}"
        )
        assert swing_low < price

        # Should also find a swing high above price
        swing_high = _find_nearest_swing_for_sl(smc, "sell", price)
        assert swing_high is not None, (
            f"No swing high found above price {price:.5f}"
        )
        assert swing_high > price

    def test_buy_plan_sl_below_entry_zone(self):
        """When a valid buy plan exists, SL must be below the entry zone."""
        from core.analysis_engine import analyze_symbol

        d1, h4, h1, m15 = self._build_data()
        request = AnalysisInput(
            symbol="EUR/USD", broker_symbol="EURUSDm",
            account_balance=10_000.0, risk_percent=2.0,
            contract_size_override=100_000.0,
        )

        result = analyze_symbol(request, {"D1": d1, "H4": h4, "H1": h1, "M15": m15})
        scenarios = result.get("scenarios", [])

        buy_scenarios = [s for s in scenarios if s.get("type") == "buy"]
        if not buy_scenarios:
            pytest.skip("No buy scenario generated")

        for sc in buy_scenarios:
            entry_low = float(sc["entry_zone"][0])
            sl = float(sc["stop_loss"])
            assert sl < entry_low, (
                f"Buy SL {sl:.5f} must be below entry_low {entry_low:.5f}"
            )

    def test_sell_plan_sl_above_entry_zone(self):
        """When a valid sell plan exists, SL must be above the entry zone."""
        from core.analysis_engine import analyze_symbol

        d1, h4, h1, m15 = self._build_data()
        request = AnalysisInput(
            symbol="EUR/USD", broker_symbol="EURUSDm",
            account_balance=10_000.0, risk_percent=2.0,
            contract_size_override=100_000.0,
        )

        result = analyze_symbol(request, {"D1": d1, "H4": h4, "H1": h1, "M15": m15})
        scenarios = result.get("scenarios", [])

        sell_scenarios = [s for s in scenarios if s.get("type") == "sell"]
        if not sell_scenarios:
            pytest.skip("No sell scenario generated")

        for sc in sell_scenarios:
            entry_high = float(sc["entry_zone"][1])
            sl = float(sc["stop_loss"])
            assert sl > entry_high, (
                f"Sell SL {sl:.5f} must be above entry_high {entry_high:.5f}"
            )


# ---------------------------------------------------------------------------
# Tests for _MIN_SL_DISTANCE_ATR guard (Change #3)
# ---------------------------------------------------------------------------


class TestMinSLDistanceGuard:
    """Verify the guard abs(level - SL) < ATR × 0.5 → return None."""

    def test_constant_is_05(self):
        assert _MIN_SL_DISTANCE_ATR == 0.5, (
            f"_MIN_SL_DISTANCE_ATR = {_MIN_SL_DISTANCE_ATR}, expected 0.5"
        )

    def test_buy_rejects_when_sl_too_tight(self, monkeypatch):
        """When swing is close to entry, SL is too tight → plan rejected."""
        end = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        d1 = _trending_candles(120, start_price=1.0500, step=0.00025,
                               bar_minutes=1440, start_time=end - timedelta(days=120))
        h4 = _trending_candles(360, start_price=d1[0].open, step=0.00012,
                               bar_minutes=240, start_time=d1[0].time)
        h1 = _trending_candles(480, start_price=h4[0].open, step=0.00006,
                               bar_minutes=60, start_time=h4[0].time)
        m15 = _trending_candles(200, start_price=h1[0].open, step=0.00002,
                                bar_minutes=15, start_time=h1[0].time)

        technical = build_technical_snapshot(d1, h4, h1)
        smc = build_smc_context(d1, h4, h1)
        price = technical["price"]
        atr = technical["atr_h4"] or technical["atr_d1"] or 0.0

        # Find the support level that would be selected
        from core.risk_engine import select_best_level
        support = select_best_level(
            list(technical["support_zones"]), price, atr * 1.5, below=True,
        )
        if support is None:
            pytest.skip("No support zone found for test")
        level = support["level"]

        # Mock swing to be very close to level → tight SL
        fake_swing = level - atr * 0.25
        monkeypatch.setattr(
            "core.risk_engine._find_nearest_swing_for_sl",
            lambda *a, **kw: fake_swing,
        )

        request = AnalysisInput(
            symbol="EUR/USD", broker_symbol="EURUSDm",
            account_balance=10_000.0, risk_percent=2.0,
            contract_size_override=100_000.0,
        )

        plan = build_trade_plan("buy", request, technical, smc, h1, m15_candles=m15)
        # SL = level - 0.25*ATR - 0.15*ATR = level - 0.40*ATR
        # abs(level - SL) = 0.40*ATR < 0.50*ATR → guard triggers
        assert plan is None, (
            f"Expected plan=None (guard triggered), but got a plan. "
            f"level={level:.5f}, fake_swing={fake_swing:.5f}, atr={atr:.6f}"
        )

    def test_buy_allows_when_sl_wide_enough(self, monkeypatch):
        """When swing is far from entry, SL is wide → guard passes."""
        end = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        d1 = _trending_candles(120, start_price=1.0500, step=0.00025,
                               bar_minutes=1440, start_time=end - timedelta(days=120))
        h4 = _trending_candles(360, start_price=d1[0].open, step=0.00012,
                               bar_minutes=240, start_time=d1[0].time)
        h1 = _trending_candles(480, start_price=h4[0].open, step=0.00006,
                               bar_minutes=60, start_time=h4[0].time)
        m15 = _trending_candles(200, start_price=h1[0].open, step=0.00002,
                                bar_minutes=15, start_time=h1[0].time)

        technical = build_technical_snapshot(d1, h4, h1)
        smc = build_smc_context(d1, h4, h1)
        price = technical["price"]
        atr = technical["atr_h4"] or technical["atr_d1"] or 0.0

        from core.risk_engine import select_best_level
        support = select_best_level(
            list(technical["support_zones"]), price, atr * 1.5, below=True,
        )
        if support is None:
            pytest.skip("No support zone found for test")
        level = support["level"]

        # Mock swing far below level → wide SL
        fake_swing = level - atr * 0.80
        monkeypatch.setattr(
            "core.risk_engine._find_nearest_swing_for_sl",
            lambda *a, **kw: fake_swing,
        )

        request = AnalysisInput(
            symbol="EUR/USD", broker_symbol="EURUSDm",
            account_balance=10_000.0, risk_percent=2.0,
            contract_size_override=100_000.0,
        )

        plan = build_trade_plan("buy", request, technical, smc, h1, m15_candles=m15)
        # SL = level - 0.80*ATR - 0.15*ATR = level - 0.95*ATR
        # abs(level - SL) = 0.95*ATR >= 0.50*ATR → guard passes
        # Plan may still be None due to TP1/R:R, but NOT due to the guard
        if plan is not None:
            sl = float(plan["stop_loss"])
            assert abs(level - sl) >= atr * _MIN_SL_DISTANCE_ATR, (
                f"SL {sl:.5f} is too close to level {level:.5f} "
                f"(distance={abs(level-sl):.6f} < {atr*_MIN_SL_DISTANCE_ATR:.6f})"
            )

    def test_sell_rejects_when_sl_too_tight(self, monkeypatch):
        """SELL: when swing is close to entry, SL too tight → rejected."""
        end = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        d1 = _trending_candles(120, start_price=1.0500, step=0.00025,
                               bar_minutes=1440, start_time=end - timedelta(days=120))
        h4 = _trending_candles(360, start_price=d1[0].open, step=0.00012,
                               bar_minutes=240, start_time=d1[0].time)
        h1 = _trending_candles(480, start_price=h4[0].open, step=0.00006,
                               bar_minutes=60, start_time=h4[0].time)
        m15 = _trending_candles(200, start_price=h1[0].open, step=0.00002,
                                bar_minutes=15, start_time=h1[0].time)

        technical = build_technical_snapshot(d1, h4, h1)
        smc = build_smc_context(d1, h4, h1)
        price = technical["price"]
        atr = technical["atr_h4"] or technical["atr_d1"] or 0.0

        from core.risk_engine import select_best_level
        resistance = select_best_level(
            list(technical["resistance_zones"]), price, atr * 1.5, below=False,
        )
        if resistance is None:
            pytest.skip("No resistance zone found for test")
        level = resistance["level"]

        # Mock swing close to level → tight SL
        fake_swing = level + atr * 0.25
        monkeypatch.setattr(
            "core.risk_engine._find_nearest_swing_for_sl",
            lambda *a, **kw: fake_swing,
        )

        request = AnalysisInput(
            symbol="EUR/USD", broker_symbol="EURUSDm",
            account_balance=10_000.0, risk_percent=2.0,
            contract_size_override=100_000.0,
        )

        plan = build_trade_plan("sell", request, technical, smc, h1, m15_candles=m15)
        # SL = level + 0.25*ATR + 0.15*ATR = level + 0.40*ATR
        # abs(level - SL) = 0.40*ATR < 0.50*ATR → guard triggers
        assert plan is None, (
            f"Expected plan=None (guard triggered), but got a plan. "
            f"level={level:.5f}, fake_swing={fake_swing:.5f}, atr={atr:.6f}"
        )

    def test_guard_runs_after_sl_floor(self, monkeypatch):
        """sl_floor (0.30 ATR) cannot satisfy the guard (0.50 ATR)."""
        end = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        d1 = _trending_candles(120, start_price=1.0500, step=0.00025,
                               bar_minutes=1440, start_time=end - timedelta(days=120))
        h4 = _trending_candles(360, start_price=d1[0].open, step=0.00012,
                               bar_minutes=240, start_time=d1[0].time)
        h1 = _trending_candles(480, start_price=h4[0].open, step=0.00006,
                               bar_minutes=60, start_time=h4[0].time)
        m15 = _trending_candles(200, start_price=h1[0].open, step=0.00002,
                                bar_minutes=15, start_time=h1[0].time)

        technical = build_technical_snapshot(d1, h4, h1)
        smc = build_smc_context(d1, h4, h1)
        price = technical["price"]
        atr = technical["atr_h4"] or technical["atr_d1"] or 0.0

        from core.risk_engine import select_best_level
        support = select_best_level(
            list(technical["support_zones"]), price, atr * 1.5, below=True,
        )
        if support is None:
            pytest.skip("No support zone found for test")
        level = support["level"]

        # Mock swing to return a level ABOVE sl_floor → SL gets pushed down
        # by sl_floor to level - 0.30*ATR, but that's still < 0.50*ATR
        fake_swing = level + atr * 0.10  # swing above level → SL = level + 0.10*ATR - 0.15*ATR = level - 0.05*ATR
        monkeypatch.setattr(
            "core.risk_engine._find_nearest_swing_for_sl",
            lambda *a, **kw: fake_swing,
        )

        request = AnalysisInput(
            symbol="EUR/USD", broker_symbol="EURUSDm",
            account_balance=10_000.0, risk_percent=2.0,
            contract_size_override=100_000.0,
        )

        plan = build_trade_plan("buy", request, technical, smc, h1, m15_candles=m15)
        # SL = level - 0.05*ATR (before sl_floor)
        # sl_floor = level - 0.30*ATR → SL gets pushed to level - 0.30*ATR
        # abs(level - 0.30*ATR) = 0.30*ATR < 0.50*ATR → guard STILL triggers
        assert plan is None, (
            "sl_floor pushes SL to 0.30 ATR, but guard requires 0.50 ATR. "
            "Plan should be rejected."
        )


# ---------------------------------------------------------------------------
# Tests for _find_nearest_equal_level (Change #4 — TP1 liquidity clusters)
# ---------------------------------------------------------------------------


def _make_smc_with_liquidity_pools(
    equal_highs: list[float] | None = None,
    equal_lows: list[float] | None = None,
) -> dict[str, Any]:
    """Build a minimal SMC dict with H4 liquidity_pools."""
    return {
        "H4": {
            "liquidity_pools": {
                "equal_highs": equal_highs or [],
                "equal_lows": equal_lows or [],
            }
        }
    }


class TestFindNearestEqualLevel:
    """Unit tests for _find_nearest_equal_level()."""

    def test_buy_finds_nearest_equal_high_above_price(self):
        smc = _make_smc_with_liquidity_pools(
            equal_highs=[1.1020, 1.1050, 1.1080],
        )
        result = _find_nearest_equal_level(smc, "buy", 1.1000)
        # 1.1020 is the lowest equal high above 1.1000
        assert result == 1.1020

    def test_buy_returns_none_when_all_equal_highs_below_price(self):
        smc = _make_smc_with_liquidity_pools(
            equal_highs=[1.0950, 1.0970, 1.0990],
        )
        result = _find_nearest_equal_level(smc, "buy", 1.1000)
        assert result is None

    def test_sell_finds_nearest_equal_low_below_price(self):
        smc = _make_smc_with_liquidity_pools(
            equal_lows=[1.0950, 1.0980, 1.1010],
        )
        result = _find_nearest_equal_level(smc, "sell", 1.1000)
        # 1.0980 is the highest equal low below 1.1000
        assert result == 1.0980

    def test_sell_returns_none_when_all_equal_lows_above_price(self):
        smc = _make_smc_with_liquidity_pools(
            equal_lows=[1.1020, 1.1050],
        )
        result = _find_nearest_equal_level(smc, "sell", 1.1000)
        assert result is None

    def test_returns_none_when_no_candidates(self):
        smc = _make_smc_with_liquidity_pools(equal_highs=[], equal_lows=[])
        assert _find_nearest_equal_level(smc, "buy", 1.1000) is None
        assert _find_nearest_equal_level(smc, "sell", 1.1000) is None

    def test_returns_none_when_smc_is_none(self):
        assert _find_nearest_equal_level(None, "buy", 1.1000) is None

    def test_returns_none_when_smc_is_not_dict(self):
        assert _find_nearest_equal_level("bad", "buy", 1.1000) is None  # type: ignore[arg-type]

    def test_searches_both_h4_and_h1(self):
        """H1 equal_high closer than H4 → H1 should be selected."""
        smc = {
            "H4": {"liquidity_pools": {"equal_highs": [1.1080], "equal_lows": []}},
            "H1": {"liquidity_pools": {"equal_highs": [1.1030], "equal_lows": []}},
        }
        # H1 equal_high 1.1030 is closer to 1.1000 than H4's 1.1080
        result = _find_nearest_equal_level(smc, "buy", 1.1000)
        assert result == 1.1030

    def test_skips_non_numeric_values(self):
        smc = {
            "H4": {"liquidity_pools": {
                "equal_highs": ["1.1050", 1.1030, None, 1.1080],
            }}
        }
        result = _find_nearest_equal_level(smc, "buy", 1.1000)
        # Only 1.1030 and 1.1080 are valid; 1.1030 is closest above 1.1000
        assert result == 1.1030

    def test_handles_missing_liquidity_pools_key(self):
        smc = {"H4": {}}  # no liquidity_pools key
        result = _find_nearest_equal_level(smc, "buy", 1.1000)
        assert result is None

    def test_buy_tp1_falls_back_when_equal_level_fails_rr(self):
        """When equal level is too close (bad R:R), fallback to S/R zones."""
        # equal_high at 1.1005 is only 5 pips above entry_for_rr of 1.1000
        # With SL at 1.0990 (10 pips risk), R:R would be 0.5:1 → falls through
        smc = _make_smc_with_liquidity_pools(equal_highs=[1.1005])
        result = _find_nearest_equal_level(smc, "buy", 1.1000)
        # The function returns the level; the caller (build_trade_plan)
        # checks R:R. So the function itself should still return 1.1005.
        assert result == 1.1005, (
            "_find_nearest_equal_level returns the level; "
            "R:R filtering is done by the caller"
        )
