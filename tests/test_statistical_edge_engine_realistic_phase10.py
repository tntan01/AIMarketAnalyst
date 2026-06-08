"""Phase 10.11: realistic journal-style data for 5 symbols.

Verifies evidence_score is stable, handles dirty data, respects sample
size thresholds, and never crashes on malformed inputs.
"""

from __future__ import annotations

from math import isnan

from core.statistical_edge_engine import calculate_evidence_score


def _trade(
    symbol: str,
    direction: str,
    result_r: float | str | None,
    *,
    regime: str = "ranging",
    status: str = "closed",
    closed_at: str = "2026-06-01T10:00:00",
) -> dict:
    return {
        "symbol": symbol,
        "direction": direction,
        "result_r": result_r,
        "result_pct": float(result_r) * 0.5 if isinstance(result_r, (int, float)) else 0.0,
        "regime": regime,
        "status": status,
        "closed_at": closed_at,
        "exit_reason": "tp" if (isinstance(result_r, (int, float)) and result_r > 0) else "sl",
        "actual_lot": 0.1,
        "planned_lot": 0.1,
        "m15_quality": "strict",
    }


# ---------------------------------------------------------------------------
# Dataset builders
# ---------------------------------------------------------------------------

# EURUSD buy: 60 trades, slightly positive edge
# 36 wins @ +1.0R, 24 losses @ -1.0R → win_rate=0.6, exp=0.6-0.4=0.20
_EURUSD_BUY = [
    *[_trade("EUR/USD", "BUY", 1.0, regime="trending_up") for _ in range(36)],
    *[_trade("eurusd", "buy", -1.0, regime="trending_up") for _ in range(24)],
]

# GBPJPY sell: 60 trades, negative edge
# 20 wins @ +1.0R, 40 losses @ -1.0R → win_rate=0.333, exp=-0.333
_GBPJPY_SELL = [
    *[_trade("GBP/JPY", "SELL", 1.0, regime="trending_down") for _ in range(20)],
    *[_trade("GBP-JPY", "sell", -1.0, regime="trending_down") for _ in range(40)],
]

# USDJPY buy: 20 trades, insufficient sample
_USDJPY_BUY = [
    *[_trade("USD/JPY", "BUY", 1.5, regime="ranging") for _ in range(12)],
    *[_trade("USD/JPY", "BUY", -1.0, regime="ranging") for _ in range(8)],
]

# XAUUSD buy: mixed clean + dirty data
_XAUUSD_BUY = [
    *[_trade("XAU/USD", "BUY", 2.0, regime="volatile") for _ in range(35)],
    *[_trade("XAUUSD", "buy", -1.5, regime="volatile") for _ in range(25)],
    # dirty entries
    {"symbol": "XAU/USD", "direction": "BUY", "result_r": "abc", "regime": "volatile", "closed_at": "2026-06-01T10:00:00"},
    {"symbol": "XAU/USD", "direction": "BUY", "result_r": None, "regime": "volatile", "closed_at": "2026-06-01T10:00:00"},
    {"symbol": "XAU/USD", "direction": "BUY", "status": "open", "result_r": 3.0},
    {"symbol": "XAU/USD", "direction": "BUY", "status": "pending", "result_r": 1.0, "regime": "volatile"},
]

# AUDUSD sell: mixed formats (AUD/USD, AUDUSD, short)
_AUDUSD_SELL = [
    *[_trade("AUD/USD", "SELL", 1.0, regime="ranging") for _ in range(30)],
    *[_trade("audusd", "short", -1.0, regime="ranging") for _ in range(30)],
]

ALL_TRADES = [*_EURUSD_BUY, *_GBPJPY_SELL, *_USDJPY_BUY, *_XAUUSD_BUY, *_AUDUSD_SELL]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _invariants(result: dict) -> None:
    assert 0 <= result["evidence_score"] <= 100
    assert isinstance(result["reason_codes"], list)
    assert isinstance(result["warning_codes"], list)
    assert "stats" in result
    assert "sample_size" in result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRealisticEvidenceScore:

    def test_eurusd_buy_positive_edge(self):
        result = calculate_evidence_score(ALL_TRADES, "EUR/USD", "buy", regime="trending_up")
        _invariants(result)
        assert result["evidence_score"] > 50
        assert result["group_used"] == "symbol_direction_regime"
        assert result["sample_size"] == 60

    def test_gbpjpy_sell_negative_edge(self):
        result = calculate_evidence_score(ALL_TRADES, "GBP/JPY", "sell", regime="trending_down")
        _invariants(result)
        assert result["evidence_score"] < 50
        assert result["group_used"] == "symbol_direction_regime"
        assert result["sample_size"] == 60

    def test_usdjpy_buy_insufficient_sample(self):
        result = calculate_evidence_score(ALL_TRADES, "USD/JPY", "buy", regime="ranging")
        _invariants(result)
        assert result["evidence_score"] == 50
        assert "STAT_EDGE_NOT_ENOUGH_DATA" in result["warning_codes"]
        assert result["sample_size"] == 20

    def test_xauusd_buy_filters_dirty_data(self):
        """60 clean trades + 4 dirty → 60 valid, not 64."""
        result = calculate_evidence_score(ALL_TRADES, "XAU/USD", "buy", regime="volatile")
        _invariants(result)
        # 35 wins + 25 losses = 60, dirty entries excluded
        assert result["sample_size"] == 60
        assert result["group_used"] == "symbol_direction_regime"

    def test_audusd_sell_normalizes_formats(self):
        """AUD/USD + audusd + short all map to same group."""
        result = calculate_evidence_score(ALL_TRADES, "AUD/USD", "sell", regime="ranging")
        _invariants(result)
        assert result["normalized_symbol"] == "AUDUSD"
        assert result["normalized_direction"] == "sell"
        assert result["sample_size"] == 60
        assert result["group_used"] == "symbol_direction_regime"

    def test_open_trades_not_counted(self):
        """Open and pending trades must not contribute to sample_size."""
        # XAUUSD has 1 open + 1 pending → should not affect count
        xau_only = [t for t in ALL_TRADES if isinstance(t, dict) and
                     str(t.get("symbol", "")).upper().replace("/", "") == "XAUUSD"]
        result = calculate_evidence_score(xau_only, "XAU/USD", "buy", regime="volatile")
        # 35 wins + 25 losses = 60 (open + pending excluded)
        assert result["sample_size"] == 60

    def test_nan_result_r_excluded(self):
        trades = [
            _trade("EUR/USD", "BUY", 1.0),
            _trade("EUR/USD", "BUY", float("nan")),
            _trade("EUR/USD", "BUY", 2.0),
        ]
        # Mark the NaN trade so it's kept in the dict but result_r is NaN
        result = calculate_evidence_score(trades, "EUR/USD", "buy")
        assert result["sample_size"] == 2  # NaN excluded

    def test_many_open_trades_does_not_crash(self):
        """Hundreds of open trades should not crash."""
        trades = [
            _trade("EUR/USD", "BUY", 1.0, status="open") for _ in range(200)
        ]
        result = calculate_evidence_score(trades, "EUR/USD", "buy")
        _invariants(result)
        assert result["sample_size"] == 0
        assert result["evidence_score"] == 50
