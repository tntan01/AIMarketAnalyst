"""Phase 15.11 — realistic scanner ranking integration test."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.scanner import sort_scanner_rows, scanner_summary, ai_targets
from core.scanner_ranking_engine import (
    READY_NOW, WAITING_CONFIRMATION, WATCH_ZONE, BLOCKED,
    enrich_scanner_row_with_ranking,
)


def _build_row(symbol, final_score, decision, entry_status, price_vs_zone,
               risk_reward, spread_status, high_impact_30m, news_3h,
               trade_permission="allowed"):
    row = {
        "symbol": symbol,
        "final_score": final_score,
        "best_score": final_score,
        "decision": decision,
        "trade_permission": {"status": trade_permission},
        "entry_status": entry_status,
        "price_vs_zone": price_vs_zone,
        "risk_reward": risk_reward,
        "spread_status": spread_status,
        "high_impact_event_within_30m": high_impact_30m,
        "news_in_3h": news_3h,
    }
    return enrich_scanner_row_with_ranking(row)


def test_realistic_dataset():
    rows = [
        _build_row("EUR/USD", 84, "READY_TO_TRADE",       "confirmed_entry",      "in_zone",   "1:2.0", "normal",   False, False),
        _build_row("XAU/USD", 80, "READY_TO_TRADE",       "confirmed_entry",      "in_zone",   "1:1.8", "caution",  False, False),
        _build_row("GBP/JPY", 88, "WAITING_CONFIRMATION", "waiting_confirmation", "near_zone", "1:2.5", "normal",   False, False),
        _build_row("USD/JPY", 76, "WATCH_ONLY",           "watch_zone",           "near_zone", "1:1.5", "normal",   False, False),
        _build_row("AUD/USD", 95, "TRADE_BLOCKED",        "confirmed_entry",      "far",       "1:3.0", "abnormal", True,  True),
        _build_row("NZD/USD", 55, "STAND_ASIDE",          "watch_zone",           "far",       "1:1.2", "normal",   False, False),
    ]

    # ---- Sort ----
    sorted_rows = sort_scanner_rows(rows)

    # Ready group first
    assert sorted_rows[0]["symbol"] == "EUR/USD"  # higher opportunity than XAU/USD
    assert sorted_rows[1]["symbol"] == "XAU/USD"
    # Waiting next
    assert sorted_rows[2]["symbol"] == "GBP/JPY"
    # Watch after waiting
    assert sorted_rows[3]["symbol"] == "USD/JPY"
    assert sorted_rows[4]["symbol"] == "NZD/USD"
    # Blocked last despite highest final_score=95
    assert sorted_rows[5]["symbol"] == "AUD/USD"

    # rank assigned
    for i, row in enumerate(sorted_rows, start=1):
        assert row["rank"] == i

    # ---- Summary ----
    summary = scanner_summary(sorted_rows)
    assert summary["ready_now_count"] == 2
    assert summary["waiting_confirmation_count"] == 1
    assert summary["watch_zone_count"] == 2
    assert summary["blocked_count"] == 1
    assert summary["top_opportunity_score"] is not None
    assert summary["average_opportunity_score"] > 0

    # ---- AI targets ----
    targets = ai_targets(sorted_rows, limit=3)
    assert len(targets) <= 3
    # Blocked not included
    target_symbols = [t["symbol"] for t in targets]
    assert "AUD/USD" not in target_symbols
    # Ready group prioritized
    assert target_symbols[0] == "EUR/USD"


def test_blocked_never_in_ai_targets():
    rows = [
        _build_row("BLK1", 95, "TRADE_BLOCKED", "confirmed_entry", "in_zone", "1:3.0", "abnormal", True, True),
        _build_row("BLK2", 88, "TRADE_BLOCKED", "confirmed_entry", "in_zone", "1:2.0", "abnormal", True, False),
        _build_row("READY", 70, "READY_TO_TRADE", "confirmed_entry", "in_zone", "1:1.5", "normal", False, False),
    ]
    targets = ai_targets(rows, limit=5)
    target_symbols = [t["symbol"] for t in targets]
    assert "BLK1" not in target_symbols
    assert "BLK2" not in target_symbols
    assert "READY" in target_symbols
