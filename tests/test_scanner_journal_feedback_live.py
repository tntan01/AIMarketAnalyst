"""Live Scanner journal-feedback attachment (F3, display-only).

``_attach_journal_feedback_to_row`` computes real R-based feedback for the row's
selected side and overrides the adapter's neutral ``journal_sample_size`` /
``journal_expectancy_r`` / ``journal_feedback`` keys. It must never mutate gate,
decision or block codes (V4 target-only discipline).
"""

from __future__ import annotations

from controllers.scanner_controller import _attach_journal_feedback_to_row


def _base_row(selected_side="buy"):
    return {
        "symbol": "EUR/USD",
        "selected_side": selected_side,
        "market_regime": "trending_up",
        "candidate_status": "READY_NOW",
        "gate_codes": [],
        "block_codes": [],
        "decision_cap": None,
        "journal_sample_size": 0,
        "journal_expectancy_r": None,
        "journal_feedback": {},
    }


def _closed_trade(result_r, direction="buy", symbol="EUR/USD"):
    return {
        "symbol": symbol,
        "direction": direction,
        "selected_scenario": direction,
        "result_r": result_r,
    }


def test_attach_journal_feedback_populates_real_keys():
    row = _base_row("buy")
    trades = [
        _closed_trade(0.5),
        _closed_trade(0.5),
        _closed_trade(-1.0),  # sell-side trade must NOT match buy row
        _closed_trade(0.5, direction="buy", symbol="GBP/USD"),  # other symbol ignored
    ]
    result = _attach_journal_feedback_to_row(row, trades, "EUR/USD")

    assert result["journal_sample_size"] == 3
    assert result["journal_expectancy_r"] is not None
    assert isinstance(result["journal_feedback"], dict)
    assert result["journal_feedback"]["sample_size"] == 3
    reasons = result["journal_feedback"].get("reasons", [])
    assert reasons, "real feedback should carry at least a reason string"


def test_attach_journal_feedback_is_display_only_not_gating():
    row = _base_row("buy")
    trades = [_closed_trade(0.5) for _ in range(3)]
    result = _attach_journal_feedback_to_row(row, trades, "EUR/USD")

    # Informational only: gate/decision/block surfaces must be untouched.
    assert result["candidate_status"] == "READY_NOW"
    assert result["gate_codes"] == []
    assert result["block_codes"] == []
    assert result["decision_cap"] is None


def test_attach_journal_feedback_no_selected_side_keeps_neutral():
    row = _base_row("neutral")
    result = _attach_journal_feedback_to_row(row, [_closed_trade(0.5)], "EUR/USD")
    assert result["journal_sample_size"] == 0
    assert result["journal_expectancy_r"] is None
    assert result["journal_feedback"] == {}


def test_attach_journal_feedback_no_matching_trades_keeps_sample_zero():
    row = _base_row("buy")
    # Only sell-side / other-symbol trades -> no buy/EUR/USD match.
    trades = [_closed_trade(0.5, direction="sell"), _closed_trade(0.5, symbol="GBP/USD")]
    result = _attach_journal_feedback_to_row(row, trades, "EUR/USD")
    assert result["journal_sample_size"] == 0
    assert result["journal_expectancy_r"] is None