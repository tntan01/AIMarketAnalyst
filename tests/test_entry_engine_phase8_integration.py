"""Phase 8 integration tests: verify M15 quality flows through build_trade_plan().

Ensures that scenarios built by core/risk_engine.py respect Phase 8 M15 rules:
  - M15 strict => scenario can be confirmed_entry
  - M15 loose => entry_status == waiting_confirmation, ready_to_trade is False
  - M15 none => entry_status == watch_zone, ready_to_trade is False
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.market_models import Candle
from core.risk_engine import AnalysisInput, build_trade_plan

UTC = timezone.utc
_M15_START = datetime(2026, 6, 1, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _request(symbol: str = "EUR/USD") -> AnalysisInput:
    return AnalysisInput(
        symbol=symbol,
        broker_symbol="EURUSD",
        account_balance=10_000,
        risk_percent=1,
    )


def _make_h1(rows: list[tuple[float, float, float, float]]) -> list[Candle]:
    base = datetime(2026, 6, 1, 0, tzinfo=UTC)
    return [
        Candle(base + timedelta(hours=i), o, h, l, c, 100)
        for i, (o, h, l, c) in enumerate(rows)
    ]


def _h1_bullish_engulfing() -> list[Candle]:
    """H1 candles: last candle is a bullish engulfing."""
    return _make_h1(
        [
            (1.100, 1.103, 1.098, 1.101),
            (1.101, 1.102, 1.097, 1.098),
            (1.098, 1.107, 1.095, 1.106),
        ]
    )


def _h1_bearish_engulfing() -> list[Candle]:
    """H1 candles: last candle is a bearish engulfing."""
    return _make_h1(
        [
            (1.100, 1.103, 1.098, 1.101),
            (1.101, 1.104, 1.100, 1.103),
            (1.103, 1.104, 1.095, 1.096),
        ]
    )


# -- M15 candle generators (verified in Phase 8.1) --


def _add_m15(candles: list[Candle], o: float, h: float, l: float, c: float) -> None:
    t = len(candles)
    candles.append(Candle(_M15_START + timedelta(minutes=15 * t), o, h, l, c, 100))


def _m15_strict_bullish() -> list[Candle]:
    candles: list[Candle] = []
    p = 1.1000
    for _ in range(5):
        _add_m15(candles, p, p + 0.0005, p - 0.0012, p - 0.0010)
        p -= 0.0010
    _add_m15(candles, p, p + 0.0004, p - 0.0015, p + 0.0002)
    p = candles[-1].close
    for _ in range(6):
        _add_m15(candles, p, p + 0.0012, p - 0.0003, p + 0.0010)
        p += 0.0010
    for _ in range(4):
        _add_m15(candles, p, p + 0.0004, p - 0.0010, p - 0.0008)
        p -= 0.0008
    _add_m15(candles, p, p + 0.0004, p - 0.0010, p + 0.0003)
    p = candles[-1].close
    for _ in range(7):
        _add_m15(candles, p, p + 0.0010, p - 0.0003, p + 0.0008)
        p += 0.0008
    while len(candles) < 47:
        _add_m15(candles, p, p + 0.0013, p - 0.0003, p + 0.0010)
        p += 0.0010
    for _ in range(3):
        _add_m15(candles, p, p + 0.0035, p - 0.0002, p + 0.0030)
        p += 0.0030
    return candles


def _m15_strict_bearish() -> list[Candle]:
    candles: list[Candle] = []
    p = 1.1000
    for _ in range(5):
        _add_m15(candles, p, p + 0.0012, p - 0.0005, p + 0.0010)
        p += 0.0010
    _add_m15(candles, p, p + 0.0015, p - 0.0004, p - 0.0002)
    p = candles[-1].close
    for _ in range(6):
        _add_m15(candles, p, p + 0.0003, p - 0.0012, p - 0.0010)
        p -= 0.0010
    for _ in range(4):
        _add_m15(candles, p, p + 0.0010, p - 0.0004, p + 0.0008)
        p += 0.0008
    _add_m15(candles, p, p + 0.0010, p - 0.0004, p - 0.0003)
    p = candles[-1].close
    for _ in range(7):
        _add_m15(candles, p, p + 0.0003, p - 0.0010, p - 0.0008)
        p -= 0.0008
    while len(candles) < 47:
        _add_m15(candles, p, p + 0.0005, p - 0.0013, p - 0.0010)
        p -= 0.0010
    for _ in range(3):
        _add_m15(candles, p, p + 0.0002, p - 0.0035, p - 0.0030)
        p -= 0.0030
    return candles


def _m15_loose_bullish() -> list[Candle]:
    candles = _m15_strict_bullish()
    for i in range(-3, 0):
        old = candles[i]
        candles[i] = Candle(old.time, old.open, old.open + 0.0001, old.open - 0.0001, old.open + 0.00005, 100)
    return candles


def _m15_loose_bearish() -> list[Candle]:
    candles = _m15_strict_bearish()
    for i in range(-3, 0):
        old = candles[i]
        candles[i] = Candle(old.time, old.open, old.open + 0.0001, old.open - 0.0001, old.open - 0.00005, 100)
    return candles


def _m15_none() -> list[Candle]:
    candles: list[Candle] = []
    p = 1.1000
    for i in range(20):
        direction = 1 if i % 2 == 0 else -1
        o = p
        c = p + direction * 0.0003
        _add_m15(candles, o, o + 0.0020, o - 0.0020, c)
        p = c
    return candles


# -- SMC helpers --


def _bullish_smc() -> dict:
    return {
        "H1": {"displacement": "bullish", "bos": True},
        "H4": {
            "displacement": "bullish",
            "bos": True,
            "premium_discount": "discount",
            "demand_zones": [
                {"low": 1.0960, "high": 1.0980, "type": "demand", "strength": "strong"}
            ],
        },
    }


def _bearish_smc() -> dict:
    return {
        "H1": {"displacement": "bearish", "bos": True},
        "H4": {
            "displacement": "bearish",
            "bos": True,
            "premium_discount": "premium",
            "supply_zones": [
                {"low": 1.1040, "high": 1.1060, "type": "supply", "strength": "strong"}
            ],
        },
    }


# -- technical context builders --


def _technical_buy_setup(price: float = 1.1010) -> dict:
    """Technical context for a buy setup with price near support.

    atr_h4=0.01, support at 1.1000, entry zone = [1.0980, 1.1020].
    price=1.1010 sits inside the entry zone.
    """
    return {
        "price": price,
        "atr_h4": 0.01,
        "atr_d1": None,
        "support_zones": [{"level": 1.1000, "strength": "strong"}],
        "resistance_zones": [
            {"level": 1.1100, "strength": "strong"},
            {"level": 1.1200, "strength": "moderate"},
        ],
    }


def _technical_sell_setup(price: float = 1.1040) -> dict:
    """Technical context for a sell setup with price near resistance.

    atr_h4=0.01, resistance at 1.1050, entry zone = [1.1030, 1.1070].
    price=1.1040 sits inside the entry zone.
    """
    return {
        "price": price,
        "atr_h4": 0.01,
        "atr_d1": None,
        "support_zones": [
            {"level": 1.0980, "strength": "moderate"},
            {"level": 1.0900, "strength": "strong"},
        ],
        "resistance_zones": [{"level": 1.1050, "strength": "strong"}],
    }


# ---------------------------------------------------------------------------
# Phase 8 integration tests
# ---------------------------------------------------------------------------


class TestPhase8IntegrationBuildTradePlan:
    """Verify M15 quality flows through build_trade_plan() into scenario output."""

    # -- Case 1: M15 strict => confirmed_entry (buy) --------------------------

    def test_build_trade_plan_m15_strict_buy_confirms(self):
        plan = build_trade_plan(
            "buy",
            _request("EUR/USD"),
            _technical_buy_setup(price=1.1010),
            _bullish_smc(),
            _h1_bullish_engulfing(),
            m15_candles=_m15_strict_bullish(),
        )
        assert plan is not None, "plan should not be None"
        assert plan["m15_quality"] == "strict", f"expected strict, got {plan.get('m15_quality')}"
        assert plan["m15_available"] is True
        assert plan["m15_checked"] is True
        assert plan["entry_status"] == "confirmed_entry", (
            f"strict M15 must give confirmed_entry, got {plan['entry_status']}"
        )
        assert plan["ready_to_trade"] is True
        assert plan["price_in_entry_zone"] is True
        # Plan-level keys still present
        assert "entry_zone" in plan
        assert "stop_loss" in plan
        assert "take_profit" in plan
        assert "expected_effective_rr" in plan
        assert "position_sizing" in plan

    # -- Case 2: M15 loose => waiting_confirmation (buy) ----------------------

    def test_build_trade_plan_m15_loose_buy_demotes(self):
        plan = build_trade_plan(
            "buy",
            _request("EUR/USD"),
            _technical_buy_setup(price=1.1010),
            _bullish_smc(),
            _h1_bullish_engulfing(),
            m15_candles=_m15_loose_bullish(),
        )
        assert plan is not None
        assert plan["m15_quality"] == "loose", f"expected loose, got {plan.get('m15_quality')}"
        assert plan["entry_status"] == "waiting_confirmation", (
            f"loose M15 must give waiting_confirmation, got {plan['entry_status']}"
        )
        assert plan["ready_to_trade"] is False
        # Trade plan infrastructure still intact
        assert "entry_zone" in plan
        assert "stop_loss" in plan
        assert "take_profit" in plan
        assert "expected_effective_rr" in plan

    # -- Case 3: M15 none => watch_zone (buy) ---------------------------------

    def test_build_trade_plan_m15_none_buy_demotes(self):
        plan = build_trade_plan(
            "buy",
            _request("EUR/USD"),
            _technical_buy_setup(price=1.1010),
            _bullish_smc(),
            _h1_bullish_engulfing(),
            m15_candles=_m15_none(),
        )
        assert plan is not None
        assert plan["m15_quality"] == "none", f"expected none, got {plan.get('m15_quality')}"
        assert plan["entry_status"] == "watch_zone", (
            f"none M15 must give watch_zone, got {plan['entry_status']}"
        )
        assert plan["ready_to_trade"] is False
        assert plan["price_in_entry_zone"] is False  # watch_zone sets this to False
        # Trade plan infrastructure still intact
        assert "entry_zone" in plan
        assert "stop_loss" in plan
        assert "take_profit" in plan
        assert "expected_effective_rr" in plan

    # -- Case 4: M15 strict => confirmed_entry (sell) -------------------------

    def test_build_trade_plan_m15_strict_sell_confirms(self):
        plan = build_trade_plan(
            "sell",
            _request("EUR/USD"),
            _technical_sell_setup(price=1.1040),
            _bearish_smc(),
            _h1_bearish_engulfing(),
            m15_candles=_m15_strict_bearish(),
        )
        assert plan is not None
        assert plan["m15_quality"] == "strict", f"expected strict, got {plan.get('m15_quality')}"
        assert plan["entry_status"] == "confirmed_entry", (
            f"strict M15 sell must give confirmed_entry, got {plan['entry_status']}"
        )
        assert plan["ready_to_trade"] is True
        assert "entry_zone" in plan
        assert "stop_loss" in plan
        assert "take_profit" in plan
        assert "expected_effective_rr" in plan

    # -- Case 5: M15 loose (sell) => waiting_confirmation ---------------------

    def test_build_trade_plan_m15_loose_sell_demotes(self):
        plan = build_trade_plan(
            "sell",
            _request("EUR/USD"),
            _technical_sell_setup(price=1.1040),
            _bearish_smc(),
            _h1_bearish_engulfing(),
            m15_candles=_m15_loose_bearish(),
        )
        assert plan is not None
        assert plan["m15_quality"] == "loose", f"expected loose, got {plan.get('m15_quality')}"
        assert plan["entry_status"] == "waiting_confirmation", (
            f"loose M15 sell must give waiting_confirmation, got {plan['entry_status']}"
        )
        assert plan["ready_to_trade"] is False
        assert "expected_effective_rr" in plan

    # -- Case 6: Missing M15 => cap at waiting_confirmation -------------------

    def test_build_trade_plan_missing_m15_caps_at_waiting(self):
        plan = build_trade_plan(
            "buy",
            _request("EUR/USD"),
            _technical_buy_setup(price=1.1010),
            _bullish_smc(),
            _h1_bullish_engulfing(),
            # m15_candles deliberately omitted
        )
        assert plan is not None
        assert plan["m15_available"] is False
        assert plan["entry_status"] != "confirmed_entry", (
            f"missing M15 must not auto-confirm, got {plan['entry_status']}"
        )
        assert plan["ready_to_trade"] is False
        assert plan["entry_status"] in ("waiting_confirmation", "watch_zone"), (
            f"missing M15 must cap at waiting_confirmation/watch_zone, got {plan['entry_status']}"
        )
        assert "entry_zone" in plan
        assert "stop_loss" in plan
        assert "take_profit" in plan
