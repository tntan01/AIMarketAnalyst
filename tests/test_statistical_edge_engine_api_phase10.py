"""Phase 10.10: verify calculate_evidence_score() main API."""

from __future__ import annotations

from core.statistical_edge_engine import (
    DEFAULT_EVIDENCE_SCORE,
    STRONG_SAMPLE_SIZE,
    calculate_evidence_score,
)


def _trade(symbol: str, direction: str, result_r: float, regime: str) -> dict:
    return {
        "symbol": symbol, "direction": direction,
        "result_r": result_r, "regime": regime,
        "closed_at": "2026-06-01T10:00:00",
    }


# 60 EURUSD buy ranging — enough for symbol_direction_regime group
_EURUSD_RANGING = [_trade("EUR/USD", "BUY", 1.5 if i % 2 == 0 else -1.0, "ranging") for i in range(60)]
# 10 EURUSD buy volatile — not enough on its own
_EURUSD_VOLATILE = [_trade("EUR/USD", "BUY", 0.3, "volatile") for _ in range(10)]
# All EURUSD buy trades = 70 total — enough for symbol_direction
_EURUSD_ALL = [*_EURUSD_RANGING, *_EURUSD_VOLATILE]
# 20 GBPJPY sell — not enough for any group
_GBPJPY_SELL = [_trade("GBP/JPY", "sell", -1.0 if i % 2 == 0 else 0.5, "ranging") for i in range(20)]


# ---------------------------------------------------------------------------
# Case 1: sufficient symbol_direction_regime
# ---------------------------------------------------------------------------


class TestSufficientRegimeGroup:
    def test_eurusd_buy_ranging_returns_score_above_50(self):
        result = calculate_evidence_score(_EURUSD_ALL, "EUR/USD", "buy", regime="ranging")
        assert result["evidence_score"] > 50
        assert result["group_used"] == "symbol_direction_regime"
        assert result["normalized_symbol"] == "EURUSD"
        assert result["normalized_direction"] == "buy"
        assert result["normalized_regime"] == "ranging"

    def test_has_all_required_keys(self):
        result = calculate_evidence_score(_EURUSD_ALL, "EUR/USD", "buy", regime="ranging")
        for key in ("evidence_score", "sample_size", "confidence",
                     "reason_codes", "warning_codes", "stats",
                     "group_used", "normalized_symbol",
                     "normalized_direction", "normalized_regime"):
            assert key in result, f"missing key: {key}"


# ---------------------------------------------------------------------------
# Case 2: regime insufficient but symbol_direction sufficient → fallback
# ---------------------------------------------------------------------------


class TestFallbackSymbolDirection:
    def test_volatile_regime_falls_back_to_symbol_direction(self):
        result = calculate_evidence_score(_EURUSD_ALL, "EUR/USD", "buy", regime="volatile")
        # Only 10 volatile trades < 50, falls back to symbol_direction (70)
        assert result["group_used"] == "symbol_direction"
        assert result["sample_size"] == 70
        assert result["normalized_regime"] == "volatile"


# ---------------------------------------------------------------------------
# Case 3: insufficient samples → neutral
# ---------------------------------------------------------------------------


class TestInsufficientSamples:
    def test_gbpjpy_sell_20_trades_returns_score_50(self):
        result = calculate_evidence_score(_GBPJPY_SELL, "GBP/JPY", "sell", regime="ranging")
        assert result["evidence_score"] == DEFAULT_EVIDENCE_SCORE
        assert result["confidence"] == "low"
        assert "STAT_EDGE_NOT_ENOUGH_DATA" in result["warning_codes"]
        assert result["group_used"] is None
        assert result["normalized_symbol"] == "GBPJPY"
        assert result["normalized_direction"] == "sell"

    def test_gbpjpy_sell_stats_still_computed(self):
        result = calculate_evidence_score(_GBPJPY_SELL, "GBP/JPY", "sell")
        assert result["stats"]["sample_size"] == 20


# ---------------------------------------------------------------------------
# Case 4: invalid input → neutral, no crash
# ---------------------------------------------------------------------------


class TestInvalidInput:
    def test_none_trades_returns_neutral(self):
        result = calculate_evidence_score(None, "EUR/USD", "buy")
        assert result["evidence_score"] == DEFAULT_EVIDENCE_SCORE
        assert result["sample_size"] == 0

    def test_invalid_direction_returns_neutral(self):
        result = calculate_evidence_score(_EURUSD_ALL, "EUR/USD", "hold")
        assert result["evidence_score"] == DEFAULT_EVIDENCE_SCORE
        assert result["normalized_direction"] is None

    def test_empty_symbol_returns_neutral(self):
        result = calculate_evidence_score(_EURUSD_ALL, "", "buy")
        assert result["evidence_score"] == DEFAULT_EVIDENCE_SCORE
        assert result["normalized_symbol"] is None


# ---------------------------------------------------------------------------
# Case 5: regime alias from analysis_engine (trend_up / trend_down)
# ---------------------------------------------------------------------------

# 60 EURUSD buy trending_up — enough for symbol_direction_regime
_EURUSD_TRENDING_UP = [
    _trade("EUR/USD", "BUY", 0.4 if i % 2 == 0 else -0.2, "trending_up")
    for i in range(60)
]
# 60 EURUSD sell trending_down — enough for symbol_direction_regime
_EURUSD_TRENDING_DOWN = [
    _trade("EUR/USD", "SELL", -0.3 if i % 2 == 0 else 0.5, "trending_down")
    for i in range(60)
]


class TestRegimeAliasFromAnalysisEngine:
    """calculate_evidence_score must accept regime='trend_up' / 'trend_down'
    as passed by analysis_engine and correctly match journal trades stored
    with canonical regime='trending_up' / 'trending_down'."""

    def test_trend_up_alias_selects_trending_up_group(self):
        result = calculate_evidence_score(
            _EURUSD_TRENDING_UP, "EUR/USD", "buy", regime="trend_up"
        )
        assert result["normalized_regime"] == "trending_up", (
            f"trend_up must normalise to trending_up, got {result['normalized_regime']}"
        )
        assert result["group_used"] == "symbol_direction_regime", (
            f"Expected symbol_direction_regime, got {result['group_used']}"
        )
        assert result["sample_size"] >= STRONG_SAMPLE_SIZE, (
            f"Sample size {result['sample_size']} < {STRONG_SAMPLE_SIZE}"
        )
        # Positive expectancy → score above neutral
        assert result["evidence_score"] != DEFAULT_EVIDENCE_SCORE, (
            f"Expected non-neutral score, got {result['evidence_score']}"
        )

    def test_trend_down_alias_selects_trending_down_group(self):
        result = calculate_evidence_score(
            _EURUSD_TRENDING_DOWN, "EUR/USD", "sell", regime="trend_down"
        )
        assert result["normalized_regime"] == "trending_down", (
            f"trend_down must normalise to trending_down, got {result['normalized_regime']}"
        )
        assert result["group_used"] == "symbol_direction_regime", (
            f"Expected symbol_direction_regime, got {result['group_used']}"
        )
        assert result["sample_size"] >= STRONG_SAMPLE_SIZE

    def test_normalized_fields_consistent_for_alias_query(self):
        result = calculate_evidence_score(
            _EURUSD_TRENDING_UP, "EUR/USD", "buy", regime="trend_up"
        )
        assert result["normalized_symbol"] == "EURUSD"
        assert result["normalized_direction"] == "buy"
        assert result["normalized_regime"] == "trending_up"

    def test_trend_up_alias_falls_back_to_symbol_direction_when_regime_insufficient(self):
        """If trending_up trades are too few, engine falls back to
        symbol_direction group and returns neutral score."""
        # Only 10 trades — insufficient for regime group
        small = [_trade("EUR/USD", "BUY", 0.3, "trending_up") for _ in range(10)]
        all_trades = [*small, *_EURUSD_RANGING[:50]]  # 10 trend_up + 50 ranging
        result = calculate_evidence_score(
            all_trades, "EUR/USD", "buy", regime="trend_up"
        )
        # regime group (10) < STRONG_SAMPLE_SIZE → falls back to symbol_direction
        assert result["group_used"] == "symbol_direction", (
            f"Expected fallback to symbol_direction, got {result['group_used']}"
        )
        assert result["normalized_regime"] == "trending_up"
