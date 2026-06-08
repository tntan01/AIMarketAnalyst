"""Verify that rows without price_vs_zone but with price_in_entry_zone
boolean receive the correct proximity bonus in calculate_opportunity_score
and enrich_scanner_row_with_ranking.

After the normalize_price_vs_zone bool fix:
  - True  → "in_zone"  → +8 proximity bonus
  - False → "far"      → 0 proximity bonus

Run:  python scripts/check_opportunity_proximity_boolean.py
Requires: nothing — no MT5, no network, no API key.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.scanner_ranking_engine import (
    calculate_opportunity_score,
    enrich_scanner_row_with_ranking,
)


# ---------------------------------------------------------------------------
# Test rows — no price_vs_zone key, only price_in_entry_zone boolean
# ---------------------------------------------------------------------------

_COMMON = {
    "symbol": "EUR/USD",
    "final_score": 80,
    "decision": "READY_TO_TRADE",
    "entry_status": "confirmed_entry",
    "risk_reward": "1:2.0",
    "spread_status": "normal",
    "news_in_3h": False,
    "high_impact_event_within_30m": False,
}

row_true = dict(_COMMON, price_in_entry_zone=True)
row_false = dict(_COMMON, price_in_entry_zone=False)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    errors: list[str] = []

    def check(cond, msg):
        if not cond:
            errors.append(msg)

    # ---- Direct calculate_opportunity_score ----
    direct_true = calculate_opportunity_score(row_true)
    direct_false = calculate_opportunity_score(row_false)

    print("=== calculate_opportunity_score (True) ===")
    print(f"  proximity_bonus = {direct_true['score_breakdown']['proximity_bonus']}  (expect 8)")
    print(f"  opportunity_score = {direct_true['opportunity_score']}")
    print(f"  reason_codes = {direct_true['reason_codes']}")

    print("\n=== calculate_opportunity_score (False) ===")
    print(f"  proximity_bonus = {direct_false['score_breakdown']['proximity_bonus']}  (expect 0)")
    print(f"  opportunity_score = {direct_false['opportunity_score']}")
    print(f"  reason_codes = {direct_false['reason_codes']}")

    check(direct_true["score_breakdown"]["proximity_bonus"] == 8,
          f"True proximity_bonus expected 8, got {direct_true['score_breakdown']['proximity_bonus']}")
    check("SCANNER_PROXIMITY_IN_ZONE" in direct_true["reason_codes"],
          f"True missing SCANNER_PROXIMITY_IN_ZONE: {direct_true['reason_codes']}")

    check(direct_false["score_breakdown"]["proximity_bonus"] == 0,
          f"False proximity_bonus expected 0, got {direct_false['score_breakdown']['proximity_bonus']}")
    check("SCANNER_PROXIMITY_FAR" in direct_false["reason_codes"],
          f"False missing SCANNER_PROXIMITY_FAR: {direct_false['reason_codes']}")

    check(direct_true["opportunity_score"] > direct_false["opportunity_score"],
          f"True opp_score ({direct_true['opportunity_score']}) must be > "
          f"False opp_score ({direct_false['opportunity_score']})")

    # ---- enrich_scanner_row_with_ranking ----
    enriched_true = enrich_scanner_row_with_ranking(row_true)
    enriched_false = enrich_scanner_row_with_ranking(row_false)

    print("\n=== enrich_scanner_row_with_ranking (True) ===")
    print(f"  proximity_bonus = {enriched_true['ranking_score_breakdown']['proximity_bonus']}  (expect 8)")
    print(f"  ranking_reason_codes = {enriched_true['ranking_reason_codes']}")

    print("\n=== enrich_scanner_row_with_ranking (False) ===")
    print(f"  proximity_bonus = {enriched_false['ranking_score_breakdown']['proximity_bonus']}  (expect 0)")
    print(f"  ranking_reason_codes = {enriched_false['ranking_reason_codes']}")

    check(enriched_true["ranking_score_breakdown"]["proximity_bonus"] == 8,
          f"Enrich True proximity_bonus expected 8, got {enriched_true['ranking_score_breakdown']['proximity_bonus']}")
    check("SCANNER_PROXIMITY_IN_ZONE" in enriched_true["ranking_reason_codes"],
          f"Enrich True missing SCANNER_PROXIMITY_IN_ZONE: {enriched_true['ranking_reason_codes']}")

    check(enriched_false["ranking_score_breakdown"]["proximity_bonus"] == 0,
          f"Enrich False proximity_bonus expected 0, got {enriched_false['ranking_score_breakdown']['proximity_bonus']}")
    check("SCANNER_PROXIMITY_FAR" in enriched_false["ranking_reason_codes"],
          f"Enrich False missing SCANNER_PROXIMITY_FAR: {enriched_false['ranking_reason_codes']}")

    if errors:
        print(f"\nFAILED — {len(errors)} assertion(s):")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("\n[PASS] ALL ASSERTIONS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
