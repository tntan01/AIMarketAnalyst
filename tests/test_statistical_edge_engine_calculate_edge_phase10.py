"""Phase 10.6: verify calculate_edge() end-to-end."""

from __future__ import annotations

from core.statistical_edge_engine import calculate_edge


def _make_trades(wins: int, losses: int, win_r: float = 1.2, loss_r: float = -1.0) -> list[dict]:
    """Build a list of trade dicts with specified win/loss ratio."""
    trades: list[dict] = []
    for i in range(wins):
        trades.append({
            "symbol": "EUR/USD", "direction": "buy",
            "result_r": win_r, "closed_at": f"2026-06-0{i+1}T10:00:00",
        })
    for i in range(losses):
        trades.append({
            "symbol": "EUR/USD", "direction": "buy",
            "result_r": loss_r, "closed_at": f"2026-06-{wins+i+1}T10:00:00",
        })
    return trades


# ---------------------------------------------------------------------------
# Case 1: insufficient sample (< 30)
# ---------------------------------------------------------------------------


class TestInsufficientSample:
    def test_10_trades_returns_score_50(self):
        trades = _make_trades(7, 3, win_r=1.5, loss_r=-1.0)
        result = calculate_edge(trades)
        assert result["evidence_score"] == 50
        assert result["sample_size"] == 10
        assert result["confidence"] == "low"
        assert "STAT_EDGE_NOT_ENOUGH_DATA" in result["warning_codes"]
        assert "STAT_EDGE_NOT_ENOUGH_DATA" in result["reason_codes"]

    def test_empty_list_returns_neutral(self):
        result = calculate_edge([])
        assert result["evidence_score"] == 50
        assert result["sample_size"] == 0
        assert result["confidence"] == "low"

    def test_none_returns_neutral(self):
        result = calculate_edge(None)
        assert result["evidence_score"] == 50
        assert result["sample_size"] == 0


# ---------------------------------------------------------------------------
# Case 2: sufficient sample, positive edge
# 24 wins * 1.2 + 16 losses * -1.0 on 40 trades
# win_rate = 24/40 = 0.6, avg_win=1.2, avg_loss=1.0
# expectancy = 0.6*1.2 - 0.4*1.0 = 0.72 - 0.40 = 0.32
# map: 0.32 >= 0.30 => 75
# ---------------------------------------------------------------------------


class TestPositiveEdge:
    def test_40_trades_positive_edge_score_above_50(self):
        trades = _make_trades(24, 16, win_r=1.2, loss_r=-1.0)
        result = calculate_edge(trades)
        assert result["evidence_score"] > 50
        assert result["sample_size"] == 40
        assert "STAT_EDGE_POSITIVE" in result["reason_codes"]
        assert result["stats"]["win_rate"] == 0.6
        assert result["stats"]["expectancy_r"] == 0.72 - 0.40  # 0.32

    def test_40_trades_positive_edge_score_is_75(self):
        trades = _make_trades(24, 16, win_r=1.2, loss_r=-1.0)
        result = calculate_edge(trades)
        # expectancy=0.32 → >=0.30 → 75
        assert result["evidence_score"] == 75


# ---------------------------------------------------------------------------
# Case 3: sufficient sample, negative edge
# 16 wins * 1.0 + 24 losses * -1.0 on 40 trades
# win_rate = 16/40 = 0.4, avg_win=1.0, avg_loss=1.0
# expectancy = 0.4*1.0 - 0.6*1.0 = -0.20
# map: -0.20 <= -0.15 => 35
# ---------------------------------------------------------------------------


class TestNegativeEdge:
    def test_40_trades_negative_edge_score_below_50(self):
        trades = _make_trades(16, 24, win_r=1.0, loss_r=-1.0)
        result = calculate_edge(trades)
        assert result["evidence_score"] < 50
        assert result["sample_size"] == 40
        assert "STAT_EDGE_NEGATIVE" in result["reason_codes"]
        assert result["stats"]["win_rate"] == 0.4
        assert result["stats"]["expectancy_r"] == 0.4 - 0.6  # -0.20

    def test_40_trades_negative_edge_score_is_35(self):
        trades = _make_trades(16, 24, win_r=1.0, loss_r=-1.0)
        result = calculate_edge(trades)
        # expectancy=-0.20 → <= -0.15 → 35
        assert result["evidence_score"] == 35


# ---------------------------------------------------------------------------
# Case 4: dirty data — handles None, NaN, open trades, bad strings
# ---------------------------------------------------------------------------


class TestDirtyData:
    def test_dirty_data_does_not_crash(self):
        trades = [
            *(_make_trades(5, 5, win_r=1.5, loss_r=-1.0)),
            {"symbol": "XAU/USD", "status": "open", "result_r": None},
            {"symbol": "XAU/USD", "result_r": "abc", "closed_at": "2026-06-15T10:00:00"},
            {"symbol": "XAU/USD", "result_r": float("nan"), "closed_at": "2026-06-16T10:00:00"},
            None,  # type: ignore
            {"symbol": "XAU/USD", "result_r": "1.5", "closed_at": "2026-06-17T10:00:00"},
            "not_a_dict",  # type: ignore
        ]
        result = calculate_edge(trades)  # type: ignore[arg-type]
        # Only the 10 clean trades + 1 string "1.5" = 11 valid
        assert result["sample_size"] == 11
        assert result["evidence_score"] == 50  # < 30 -> neutral
        assert "STAT_EDGE_NOT_ENOUGH_DATA" in result["warning_codes"]


# ---------------------------------------------------------------------------
# Additional: high confidence
# ---------------------------------------------------------------------------


class TestConfidenceTiers:
    def test_50_trades_medium_confidence(self):
        trades = _make_trades(30, 20, win_r=1.2, loss_r=-1.0)
        result = calculate_edge(trades)
        assert result["sample_size"] == 50
        assert result["confidence"] == "medium"

    def test_100_trades_high_confidence(self):
        trades = _make_trades(60, 40, win_r=1.2, loss_r=-1.0)
        result = calculate_edge(trades)
        assert result["sample_size"] == 100
        assert result["confidence"] == "high"
        assert result["evidence_score"] > 50


# ---------------------------------------------------------------------------
# group_used passthrough
# ---------------------------------------------------------------------------


class TestGroupUsed:
    def test_group_used_passed_through(self):
        trades = _make_trades(30, 20, win_r=1.2, loss_r=-1.0)
        result = calculate_edge(trades, group_used="EUR/USD:buy")
        assert result["group_used"] == "EUR/USD:buy"

    def test_group_used_none_by_default(self):
        trades = _make_trades(30, 20, win_r=1.2, loss_r=-1.0)
        result = calculate_edge(trades)
        assert result["group_used"] is None
