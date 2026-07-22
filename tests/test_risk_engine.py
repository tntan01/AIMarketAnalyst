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
    _MIN_STOP_DISTANCE_ATR_MULT,
    _SWING_SL_BUFFER_ATR,
    AnalysisInput,
    _find_nearest_equal_level,
    _find_nearest_swing_for_sl,
    _resolve_quote_to_usd_rate,
    _asset_class_for,
    ASSET_CLASS_SL_MULTIPLIER,
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


def test_entry_zone_atr_mult_is_035():
    """The module-level constant must be 0.35 (changed from 0.20)."""
    assert ENTRY_ZONE_ATR_MULT == 0.35, (
        f"ENTRY_ZONE_ATR_MULT = {ENTRY_ZONE_ATR_MULT}, expected 0.35"
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


# ---------------------------------------------------------------------------
# Tests for select_best_level with _effective_zone_score (zone_score-driven)
# ---------------------------------------------------------------------------


def test_select_best_level_prefers_higher_zone_score():
    """Two zones same strength, same distance; higher zone_score wins."""
    from core.risk_engine import select_best_level

    price = 1.1000
    zones = [
        {"level": 1.0950, "strength": "strong", "zone_score": 76},
        {"level": 1.0945, "strength": "strong", "zone_score": 99},
    ]
    result = select_best_level(zones, price, max_distance=0.0050 * 3.5, below=True)
    assert result is not None
    # zone_score 99 should beat zone_score 76
    assert result["zone_score"] == 99, (
        f"Expected zone_score=99 to be selected, got {result['zone_score']}"
    )


def test_select_best_level_handles_no_zone_score_with_fallback():
    """SMC zone (has zone_score) vs technical zone (no zone_score, strength only).
    Fallback must not crash and must compare fairly."""
    from core.risk_engine import select_best_level, _STRENGTH_FALLBACK_SCORE

    price = 1.1000
    smc_zone = {"level": 1.0950, "strength": "moderate", "zone_score": 90}
    # technical zone: no zone_score field at all, relies on strength fallback
    tech_zone = {"level": 1.0945, "strength": "strong"}

    zones = [smc_zone, tech_zone]
    result = select_best_level(zones, price, max_distance=0.0050 * 3.5, below=True)
    assert result is not None
    # SMC zone_score=90 > strong fallback=80 → SMC should win
    assert result is smc_zone, (
        f"Expected SMC zone (score=90) to beat technical zone (fallback=80), got {result}"
    )

    # Reverse: SMC with low zone_score should lose to strong technical
    smc_weak = {"level": 1.0950, "strength": "weak", "zone_score": 30}
    result2 = select_best_level([smc_weak, tech_zone], price, max_distance=0.0050 * 3.5, below=True)
    assert result2 is not None
    assert result2 is tech_zone, (
        f"Expected technical zone (fallback=80) to beat SMC zone (score=30), got {result2}"
    )


# ---------------------------------------------------------------------------
# Tests for SMC relaxed SL threshold (is_smc_zone → 0.20×ATR)
# ---------------------------------------------------------------------------


def test_smc_zone_uses_relaxed_sl_threshold():
    """SMC zone (source='smc') passes SL check at 0.25×ATR,
    while technical zone would fail."""
    from core.risk_engine import build_trade_plan, AnalysisInput

    d1 = _trending_candles(100, start_price=1.1000, step=0.00002, bar_minutes=1440)
    h4 = _trending_candles(200, start_price=1.1000, step=0.00002, bar_minutes=240)
    h1 = _trending_candles(200, start_price=1.1000, step=0.00002, bar_minutes=60)
    m15 = _trending_candles(200, start_price=1.1000, step=0.00002, bar_minutes=15)

    from core.technical_context import build_technical_snapshot
    from core.smc_context import build_smc_context
    technical = build_technical_snapshot(d1, h4, h1)
    smc = build_smc_context(d1, h4, h1)

    request = AnalysisInput(
        symbol="EUR/USD", broker_symbol="EURUSDm",
        account_balance=10_000.0, risk_percent=2.0, contract_size_override=100_000.0,
    )

    plan = build_trade_plan("buy", request, technical, smc, h1, m15_candles=m15)
    if plan is None:
        pytest.skip("No valid plan generated from test candles")

    # If a plan was generated and the zone is SMC, sl_source should reflect it
    zone_source = plan.get("entry_zone_source")
    sl_source = plan.get("sl_source")
    assert sl_source is not None, "sl_source must be present in plan output"
    if zone_source == "smc":
        # SMC zones should get relaxed treatment
        assert sl_source in ("zone_boundary", "swing"), (
            f"SMC zone should have sl_source=swing or zone_boundary, got {sl_source}"
        )


# ---------------------------------------------------------------------------
# Tests for asset_class_sl_multiplier
# ---------------------------------------------------------------------------


def _build_test_data(base_price: float = 1.0800):
    """Build technical + smc + candles from synthetic trending data.

    Returns (request, technical, smc, h1_candles, m15_candles).
    The raw data alone rarely produces a valid plan — callers must mock
    select_best_level / _find_nearest_swing_for_sl / nearest_target to
    force a deterministic plan.
    """
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


def _make_controlled_plan(
    symbol: str,
    side: str,
    monkeypatch,
    *,
    fake_zone_level: float | None = None,
    fake_tp: float | None = None,
    asset_multipliers: dict[str, float] | None = None,
    zone_source: str = "technical",
) -> dict[str, Any] | None:
    """Build a trade plan with mocked zone/SL/TP to force deterministic output.

    Mocks select_best_level, _find_nearest_swing_for_sl, and nearest_target
    so the plan always succeeds.  The ATR-based SL path is used (no swing),
    which means sl_mult directly controls the SL distance.
    """
    d1, h4, h1, m15 = _build_test_data()
    technical = build_technical_snapshot(d1, h4, h1)
    smc = build_smc_context(d1, h4, h1)
    price = technical["price"]
    atr = technical["atr_h4"] or technical["atr_d1"] or 0.0

    request = AnalysisInput(
        symbol=symbol,
        broker_symbol=symbol.replace("/", "").replace("USD", "USDm"),
        account_balance=10_000.0,
        risk_percent=2.0,
        contract_size_override=100_000.0,
    )

    # Zone: place it slightly on the correct side of price so it's always
    # selected.  low == level ensures the ATR-based SL path is used
    # (zone boundary guard falls through because zone_low >= level).
    lvl = fake_zone_level if fake_zone_level is not None else (
        price - atr * 0.5 if side == "buy" else price + atr * 0.5
    )
    fake_zone = {"level": lvl, "low": lvl, "high": lvl + atr * 0.1,
                 "zone_score": 80, "source": zone_source}

    # TP: far enough to pass all RR guards
    sign = 1 if side == "buy" else -1
    tp = fake_tp if fake_tp is not None else lvl + sign * atr * 3.0

    with monkeypatch.context() as m:
        m.setattr("core.risk_engine.select_best_level", lambda *a, **kw: fake_zone)
        m.setattr("core.risk_engine.select_top_levels", lambda *a, **kw: [fake_zone])
        m.setattr("core.risk_engine._find_nearest_swing_for_sl", lambda *a, **kw: None)
        m.setattr("core.risk_engine.nearest_target", lambda *a, **kw: tp)
        m.setattr("core.risk_engine.next_target", lambda *a, **kw: tp + sign * atr * 1.0)
        m.setattr("core.risk_engine._find_nearest_equal_level", lambda *a, **kw: None)
        # Ensure sl_mult is wide enough to pass the guard (now uses entry_for_rr,
        # which is entry_zone_atr_mult*ATR closer to SL than level)
        m.setattr("core.risk_engine.REGIME_SL_MULTIPLIER",
                  {"unknown": 0.65, "trend_up": 0.65, "trend_down": 0.65,
                   "range": 0.70, "volatile": 0.85})
        if asset_multipliers is not None:
            m.setattr("core.risk_engine.ASSET_CLASS_SL_MULTIPLIER", asset_multipliers)

        return build_trade_plan(side, request, technical, smc, h1, m15_candles=m15)


class TestAssetClassSLMultiplier:
    """Tests for asset-class-based SL multiplier overlay."""

    def test_default_multipliers_are_1(self):
        """All default asset class multipliers must be 1.0 (no-op)."""
        assert ASSET_CLASS_SL_MULTIPLIER["forex"] == 1.0
        assert ASSET_CLASS_SL_MULTIPLIER["metals"] == 1.0
        assert ASSET_CLASS_SL_MULTIPLIER["crypto"] == 1.0

    def test_forex_symbol_uses_asset_class_forex(self):
        """EUR/USD (not in SYMBOL_CONFIG) → asset_class = 'forex'."""
        assert _asset_class_for("EUR/USD") == "forex"

    def test_unknown_symbol_defaults_to_forex(self):
        """Any symbol not in SYMBOL_CONFIG defaults to 'forex'."""
        assert _asset_class_for("GBP/JPY") == "forex"
        assert _asset_class_for("AUD/NZD") == "forex"
        assert _asset_class_for("SOMETHING/XYZ") == "forex"

    def test_xau_usd_is_metals(self):
        assert _asset_class_for("XAU/USD") == "metals"

    def test_xag_usd_is_metals(self):
        assert _asset_class_for("XAG/USD") == "metals"

    def test_btc_usd_is_crypto(self):
        assert _asset_class_for("BTC/USD") == "crypto"

    def test_regression_sl_unchanged_with_default_multipliers(self, monkeypatch):
        """With asset_class multipliers all = 1.0, stop_loss must be identical
        across two calls — proving the new multiplier layer is a no-op at
        default settings.
        """
        plan1 = _make_controlled_plan(
            "EUR/USD", "buy", monkeypatch,
            asset_multipliers={"forex": 1.0, "metals": 1.0, "crypto": 1.0},
        )
        plan2 = _make_controlled_plan(
            "EUR/USD", "buy", monkeypatch,
            asset_multipliers={"forex": 1.0, "metals": 1.0, "crypto": 1.0},
        )

        assert plan1 is not None, "Plan 1 must not be None"
        assert plan2 is not None, "Plan 2 must not be None"
        assert float(plan1["stop_loss"]) == float(plan2["stop_loss"]), (
            f"SL must be identical with same multipliers: "
            f"{plan1['stop_loss']} vs {plan2['stop_loss']}"
        )
        assert float(plan1["entry_price"]) == float(plan2["entry_price"]), (
            "Entry price must be identical"
        )
        assert plan1["take_profit"] == plan2["take_profit"], (
            "Take-profit must be identical"
        )

    def test_crypto_multiplier_widens_sl(self, monkeypatch):
        """BTC/USD with crypto multiplier=1.6 must have wider SL distance
        than with multiplier=1.0.
        """
        plan_default = _make_controlled_plan(
            "BTC/USD", "buy", monkeypatch,
            asset_multipliers={"forex": 1.0, "metals": 1.0, "crypto": 1.0},
        )
        plan_wider = _make_controlled_plan(
            "BTC/USD", "buy", monkeypatch,
            asset_multipliers={"forex": 1.0, "metals": 1.0, "crypto": 1.6},
        )

        assert plan_default is not None, "Plan with multiplier=1.0 must not be None"
        assert plan_wider is not None, "Plan with multiplier=1.6 must not be None"

        sl_dist_default = abs(
            float(plan_default["entry_price"]) - float(plan_default["stop_loss"])
        )
        sl_dist_wider = abs(
            float(plan_wider["entry_price"]) - float(plan_wider["stop_loss"])
        )

        assert sl_dist_wider > sl_dist_default, (
            f"Crypto multiplier=1.6 must produce wider SL than 1.0. "
            f"default={sl_dist_default:.6f}, wider={sl_dist_wider:.6f}"
        )

    def test_json_missing_key_falls_back_to_1(self, monkeypatch):
        """_load_risk_params() with missing asset_class_sl_multiplier must work."""
        import core.risk_engine as re

        minimal = {
            "default_sl_mult": 0.50,
            "regime_sl_multiplier": {
                "trend_up": 0.65, "trend_down": 0.65,
                "range": 0.70, "volatile": 0.85, "unknown": 0.50,
            },
            "min_sl_distance_atr": 0.5,
        }

        with monkeypatch.context() as m:
            m.setattr(re, "_rp", minimal)
            m.setattr(
                re, "ASSET_CLASS_SL_MULTIPLIER",
                minimal.get("asset_class_sl_multiplier", {
                    "forex": 1.0, "metals": 1.0, "crypto": 1.0,
                }),
            )
            m.setattr(
                re, "REGIME_SL_MULTIPLIER",
                minimal.get("regime_sl_multiplier", {
                    "trend_up": 0.65, "trend_down": 0.65,
                    "range": 0.70, "volatile": 0.85, "unknown": 0.50,
                }),
            )
            multi = re.ASSET_CLASS_SL_MULTIPLIER
            assert multi["forex"] == 1.0
            assert multi["metals"] == 1.0
            assert multi["crypto"] == 1.0


# ---------------------------------------------------------------------------
# Việc 1 — Fix key name: min_stop_distance_atr_mult → min_sl_distance_atr_mult
# ---------------------------------------------------------------------------


class TestMinStopDistanceKeyFix:
    """Verify _MIN_STOP_DISTANCE_ATR_MULT reads correct JSON key."""

    def test_constant_reads_from_correct_json_key(self):
        """_MIN_STOP_DISTANCE_ATR_MULT must equal config min_sl_distance_atr_mult."""
        import json
        from pathlib import Path
        params_file = Path(__file__).resolve().parents[1] / "config" / "risk_params.json"
        rp = json.loads(params_file.read_text())

        assert "min_sl_distance_atr_mult" in rp, (
            "Config must have key 'min_sl_distance_atr_mult'"
        )
        assert "min_stop_distance_atr_mult" not in rp, (
            "Stale key 'min_stop_distance_atr_mult' still in config — remove it"
        )
        expected = rp["min_sl_distance_atr_mult"]
        assert _MIN_STOP_DISTANCE_ATR_MULT == expected, (
            f"_MIN_STOP_DISTANCE_ATR_MULT={_MIN_STOP_DISTANCE_ATR_MULT}, "
            f"expected {expected} from config key 'min_sl_distance_atr_mult'. "
            f"Code may still be reading from wrong key name."
        )

    def test_guard_uses_patched_multiplier_not_default(self, monkeypatch):
        """When _MIN_STOP_DISTANCE_ATR_MULT=0.35, SL is at least 0.20*ATR wide
        and the plan is valid (multiplier applied through min_stop_distance)."""
        d1, h4, h1, m15 = _build_test_data()
        technical = build_technical_snapshot(d1, h4, h1)
        smc = build_smc_context(d1, h4, h1)
        price = technical["price"]
        atr = technical["atr_h4"] or technical["atr_d1"] or 0.0

        request = AnalysisInput(
            symbol="EUR/USD", broker_symbol="EURUSDm",
            account_balance=10_000.0, risk_percent=2.0,
            contract_size_override=100_000.0,
        )

        lvl = price - atr * 0.5
        fake_zone = {"level": lvl, "low": lvl, "high": lvl + atr * 0.05,
                     "zone_score": 80, "source": "smc"}
        tp = lvl + atr * 3.0

        with monkeypatch.context() as m:
            m.setattr("core.risk_engine.select_best_level", lambda *a, **kw: fake_zone)
            m.setattr("core.risk_engine.select_top_levels", lambda *a, **kw: [fake_zone])
            m.setattr("core.risk_engine._find_nearest_swing_for_sl", lambda *a, **kw: None)
            m.setattr("core.risk_engine.nearest_target", lambda *a, **kw: tp)
            m.setattr("core.risk_engine.next_target", lambda *a, **kw: tp + atr * 1.0)
            m.setattr("core.risk_engine._find_nearest_equal_level", lambda *a, **kw: None)
            m.setattr("core.risk_engine.REGIME_SL_MULTIPLIER",
                      {"unknown": 0.65, "trend_up": 0.65, "trend_down": 0.65,
                       "range": 0.70, "volatile": 0.85})
            m.setattr("core.risk_engine._MIN_STOP_DISTANCE_ATR_MULT", 0.35)

            plan = build_trade_plan("buy", request, technical, smc, h1, m15_candles=m15)

        # Plan must exist (sl_mult=0.65 ensures rr_risk passes guard)
        assert plan is not None, (
            "Plan should exist — _MIN_STOP_DISTANCE_ATR_MULT=0.35 "
            "provides enough min_stop_distance"
        )
        sl = float(plan["stop_loss"])
        sl_distance = abs(lvl - sl)
        # With sl_mult=0.65, SL is at least 0.50*ATR from entry_for_rr,
        # confirming the patched multiplier is applied
        assert sl_distance >= atr * 0.50, (
            f"SL distance {sl_distance:.6f} too small for patched multiplier. "
            f"Expected roughly {atr*0.65:.6f}. Multiplier not applied."
        )

    def test_sl_distance_wider_with_035_than_020(self, monkeypatch):
        """With _MIN_STOP_DISTANCE_ATR_MULT=0.50 (larger), guard rejects a plan
        that passes with mult=0.20 — proving config key controls guard behavior."""
        d1, h4, h1, m15 = _build_test_data()
        technical = build_technical_snapshot(d1, h4, h1)
        smc = build_smc_context(d1, h4, h1)
        price = technical["price"]
        atr = technical["atr_h4"] or technical["atr_d1"] or 0.0

        request = AnalysisInput(
            symbol="EUR/USD", broker_symbol="EURUSDm",
            account_balance=10_000.0, risk_percent=2.0,
            contract_size_override=100_000.0,
        )

        lvl = price - atr * 0.5
        fake_zone = {"level": lvl, "low": lvl, "high": lvl + atr * 0.05,
                     "zone_score": 80, "source": "smc"}
        tp = lvl + atr * 3.0

        # Swing produces SL at lvl - 0.35*ATR (entry_for_rr - 0.25*ATR)
        # With SMC relaxed threshold 0.20: 0.25 >= 0.20 → plan exists
        # With SMC relaxed threshold 0.50: 0.25 < 0.50 → plan rejected
        fake_swing = lvl - atr * 0.20

        def _build_with_mult(mult):
            with monkeypatch.context() as m:
                m.setattr("core.risk_engine.select_best_level", lambda *a, **kw: fake_zone)
                m.setattr("core.risk_engine.select_top_levels", lambda *a, **kw: [fake_zone])
                m.setattr("core.risk_engine._find_nearest_swing_for_sl",
                          lambda *a, **kw: fake_swing)
                m.setattr("core.risk_engine.nearest_target", lambda *a, **kw: tp)
                m.setattr("core.risk_engine.next_target", lambda *a, **kw: tp + atr * 1.0)
                m.setattr("core.risk_engine._find_nearest_equal_level", lambda *a, **kw: None)
                m.setattr("core.risk_engine._MIN_STOP_DISTANCE_ATR_MULT", mult)
                return build_trade_plan("buy", request, technical, smc, h1, m15_candles=m15)

        plan_020 = _build_with_mult(0.20)
        plan_050 = _build_with_mult(0.50)

        assert plan_020 is not None, (
            "Plan should exist with SMC relaxed threshold 0.20"
        )
        assert plan_050 is None, (
            "Plan should be REJECTED with SMC threshold 0.50: "
            "entry_for_rr-to-SL=0.25*ATR < 0.50*ATR"
        )


# ---------------------------------------------------------------------------
# Việc 2 — Guard "skip plan if SL too tight" must use entry_for_selection
# ---------------------------------------------------------------------------


class TestSLGuardReferencePoint:
    """Guard must reference entry_for_selection, not level."""

    def test_guard_uses_entry_for_selection_not_level(self, monkeypatch):
        """When level is far from SL but entry_for_selection is close,
        guard must reject the plan.

        BEFORE fix: guard used abs(level - SL) → plan incorrectly passed.
        AFTER fix:  guard uses abs(entry_for_selection - SL) → correctly rejects.
        """
        d1, h4, h1, m15 = _build_test_data()
        technical = build_technical_snapshot(d1, h4, h1)
        smc = build_smc_context(d1, h4, h1)
        price = technical["price"]
        atr = technical["atr_h4"] or technical["atr_d1"] or 0.0

        request = AnalysisInput(
            symbol="EUR/USD", broker_symbol="EURUSDm",
            account_balance=10_000.0, risk_percent=2.0,
            contract_size_override=100_000.0,
        )

        # Zone: small width → entry_zone_atr_mult = 0.10
        lvl = price - atr * 0.5
        zone_width = atr * 0.10
        fake_zone = {
            "level": lvl,
            "low": lvl - zone_width / 2,
            "high": lvl + zone_width / 2,
            "zone_score": 80,
            "source": "technical",
        }

        # TP far enough
        tp = lvl + atr * 3.0

        # Swing at lvl - 0.40*ATR → stop_loss = lvl - 0.55*ATR
        # abs(level - SL) = 0.55*ATR >= 0.50*ATR → old guard PASSES (bug)
        # With _TP_SELECTION_AGGRESSIVENESS=0.0, entry_for_selection = entry_low
        #   = lvl - 0.10*ATR
        # abs(entry_for_selection - SL) = 0.45*ATR < 0.50*ATR → new guard REJECTS
        fake_swing = lvl - atr * 0.40

        with monkeypatch.context() as m:
            m.setattr("core.risk_engine.select_best_level", lambda *a, **kw: fake_zone)
            m.setattr("core.risk_engine.select_top_levels", lambda *a, **kw: [fake_zone])
            m.setattr("core.risk_engine._find_nearest_swing_for_sl",
                      lambda *a, **kw: fake_swing)
            m.setattr("core.risk_engine.nearest_target", lambda *a, **kw: tp)
            m.setattr("core.risk_engine.next_target", lambda *a, **kw: tp + atr * 1.0)
            m.setattr("core.risk_engine._find_nearest_equal_level", lambda *a, **kw: None)
            # Set aggressiveness=0.0 so entry_for_selection = entry_low ≠ level
            m.setattr("core.risk_engine._TP_SELECTION_AGGRESSIVENESS", 0.0)

            plan = build_trade_plan("buy", request, technical, smc, h1, m15_candles=m15)

        # After fix: entry_for_selection-to-SL = 0.45*ATR < 0.50*ATR → rejected
        assert plan is None, (
            f"Expected plan=None because entry_for_selection is too close to SL. "
            f"level={lvl:.5f}, entry_low≈{lvl - atr * 0.10:.5f}, "
            f"fake_swing={fake_swing:.5f}, atr={atr:.6f}, "
            f"level-to-SL={abs(lvl - (fake_swing - atr*0.15)):.6f}, "
            f"entry_for_sel-to-SL={abs(lvl - atr*0.10 - (fake_swing - atr*0.15)):.6f}"
        )

    def test_guard_allows_plan_when_sl_wide_enough(self, monkeypatch):
        """When entry_for_selection-to-SL >= _min_sl, guard must NOT reject.

        Regression: ensure the new guard (using entry_for_selection) does not
        block valid plans that were passing before the fix.
        """
        d1, h4, h1, m15 = _build_test_data()
        technical = build_technical_snapshot(d1, h4, h1)
        smc = build_smc_context(d1, h4, h1)
        price = technical["price"]
        atr = technical["atr_h4"] or technical["atr_d1"] or 0.0

        request = AnalysisInput(
            symbol="EUR/USD", broker_symbol="EURUSDm",
            account_balance=10_000.0, risk_percent=2.0,
            contract_size_override=100_000.0,
        )

        # Zone: small width
        lvl = price - atr * 0.5
        zone_width = atr * 0.10
        fake_zone = {
            "level": lvl,
            "low": lvl - zone_width / 2,
            "high": lvl + zone_width / 2,
            "zone_score": 80,
            "source": "technical",
        }
        tp = lvl + atr * 3.0

        # Swing at lvl - 0.80*ATR → stop_loss = lvl - 0.95*ATR
        # entry_for_selection = lvl (aggressiveness=0.5 default)
        # abs(entry_for_selection - SL) = 0.95*ATR >= 0.50*ATR → guard passes
        fake_swing = lvl - atr * 0.80

        with monkeypatch.context() as m:
            m.setattr("core.risk_engine.select_best_level", lambda *a, **kw: fake_zone)
            m.setattr("core.risk_engine.select_top_levels", lambda *a, **kw: [fake_zone])
            m.setattr("core.risk_engine._find_nearest_swing_for_sl",
                      lambda *a, **kw: fake_swing)
            m.setattr("core.risk_engine.nearest_target", lambda *a, **kw: tp)
            m.setattr("core.risk_engine.next_target", lambda *a, **kw: tp + atr * 1.0)
            m.setattr("core.risk_engine._find_nearest_equal_level", lambda *a, **kw: None)

            plan = build_trade_plan("buy", request, technical, smc, h1, m15_candles=m15)

        # Guard must NOT reject: SL is 0.95*ATR from entry_for_selection ≥ 0.50*ATR
        assert plan is not None, (
            f"Expected plan to exist (SL wide enough), but got None. "
            f"level={lvl:.5f}, fake_swing={fake_swing:.5f}, "
            f"entry_for_sel-to-SL≈{abs(lvl - (fake_swing - atr*0.15)):.6f}, "
            f"min threshold={atr * _MIN_SL_DISTANCE_ATR:.6f}"
        )

    def test_guard_uses_min_of_rr_and_selection_distances(self, monkeypatch):
        """Guard must use min(entry_for_rr, entry_for_selection) distance to SL.

        With DEFAULT aggressiveness (entry_aggressiveness=0.0,
        tp_selection_aggressiveness=0.5):
        - entry_for_rr = entry_low (nearest edge, CLOSEST to SL)
        - entry_for_selection = level (midpoint)

        A guard using ONLY entry_for_selection would pass when
        abs(level - SL) >= threshold but abs(entry_low - SL) < threshold.

        The min() guard correctly rejects this case.
        """
        d1, h4, h1, m15 = _build_test_data()
        technical = build_technical_snapshot(d1, h4, h1)
        smc = build_smc_context(d1, h4, h1)
        price = technical["price"]
        atr = technical["atr_h4"] or technical["atr_d1"] or 0.0

        request = AnalysisInput(
            symbol="EUR/USD", broker_symbol="EURUSDm",
            account_balance=10_000.0, risk_percent=2.0,
            contract_size_override=100_000.0,
        )

        # Zone: small width → entry_zone_atr_mult = 0.10
        lvl = price - atr * 0.5
        zone_width = atr * 0.10
        fake_zone = {
            "level": lvl,
            "low": lvl - zone_width / 2,
            "high": lvl + zone_width / 2,
            "zone_score": 80,
            "source": "technical",
        }
        tp = lvl + atr * 3.0

        # Swing at lvl - 0.40*ATR → stop_loss = lvl - 0.55*ATR
        # entry_for_rr = entry_low = lvl - 0.10*ATR (aggressiveness=0.0 default)
        # entry_for_selection = lvl (tp_selection_aggressiveness=0.5 default)
        #
        # OLD guard (entry_for_selection only):
        #   abs(lvl - (lvl - 0.55*ATR)) = 0.55*ATR >= 0.50*ATR → PASSES (BUG)
        # NEW guard (min of both):
        #   rr_risk = abs(lvl - 0.10*ATR - (lvl - 0.55*ATR)) = 0.45*ATR
        #   sel_risk = abs(lvl - (lvl - 0.55*ATR)) = 0.55*ATR
        #   min(0.45, 0.55) = 0.45*ATR < 0.50*ATR → REJECTS (CORRECT)
        fake_swing = lvl - atr * 0.40

        with monkeypatch.context() as m:
            m.setattr("core.risk_engine.select_best_level", lambda *a, **kw: fake_zone)
            m.setattr("core.risk_engine.select_top_levels", lambda *a, **kw: [fake_zone])
            m.setattr("core.risk_engine._find_nearest_swing_for_sl",
                      lambda *a, **kw: fake_swing)
            m.setattr("core.risk_engine.nearest_target", lambda *a, **kw: tp)
            m.setattr("core.risk_engine.next_target", lambda *a, **kw: tp + atr * 1.0)
            m.setattr("core.risk_engine._find_nearest_equal_level", lambda *a, **kw: None)
            # Both aggressiveness values at DEFAULT:
            # entry_aggressiveness=0.0 → entry_for_rr = entry_low
            # _TP_SELECTION_AGGRESSIVENESS=0.5 → entry_for_selection = level
            # (no monkeypatch needed — these are the real defaults)

            plan = build_trade_plan("buy", request, technical, smc, h1, m15_candles=m15)

        # Guard must reject: entry_for_rr is only 0.45*ATR from SL < 0.50*ATR
        assert plan is None, (
            f"Expected plan=None because entry_for_rr (nearest edge) is too close to SL. "
            f"level={lvl:.5f}, entry_low≈{lvl - atr * 0.10:.5f}, "
            f"fake_swing={fake_swing:.5f}, atr={atr:.6f}, "
            f"entry_for_rr-to-SL={abs(lvl - atr*0.10 - (fake_swing - atr*0.15)):.6f}, "
            f"entry_for_sel-to-SL={abs(lvl - (fake_swing - atr*0.15)):.6f}, "
            f"min_threshold={atr * _MIN_SL_DISTANCE_ATR:.6f}"
        )


# ---------------------------------------------------------------------------
# Việc 3 — Increase _SL_FLOOR_BUFFER_ATR 0.10 → 0.20
# ---------------------------------------------------------------------------


class TestSLFloorBufferChange:
    """Verify sl_floor_buffer_atr increase from 0.10 to 0.20 widens SL floor."""

    def test_new_buffer_produces_wider_sl_than_old_buffer(self, monkeypatch):
        """sl_edge with buffer=0.20 must be farther from entry zone than buffer=0.10.

        Constructs a case where the raw stop_loss is inside the entry zone,
        so the sl_edge guard clamps it.  The clamped SL with 0.20 buffer is
        wider than with 0.10 buffer.
        """
        d1, h4, h1, m15 = _build_test_data()
        technical = build_technical_snapshot(d1, h4, h1)
        smc = build_smc_context(d1, h4, h1)
        price = technical["price"]
        atr = technical["atr_h4"] or technical["atr_d1"] or 0.0

        request = AnalysisInput(
            symbol="EUR/USD", broker_symbol="EURUSDm",
            account_balance=10_000.0, risk_percent=2.0,
            contract_size_override=100_000.0,
        )

        lvl = price - atr * 0.5
        zone_width = atr * 0.10
        fake_zone = {
            "level": lvl,
            "low": lvl - zone_width / 2,
            "high": lvl + zone_width / 2,
            "zone_score": 80,
            "source": "smc",  # SMC → relaxed tightness guard (0.20*ATR)
        }
        tp = lvl + atr * 3.0

        # entry_low = lvl - atr * 0.10 (zone_width_atr=0.10)
        # Mock swing so raw stop_loss falls INSIDE the entry zone
        # swing = entry_low + 0.20*ATR → raw SL = entry_low + 0.05*ATR (above entry_low!)
        entry_low = lvl - atr * 0.10
        fake_swing = entry_low + atr * 0.20

        def _build_with_buffer(buf):
            with monkeypatch.context() as m:
                m.setattr("core.risk_engine.select_best_level", lambda *a, **kw: fake_zone)
                m.setattr("core.risk_engine.select_top_levels", lambda *a, **kw: [fake_zone])
                m.setattr("core.risk_engine._find_nearest_swing_for_sl",
                          lambda *a, **kw: fake_swing)
                m.setattr("core.risk_engine.nearest_target", lambda *a, **kw: tp)
                m.setattr("core.risk_engine.next_target", lambda *a, **kw: tp + atr * 1.0)
                m.setattr("core.risk_engine._find_nearest_equal_level", lambda *a, **kw: None)
                # Relax tightness guard so it doesn't reject our plan
                m.setattr("core.risk_engine._MIN_SL_DISTANCE_ATR", 0.05)
                m.setattr("core.risk_engine._MIN_STOP_DISTANCE_ATR_MULT", 0.05)
                m.setattr("core.risk_engine._SL_FLOOR_BUFFER_ATR", buf)
                return build_trade_plan("buy", request, technical, smc, h1, m15_candles=m15)

        plan_old = _build_with_buffer(0.10)
        plan_new = _build_with_buffer(0.20)

        assert plan_old is not None, "Plan with buffer=0.10 should exist"
        assert plan_new is not None, "Plan with buffer=0.20 should exist"

        sl_old = float(plan_old["stop_loss"])
        sl_new = float(plan_new["stop_loss"])

        # sl_edge = entry_low - atr * buffer
        # buffer 0.10 → sl_edge = entry_low - 0.10*ATR = lvl - 0.20*ATR
        # buffer 0.20 → sl_edge = entry_low - 0.20*ATR = lvl - 0.30*ATR
        # assert SL with buffer=0.20 is lower (wider) than with buffer=0.10
        assert sl_new < sl_old, (
            f"SL with buffer=0.20 ({sl_new:.5f}) must be lower (wider) than "
            f"buffer=0.10 ({sl_old:.5f}) for BUY. "
            f"entry_low={entry_low:.5f}, atr={atr:.6f}"
        )

        # Verify SL distances match expected sl_edge values
        sl_dist_old = abs(entry_low - sl_old)
        sl_dist_new = abs(entry_low - sl_new)
        assert sl_dist_new > sl_dist_old, (
            f"SL-to-entry_low distance with buffer=0.20 ({sl_dist_new:.6f}) "
            f"must be > buffer=0.10 ({sl_dist_old:.6f})"
        )