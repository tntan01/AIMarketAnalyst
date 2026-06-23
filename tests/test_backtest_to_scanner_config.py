"""Tests for backtest_to_scanner_config — recommend scanner configs from backtest."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.backtest_to_scanner_config import (
    _normalize_trades,
    _find_regime_side_combos,
    _find_optimal_min_score,
    _find_optimal_min_rr,
    _summarize,
    recommend_scanner_configs,
    summarize_recommendations,
    MIN_TRADES_FOR_RECOMMENDATION,
)


def _make_trades(*rows) -> list[dict]:
    """Build trade dicts from compact tuples:
    (symbol, side, regime, final_score, expected_rr, result, result_r)
    """
    trades = []
    for row in rows:
        trades.append({
            "symbol": row[0],
            "side": row[1],
            "market_regime": row[2],
            "final_score": row[3],
            "signal_score": row[3],
            "expected_effective_rr": row[4],
            "result": row[5],
            "result_r": row[6],
        })
    return trades


# ---------------------------------------------------------------------------
# Test 1: _summarize basic stats
# ---------------------------------------------------------------------------

def test_summarize():
    trades = _make_trades(
        ("EUR/USD", "buy", "range", 72, 2.5, "win", 1.5),
        ("EUR/USD", "buy", "range", 65, 1.8, "win", 2.0),
        ("EUR/USD", "buy", "range", 55, 1.5, "loss", -1.0),
        ("EUR/USD", "buy", "range", 70, 3.0, "loss", -1.0),
        ("EUR/USD", "buy", "range", 60, 2.0, "win", 0.5),
    )
    s = _summarize(trades)
    assert s["total_trades"] == 5
    assert s["wins"] == 3
    assert s["losses"] == 2
    assert s["win_rate"] == 60.0
    assert s["total_r"] == 2.0  # 1.5 + 2.0 - 1.0 - 1.0 + 0.5
    assert s["expectancy_r"] == 0.4  # 2.0 / 5

    print("  PASS: test_summarize")


# ---------------------------------------------------------------------------
# Test 2: Full recommendation for a clean case
# ---------------------------------------------------------------------------

def test_recommend_clean_case():
    trades = _make_trades(
        # EUR/USD range+buy: good edge
        ("EUR/USD", "buy", "range", 72, 2.5, "win", 1.5),
        ("EUR/USD", "buy", "range", 68, 2.0, "win", 2.0),
        ("EUR/USD", "buy", "range", 75, 3.0, "win", 1.0),
        ("EUR/USD", "buy", "range", 55, 1.5, "loss", -1.0),
        ("EUR/USD", "buy", "range", 70, 2.2, "win", 0.8),
        ("EUR/USD", "buy", "range", 65, 1.8, "loss", -1.0),
        ("EUR/USD", "buy", "range", 80, 2.8, "win", 2.1),
        ("EUR/USD", "buy", "range", 60, 1.3, "loss", -1.0),
        ("EUR/USD", "buy", "range", 72, 2.5, "win", 0.6),
        ("EUR/USD", "buy", "range", 58, 1.6, "win", 1.2),
        # EUR/USD trend_up+sell: bad edge
        ("EUR/USD", "sell", "trend_up", 55, 1.5, "loss", -1.0),
        ("EUR/USD", "sell", "trend_up", 50, 1.2, "loss", -1.0),
        ("EUR/USD", "sell", "trend_up", 60, 1.8, "loss", -1.0),
        ("EUR/USD", "sell", "trend_up", 45, 1.0, "win", 0.3),
        ("EUR/USD", "sell", "trend_up", 55, 1.3, "loss", -1.0),
        ("EUR/USD", "sell", "trend_up", 62, 1.5, "loss", -1.0),
        ("EUR/USD", "sell", "trend_up", 50, 1.1, "loss", -1.0),
        ("EUR/USD", "sell", "trend_up", 58, 1.4, "win", 0.5),
        ("EUR/USD", "sell", "trend_up", 48, 1.0, "loss", -1.0),
        ("EUR/USD", "sell", "trend_up", 55, 1.2, "loss", -1.0),
    )
    result = {"trades": trades, "summary": {}}
    recs = recommend_scanner_configs(result)

    assert "EUR/USD" in recs
    cfg = recs["EUR/USD"]
    assert cfg is not None, f"Expected a recommendation, got None"
    assert cfg["regime"] == "range"
    assert cfg["side"] == "buy"
    assert cfg["min_score"] >= 50
    assert cfg["min_rr"] >= 1.0
    assert "_evidence" in cfg
    assert "kỳ vọng" in cfg["_evidence"]

    print("  PASS: test_recommend_clean_case")


# ---------------------------------------------------------------------------
# Test 3: Not enough trades → None
# ---------------------------------------------------------------------------

def test_not_enough_trades():
    trades = _make_trades(
        ("EUR/USD", "buy", "range", 72, 2.5, "win", 1.5),
        ("EUR/USD", "buy", "range", 68, 2.0, "win", 2.0),
    )
    result = {"trades": trades, "summary": {}}
    recs = recommend_scanner_configs(result)
    assert recs["EUR/USD"] is None  # only 2 trades

    print("  PASS: test_not_enough_trades")


# ---------------------------------------------------------------------------
# Test 4: All negative → None
# ---------------------------------------------------------------------------

def test_all_negative():
    trades = _make_trades(
        ("GBP/USD", "buy", "trend_up", 60, 1.5, "loss", -1.0),
        ("GBP/USD", "buy", "trend_up", 55, 1.3, "loss", -1.0),
        ("GBP/USD", "buy", "trend_up", 65, 1.8, "loss", -1.0),
        ("GBP/USD", "buy", "trend_up", 50, 1.2, "loss", -1.0),
        ("GBP/USD", "buy", "trend_up", 62, 1.4, "loss", -1.0),
        ("GBP/USD", "buy", "trend_up", 58, 1.6, "loss", -1.0),
        ("GBP/USD", "buy", "trend_up", 70, 2.0, "loss", -1.0),
        ("GBP/USD", "buy", "trend_up", 55, 1.3, "loss", -1.0),
        ("GBP/USD", "buy", "trend_up", 60, 1.5, "loss", -1.0),
        ("GBP/USD", "buy", "trend_up", 52, 1.1, "loss", -1.0),
    )
    result = {"trades": trades, "summary": {}}
    recs = recommend_scanner_configs(result)
    assert recs["GBP/USD"] is None

    print("  PASS: test_all_negative")


# ---------------------------------------------------------------------------
# Test 5: Multiple regimes, picks best
# ---------------------------------------------------------------------------

def test_multiple_regimes_picks_best():
    trades = _make_trades(
        # range+buy: decent
        ("EUR/USD", "buy", "range", 70, 2.0, "win", 1.0),
        ("EUR/USD", "buy", "range", 65, 1.5, "win", 0.5),
        ("EUR/USD", "buy", "range", 60, 1.3, "loss", -1.0),
        ("EUR/USD", "buy", "range", 68, 1.8, "win", 1.2),
        ("EUR/USD", "buy", "range", 55, 1.2, "loss", -1.0),
        ("EUR/USD", "buy", "range", 72, 2.5, "win", 2.0),
        ("EUR/USD", "buy", "range", 58, 1.4, "loss", -1.0),
        ("EUR/USD", "buy", "range", 75, 2.2, "win", 1.8),
        ("EUR/USD", "buy", "range", 62, 1.6, "loss", -1.0),
        ("EUR/USD", "buy", "range", 70, 2.0, "win", 0.8),
        # trend_up+buy: better edge
        ("EUR/USD", "buy", "trend_up", 72, 2.0, "win", 2.5),
        ("EUR/USD", "buy", "trend_up", 68, 1.8, "win", 2.0),
        ("EUR/USD", "buy", "trend_up", 75, 2.2, "win", 1.5),
        ("EUR/USD", "buy", "trend_up", 55, 1.5, "loss", -1.0),
        ("EUR/USD", "buy", "trend_up", 80, 2.5, "win", 3.0),
        ("EUR/USD", "buy", "trend_up", 65, 1.6, "loss", -1.0),
        ("EUR/USD", "buy", "trend_up", 70, 2.0, "win", 1.8),
        ("EUR/USD", "buy", "trend_up", 60, 1.4, "win", 0.5),
        ("EUR/USD", "buy", "trend_up", 72, 2.1, "loss", -1.0),
        ("EUR/USD", "buy", "trend_up", 78, 2.3, "win", 1.2),
    )
    result = {"trades": trades, "summary": {}}
    recs = recommend_scanner_configs(result)

    cfg = recs["EUR/USD"]
    assert cfg is not None
    # Should pick trend_up (higher expectancy)
    assert cfg["regime"] == "trend_up"
    assert cfg["side"] == "buy"

    print("  PASS: test_multiple_regimes_picks_best")


# ---------------------------------------------------------------------------
# Test 6: _find_optimal_min_score
# ---------------------------------------------------------------------------

def test_find_optimal_min_score():
    trades = _make_trades(
        ("X", "buy", "range", 80, 2.0, "win", 2.0),
        ("X", "buy", "range", 75, 2.0, "win", 1.5),
        ("X", "buy", "range", 70, 2.0, "win", 1.0),
        ("X", "buy", "range", 55, 2.0, "loss", -1.0),
        ("X", "buy", "range", 50, 2.0, "loss", -1.0),
        ("X", "buy", "range", 65, 2.0, "win", 0.5),
        ("X", "buy", "range", 60, 2.0, "loss", -1.0),
        ("X", "buy", "range", 72, 2.0, "win", 1.2),
        ("X", "buy", "range", 52, 2.0, "loss", -1.0),
        ("X", "buy", "range", 78, 2.0, "win", 1.8),
    )
    threshold, evidence = _find_optimal_min_score(trades)
    assert threshold is not None
    assert threshold >= 50
    assert "kỳ vọng" in evidence

    print("  PASS: test_find_optimal_min_score")


# ---------------------------------------------------------------------------
# Test 7: summarize_recommendations output
# ---------------------------------------------------------------------------

def test_summarize_recommendations():
    recs = {
        "EUR/USD": {"regime": "range", "side": "buy", "min_score": 55, "min_rr": 1.5,
                     "_evidence": "15 lệnh, kỳ vọng +0.35R, PF 1.60, win rate 47.0%"},
        "GBP/USD": None,
        "USD/JPY": {"regime": "trend_up", "side": "sell", "min_score": 60, "min_rr": 1.3,
                     "_evidence": "12 lệnh, kỳ vọng +0.25R, PF 1.40, win rate 50.0%"},
    }
    text = summarize_recommendations(recs)
    assert "EUR/USD" in text
    assert "range" in text
    assert "GBP/USD" in text
    assert "không đủ dữ liệu" in text
    assert "USD/JPY" in text
    assert "trend_up" in text

    print("  PASS: test_summarize_recommendations")


# ---------------------------------------------------------------------------
# Test 8: Empty trades → empty dict
# ---------------------------------------------------------------------------

def test_empty_trades():
    result = {"trades": [], "summary": {}}
    recs = recommend_scanner_configs(result)
    assert recs == {}

    print("  PASS: test_empty_trades")


# ---------------------------------------------------------------------------
# Test 9: _find_regime_side_combos
# ---------------------------------------------------------------------------

def test_find_regime_side_combos():
    trades = _make_trades(
        ("A", "buy", "range", 70, 2.0, "win", 1.0),
        ("A", "sell", "trend_up", 60, 1.5, "loss", -1.0),
        ("A", "buy", "trend_up", 65, 1.8, "win", 1.2),
    )
    combos = _find_regime_side_combos(trades)
    assert ("range", "buy") in combos
    assert ("trend_up", "buy") in combos
    assert ("trend_up", "sell") in combos
    assert len(combos) == 3

    print("  PASS: test_find_regime_side_combos")


# ---------------------------------------------------------------------------
# Test 10: _find_optimal_min_rr
# ---------------------------------------------------------------------------

def test_find_optimal_min_rr():
    trades = _make_trades(
        ("X", "buy", "range", 70, 3.0, "win", 2.0),
        ("X", "buy", "range", 65, 2.5, "win", 1.5),
        ("X", "buy", "range", 60, 2.0, "win", 1.0),
        ("X", "buy", "range", 55, 1.8, "loss", -1.0),
        ("X", "buy", "range", 50, 1.5, "loss", -1.0),
        ("X", "buy", "range", 68, 2.2, "win", 0.8),
        ("X", "buy", "range", 58, 1.3, "loss", -1.0),
        ("X", "buy", "range", 72, 2.8, "win", 1.6),
        ("X", "buy", "range", 62, 1.6, "win", 0.5),
        ("X", "buy", "range", 70, 2.0, "loss", -1.0),
    )
    threshold, evidence = _find_optimal_min_rr(trades)
    assert threshold is not None
    assert threshold >= 1.0

    print("  PASS: test_find_optimal_min_rr")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_all_tests():
    tests = [
        ("Summarize stats", test_summarize),
        ("Recommend clean case", test_recommend_clean_case),
        ("Not enough trades", test_not_enough_trades),
        ("All negative", test_all_negative),
        ("Multiple regimes picks best", test_multiple_regimes_picks_best),
        ("Find optimal min_score", test_find_optimal_min_score),
        ("Summarize recommendations", test_summarize_recommendations),
        ("Empty trades", test_empty_trades),
        ("Find regime side combos", test_find_regime_side_combos),
        ("Find optimal min_rr", test_find_optimal_min_rr),
    ]

    print("=" * 60)
    print("Backtest -> Scanner Config Tests")
    print("=" * 60)

    passed = 0
    failed = 0
    for name, test_fn in tests:
        try:
            print(f"\n[{name}]")
            test_fn()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  FAIL: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'=' * 60}")
    return failed == 0


if __name__ == "__main__":
    ok = run_all_tests()
    sys.exit(0 if ok else 1)
