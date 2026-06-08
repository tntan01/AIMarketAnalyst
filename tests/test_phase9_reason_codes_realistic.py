"""Phase 9.6: comprehensive realistic tests for reason codes across all layers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.account_guard import check_account_guard
from core.entry_engine import evaluate_entry
from core.market_models import Candle
from core.signal_engine import score_scenario
from core.trade_gate_engine import check_trade_gates

UTC = timezone.utc
_M15_START = datetime(2026, 6, 1, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _add_m15(candles, o, h, l, c):
    t = len(candles)
    candles.append(Candle(_M15_START + timedelta(minutes=15 * t), o, h, l, c, 100))


def _m15_strict_bullish():
    c = []; p = 1.1000
    for _ in range(5): _add_m15(c, p, p + 0.0005, p - 0.0012, p - 0.0010); p -= 0.0010
    _add_m15(c, p, p + 0.0004, p - 0.0015, p + 0.0002); p = c[-1].close
    for _ in range(6): _add_m15(c, p, p + 0.0012, p - 0.0003, p + 0.0010); p += 0.0010
    for _ in range(4): _add_m15(c, p, p + 0.0004, p - 0.0010, p - 0.0008); p -= 0.0008
    _add_m15(c, p, p + 0.0004, p - 0.0010, p + 0.0003); p = c[-1].close
    for _ in range(7): _add_m15(c, p, p + 0.0010, p - 0.0003, p + 0.0008); p += 0.0008
    while len(c) < 47: _add_m15(c, p, p + 0.0013, p - 0.0003, p + 0.0010); p += 0.0010
    for _ in range(3): _add_m15(c, p, p + 0.0035, p - 0.0002, p + 0.0030); p += 0.0030
    return c


def _m15_loose_bullish():
    c = _m15_strict_bullish()
    for i in range(-3, 0): old = c[i]; c[i] = Candle(old.time, old.open, old.open + 0.0001, old.open - 0.0001, old.open + 0.00005, 100)
    return c


def _m15_none():
    c = []; p = 1.1000
    for i in range(20):
        d = 1 if i % 2 == 0 else -1; o = p; c2 = p + d * 0.0003
        _add_m15(c, o, o + 0.0020, o - 0.0020, c2); p = c2
    return c


def _h1_bullish():
    t0 = datetime(2026, 6, 1, 0, tzinfo=UTC)
    rows = [(1.100, 1.103, 1.098, 1.101), (1.101, 1.102, 1.097, 1.098), (1.098, 1.107, 1.095, 1.106)]
    return [Candle(t0 + timedelta(hours=i), o, h, l, c, 100) for i, (o, h, l, c) in enumerate(rows)]


def _tech():
    return {
        "price": 1.1000, "ema50_d1": 1.0900, "ema200_d1": 1.0700, "ema50_h4": 1.0950,
        "structure_h4": "HH/HL", "structure_d1": "HH/HL",
        "rsi_h4": 45.0, "rsi_h4_previous": 40.0,
        "macd_histogram_h4": {"value": 0.02, "previous_value": 0.01, "previous2_value": 0.0},
        "atr_h4": 0.005, "atr_d1": 0.008, "atr_avg_14d": 0.006,
        "support_zones": [{"level": 1.0900, "low": 1.0880, "high": 1.0920, "strength": "moderate", "confluence_count": 1, "consolidation_bars": 1}],
        "resistance_zones": [{"level": 1.1150, "low": 1.1130, "high": 1.1170, "strength": "weak", "confluence_count": 0, "consolidation_bars": 0}],
    }


def _smc():
    return {
        "H4": {"bos": True, "choch": False, "displacement": "bullish", "demand_zones": [
            {"type": "demand_zone", "zone_score": 80, "zone_location": "discount", "liquidity_sweep": True, "broken": False, "mitigated": False, "test_count": 0}
        ]},
        "H1": {"bos": True, "choch": False, "displacement": "bullish", "liquidity_sweeps": {"swept_lows": [1.09]}},
    }


def _bullish_entry_smc():
    return {"H1": {"displacement": "bullish", "bos": True}, "H4": {"displacement": "bullish", "bos": True, "premium_discount": "discount"}}


# ---------------------------------------------------------------------------
# Case 1 — Signal macro conflict
# ---------------------------------------------------------------------------


def test_signal_macro_conflict_penalty_code():
    result = score_scenario("buy", _tech(), _smc(), 12, 20, macro_confidence=1.0,
                            macro_context={"buy": 5, "sell": 25})
    assert "MACRO_CONFLICT" in result["penalty_codes"]
    assert result["macro_status"] == "conflict"
    assert result["macro_modifier"] == -15
    no_duplicates(result["reason_codes"])
    no_duplicates(result["penalty_codes"])


# ---------------------------------------------------------------------------
# Case 2 — Trade gate multiple warnings
# ---------------------------------------------------------------------------


def test_trade_gate_multiple_warnings():
    ctx = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "abnormal",
        "m15_quality": "none",
        "score_gap": 4,
        "expected_effective_rr": 1.1,
    }
    result = check_trade_gates(ctx)

    assert result["allowed"] is False
    assert result["decision_cap"] == "TRADE_BLOCKED"
    assert "SPREAD_ABNORMAL" in result["block_codes"]
    assert "M15_NOT_CONFIRMED" in result["warning_codes"]
    assert "BUY_SELL_SCORE_GAP_LOW" in result["warning_codes"]
    assert "EXPECTED_RR_TOO_LOW" in result["warning_codes"]
    no_duplicates(result["block_codes"])
    no_duplicates(result["warning_codes"])


# ---------------------------------------------------------------------------
# Case 3 — Account guard daily loss
# ---------------------------------------------------------------------------


def test_account_guard_daily_loss_code():
    today = datetime.now(UTC)
    trades = [{"closed_at": today.isoformat(), "result_pct": -2.1}]
    result = check_account_guard(
        closed_trades=trades,
        settings={"max_daily_loss_pct": 2.0, "trader_timezone": "UTC"},
        action="open_new_trade",
        now=today,
    )
    assert result["blocked"] is True
    assert result["allowed"] is False
    assert "DAILY_LOSS_LIMIT_REACHED" in result["block_codes"]
    no_duplicates(result["block_codes"])


# ---------------------------------------------------------------------------
# Case 4 — Entry M15 codes
# ---------------------------------------------------------------------------


def test_entry_m15_strict_reason_code():
    r = evaluate_entry(side="buy", technical={"price": 1.101, "atr_h4": 0.01},
                       smc=_bullish_entry_smc(), h1_candles=_h1_bullish(),
                       entry_zone=[1.098, 1.104], m15_candles=_m15_strict_bullish())
    assert r["entry_status"] == "confirmed_entry"
    assert "M15_STRICT_CONFIRMED" in r["reason_codes"]
    no_duplicates(r["reason_codes"])


def test_entry_m15_loose_warning_code():
    r = evaluate_entry(side="buy", technical={"price": 1.101, "atr_h4": 0.01},
                       smc=_bullish_entry_smc(), h1_candles=_h1_bullish(),
                       entry_zone=[1.098, 1.104], m15_candles=_m15_loose_bullish())
    assert r["entry_status"] == "waiting_confirmation"
    assert "M15_LOOSE_CONFIRMATION" in r["warning_codes"]
    no_duplicates(r["warning_codes"])


def test_entry_m15_none_warning_code():
    r = evaluate_entry(side="buy", technical={"price": 1.101, "atr_h4": 0.01},
                       smc=_bullish_entry_smc(), h1_candles=_h1_bullish(),
                       entry_zone=[1.098, 1.104], m15_candles=_m15_none())
    assert r["entry_status"] == "watch_zone"
    assert "M15_NOT_CONFIRMED" in r["warning_codes"]
    no_duplicates(r["warning_codes"])


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def no_duplicates(codes: list[str]) -> None:
    assert len(codes) == len(set(codes)), f"duplicates found: {codes}"
