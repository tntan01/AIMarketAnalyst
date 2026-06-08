"""Phase 9.4: verify entry_engine outputs reason_codes, warning_codes, block_codes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.entry_engine import evaluate_entry
from core.market_models import Candle

UTC = timezone.utc
_M15_START = datetime(2026, 6, 1, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_h1(rows):
    return [Candle(datetime(2026, 6, 1, tzinfo=UTC) + timedelta(hours=i), o, h, l, c, 100)
            for i, (o, h, l, c) in enumerate(rows)]


def _h1_bullish():
    return _make_h1([(1.100, 1.103, 1.098, 1.101), (1.101, 1.102, 1.097, 1.098), (1.098, 1.107, 1.095, 1.106)])


def _h1_bearish():
    return _make_h1([(1.100, 1.103, 1.098, 1.101), (1.101, 1.104, 1.100, 1.103), (1.103, 1.104, 1.095, 1.096)])


def _add_m15(candles, o, h, l, c):
    t = len(candles)
    candles.append(Candle(_M15_START + timedelta(minutes=15 * t), o, h, l, c, 100))


def _m15_strict_bullish():
    candles = []; p = 1.1000
    for _ in range(5): _add_m15(candles, p, p + 0.0005, p - 0.0012, p - 0.0010); p -= 0.0010
    _add_m15(candles, p, p + 0.0004, p - 0.0015, p + 0.0002); p = candles[-1].close
    for _ in range(6): _add_m15(candles, p, p + 0.0012, p - 0.0003, p + 0.0010); p += 0.0010
    for _ in range(4): _add_m15(candles, p, p + 0.0004, p - 0.0010, p - 0.0008); p -= 0.0008
    _add_m15(candles, p, p + 0.0004, p - 0.0010, p + 0.0003); p = candles[-1].close
    for _ in range(7): _add_m15(candles, p, p + 0.0010, p - 0.0003, p + 0.0008); p += 0.0008
    while len(candles) < 47: _add_m15(candles, p, p + 0.0013, p - 0.0003, p + 0.0010); p += 0.0010
    for _ in range(3): _add_m15(candles, p, p + 0.0035, p - 0.0002, p + 0.0030); p += 0.0030
    return candles


def _m15_loose_bullish():
    c = _m15_strict_bullish()
    for i in range(-3, 0): old = c[i]; c[i] = Candle(old.time, old.open, old.open + 0.0001, old.open - 0.0001, old.open + 0.00005, 100)
    return c


def _m15_none():
    candles = []; p = 1.1000
    for i in range(20):
        d = 1 if i % 2 == 0 else -1; o = p; c2 = p + d * 0.0003
        _add_m15(candles, o, o + 0.0020, o - 0.0020, c2); p = c2
    return candles


def _bullish_smc():
    return {"H1": {"displacement": "bullish", "bos": True}, "H4": {"displacement": "bullish", "bos": True, "premium_discount": "discount"}}


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


class TestEntryEngineReasonCodes:
    """Verify evaluate_entry() outputs standardised reason/warning/block codes."""

    def test_all_outputs_have_code_lists(self):
        """Every evaluate_entry result must have reason/warning/block_codes as lists."""
        result = evaluate_entry(
            side="buy",
            technical={"price": 1.101, "atr_h4": 0.01},
            smc=_bullish_smc(),
            h1_candles=_h1_bullish(),
            entry_zone=[1.098, 1.104],
            m15_candles=_m15_strict_bullish(),
        )
        assert isinstance(result["reason_codes"], list)
        assert isinstance(result["warning_codes"], list)
        assert isinstance(result["block_codes"], list)

    def test_strict_confirmed_has_m15_strict_code(self):
        result = evaluate_entry(
            side="buy",
            technical={"price": 1.101, "atr_h4": 0.01},
            smc=_bullish_smc(),
            h1_candles=_h1_bullish(),
            entry_zone=[1.098, 1.104],
            m15_candles=_m15_strict_bullish(),
        )
        assert result["entry_status"] == "confirmed_entry"
        assert "M15_STRICT_CONFIRMED" in result["reason_codes"]
        assert result["ready_to_trade"] is True

    def test_loose_has_m15_loose_warning(self):
        result = evaluate_entry(
            side="buy",
            technical={"price": 1.101, "atr_h4": 0.01},
            smc=_bullish_smc(),
            h1_candles=_h1_bullish(),
            entry_zone=[1.098, 1.104],
            m15_candles=_m15_loose_bullish(),
        )
        assert result["entry_status"] == "waiting_confirmation"
        assert "M15_LOOSE_CONFIRMATION" in result["warning_codes"]
        assert result["ready_to_trade"] is False

    def test_none_has_m15_not_confirmed_warning(self):
        result = evaluate_entry(
            side="buy",
            technical={"price": 1.101, "atr_h4": 0.01},
            smc=_bullish_smc(),
            h1_candles=_h1_bullish(),
            entry_zone=[1.098, 1.104],
            m15_candles=_m15_none(),
        )
        assert result["entry_status"] == "watch_zone"
        assert "M15_NOT_CONFIRMED" in result["warning_codes"]
        assert result["ready_to_trade"] is False

    def test_missing_m15_has_unavailable_warning(self):
        result = evaluate_entry(
            side="buy",
            technical={"price": 1.101, "atr_h4": 0.01},
            smc=_bullish_smc(),
            h1_candles=_h1_bullish(),
            entry_zone=[1.098, 1.104],
        )
        assert result["entry_status"] != "confirmed_entry"
        assert "M15_DATA_UNAVAILABLE" in result["warning_codes"]
        assert result["ready_to_trade"] is False

    def test_zone_broken_has_zone_broken_warning(self):
        # buy side: broken when price < entry_zone_low - atr * 0.25
        # entry_zone=[1.098, 1.104], atr=0.01 -> broken if price < 1.098 - 0.0025 = 1.0955
        result = evaluate_entry(
            side="buy",
            technical={"price": 1.094, "atr_h4": 0.01},
            smc=_bullish_smc(),
            h1_candles=_h1_bullish(),
            entry_zone=[1.098, 1.104],
        )
        assert result["entry_status"] == "invalidated"
        assert "ZONE_BROKEN" in result["warning_codes"]

    def test_strict_no_false_warning_codes(self):
        """M15 strict must NOT have loose/none/unavailable warnings."""
        result = evaluate_entry(
            side="buy",
            technical={"price": 1.101, "atr_h4": 0.01},
            smc=_bullish_smc(),
            h1_candles=_h1_bullish(),
            entry_zone=[1.098, 1.104],
            m15_candles=_m15_strict_bullish(),
        )
        assert "M15_LOOSE_CONFIRMATION" not in result["warning_codes"]
        assert "M15_NOT_CONFIRMED" not in result["warning_codes"]
        assert "M15_DATA_UNAVAILABLE" not in result["warning_codes"]

    def test_no_duplicate_codes(self):
        result = evaluate_entry(
            side="buy",
            technical={"price": 1.101, "atr_h4": 0.01},
            smc=_bullish_smc(),
            h1_candles=_h1_bullish(),
            entry_zone=[1.098, 1.104],
            m15_candles=_m15_strict_bullish(),
        )
        assert len(result["reason_codes"]) == len(set(result["reason_codes"]))
        assert len(result["warning_codes"]) == len(set(result["warning_codes"]))
        assert len(result["block_codes"]) == len(set(result["block_codes"]))
