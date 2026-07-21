"""Backfill entry_zone_score/entry_zone_source/sub_zone cho journal entries cu
bang cach tinh lai tu raw SMC data da luu trong analysis_json.

CHI chay cho entries co analysis_json chua key "smc" VA hien tai entry_zone_score
dang NULL (khong ghi de entry da co du lieu moi).

Danh dau entry_zone_source = "backfilled_recomputed" de phan biet voi du lieu
ghi truc tiep luc phan tich.

Usage:
    python scripts/backfill_zone_metadata.py          # dry-run
    python scripts/backfill_zone_metadata.py --apply  # actually update DB
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

from config.paths import journal_db_path


def _safe_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _find_matching_zone(
    entry_zone_raw: str | None,
    side: str,
    smc: dict,
) -> dict | None:
    """Tim zone SMC trong smc context co low/high khop voi entry_zone da luu."""
    if not entry_zone_raw:
        return None
    try:
        zone_arr = json.loads(entry_zone_raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(zone_arr, list) or len(zone_arr) < 2:
        return None
    target_low = float(zone_arr[0])
    target_high = float(zone_arr[1])
    tolerance = max(1e-6, (target_high - target_low) * 0.1)

    def _match(candidate: dict) -> bool:
        low = candidate.get("low")
        high = candidate.get("high")
        if low is None or high is None:
            return False
        return abs(float(low) - target_low) < tolerance and abs(float(high) - target_high) < tolerance

    zone_keys = ["demand_zones", "order_blocks", "fvg"] if side == "buy" else ["supply_zones", "order_blocks", "fvg"]

    for tf_key in ("H4", "H1"):
        tf = smc.get(tf_key, {}) if isinstance(smc, dict) else {}
        if not isinstance(tf, dict):
            continue
        for key in zone_keys:
            zones = tf.get(key, [])
            if not isinstance(zones, list):
                continue
            for zone in zones:
                if not isinstance(zone, dict):
                    continue
                if _match(zone):
                    return zone

    return None


def backfill(*, apply: bool = False) -> dict:
    """Chay backfill, tra ve tong ket."""
    db_path = journal_db_path()
    if not db_path.exists():
        print(f"DB not found: {db_path}")
        return {"success": 0, "skipped": 0, "errors": []}

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT id, symbol, selected_scenario, entry_zone, analysis_json "
        "FROM journal_entries "
        "WHERE entry_zone_score IS NULL "
        "AND analysis_json IS NOT NULL AND analysis_json != '' "
        "AND trade_status = 'closed'"
    ).fetchall()

    print(f"Found {len(rows)} closed entries with NULL entry_zone_score and analysis_json")

    from core.smc_context import zone_quality_score

    success = 0
    skipped = 0
    skip_reasons: dict[str, int] = {}

    for row in rows:
        entry_id = row["id"]
        symbol = row["symbol"]
        side = str(row["selected_scenario"] or "").strip().lower()
        entry_zone_raw = row["entry_zone"]

        if side not in ("buy", "sell"):
            skip_reasons["no_side"] = skip_reasons.get("no_side", 0) + 1
            skipped += 1
            continue

        try:
            analysis = json.loads(row["analysis_json"])
        except (json.JSONDecodeError, TypeError):
            skip_reasons["bad_json"] = skip_reasons.get("bad_json", 0) + 1
            skipped += 1
            continue

        smc = analysis.get("smc")
        if not isinstance(smc, dict):
            skip_reasons["no_smc"] = skip_reasons.get("no_smc", 0) + 1
            skipped += 1
            continue

        # Tim scenario khớp best_side de lay sub_zone
        scenarios = analysis.get("scenarios")
        best_side = analysis.get("decision_summary", {}).get("best_side") if isinstance(analysis.get("decision_summary"), dict) else None
        best_scenario = None
        if isinstance(scenarios, list):
            for s in scenarios:
                if isinstance(s, dict):
                    s_side = s.get("side") or s.get("type")
                    if best_side and s_side == best_side:
                        best_scenario = s
                        break
            if best_scenario is None and scenarios:
                best_scenario = scenarios[0] if isinstance(scenarios[0], dict) else None

        sub_zone_val = None
        if isinstance(best_scenario, dict):
            sub_zone_val = str(best_scenario.get("sub_zone") or "") or None

        zone = _find_matching_zone(entry_zone_raw, side, smc)
        if zone is None:
            skip_reasons["zone_not_found"] = skip_reasons.get("zone_not_found", 0) + 1
            skipped += 1
            continue

        zone_score = zone_quality_score(zone, side)

        if apply:
            conn.execute(
                "UPDATE journal_entries SET entry_zone_score=?, entry_zone_source='backfilled_recomputed', sub_zone=? WHERE id=?",
                (zone_score, sub_zone_val, entry_id),
            )
        else:
            print(f"  [DRY-RUN] id={entry_id} {symbol} {side}: zone_score={zone_score}, sub_zone={sub_zone_val}")

        success += 1

    if apply:
        conn.commit()
        print(f"\nApplied: {success} entries updated")

    conn.close()

    print(f"\nSummary: success={success}, skipped={skipped}")
    if skip_reasons:
        for reason, count in sorted(skip_reasons.items()):
            print(f"  {reason}: {count}")

    return {"success": success, "skipped": skipped, "errors": list(skip_reasons.keys())}


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    backfill(apply=apply)
