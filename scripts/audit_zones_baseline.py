"""Audit supply/demand zones from detect_supply_demand_zones().

Generates test candles with consolidation+impulse patterns and saves zone
baseline for before/after comparison.

Usage: python scripts/audit_zones_baseline.py
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

from core.market_models import Candle
from core.smc_context import detect_supply_demand_zones, enrich_zones

random.seed(123)


def generate_test_candles(cycles: int = 10, future_bars: int = 30) -> list[Candle]:
    """Generate realistic H4 candles with consolidation + impulse patterns."""
    candles = []
    price = 1.1000
    base_time = datetime(2026, 1, 1, 0, 0)

    for _ in range(cycles):
        # Random walk warmup
        for _ in range(8):
            o = price
            c = o + random.uniform(-0.0005, 0.0005)
            h = max(o, c) + random.uniform(0, 0.0003)
            l = min(o, c) - random.uniform(0, 0.0003)
            candles.append(Candle(open=o, high=h, low=l, close=c, time=base_time, volume=1000))
            price = c
            base_time += timedelta(hours=4)

        # Consolidation base (3/5/7 bars)
        base_bars = random.choice([3, 5, 7])
        for _ in range(base_bars):
            o = price
            c = o + random.uniform(-0.0002, 0.0002)
            h = max(o, c) + random.uniform(0, 0.0001)
            l = min(o, c) - random.uniform(0, 0.0001)
            candles.append(Candle(open=o, high=h, low=l, close=c, time=base_time, volume=1000))
            price = c
            base_time += timedelta(hours=4)

        # Impulse candle
        is_bullish = random.choice([True, False])
        impulse_size = random.uniform(0.0020, 0.0040)
        base_candles = candles[-base_bars:]
        if is_bullish:
            bl = min(c.low for c in base_candles)
            o = bl + random.uniform(0, 0.0002)
            c = o + impulse_size
            h = c + random.uniform(0, 0.0005)
            l = o - random.uniform(0, 0.0003)
        else:
            bh = max(c.high for c in base_candles)
            o = bh - random.uniform(0, 0.0002)
            c = o - impulse_size
            h = o + random.uniform(0, 0.0003)
            l = c - random.uniform(0, 0.0005)
        candles.append(Candle(open=o, high=h, low=l, close=c, time=base_time, volume=2000))
        price = c
        base_time += timedelta(hours=4)

    # Future bars for test_count/broken detection
    for _ in range(future_bars):
        o = price
        c = o + random.uniform(-0.0005, 0.0005)
        h = max(o, c) + random.uniform(0, 0.0003)
        l = min(o, c) - random.uniform(0, 0.0003)
        candles.append(Candle(open=o, high=h, low=l, close=c, time=base_time, volume=1000))
        price = c
        base_time += timedelta(hours=4)

    return candles


def main():
    candles = generate_test_candles(cycles=10, future_bars=30)
    print(f"Candles: {len(candles)}")

    price_range = max(c.high for c in candles) - min(c.low for c in candles)
    mid = (max(c.high for c in candles) + min(c.low for c in candles)) / 2
    pd_range = {
        "low": mid - price_range * 0.3,
        "high": mid + price_range * 0.3,
        "midpoint": mid,
        "status": "ok",
    }
    sweeps = {"swept_lows": [], "swept_highs": []}

    demand, supply = detect_supply_demand_zones(candles)
    all_zones = demand + supply
    enriched = enrich_zones(all_zones, candles, "", sweeps, pd_range, tf_minutes=240)

    score_dist = {"0-39": 0, "40-54": 0, "55-74": 0, "75-100": 0}
    for z in enriched:
        s = z.get("zone_score", 0)
        if s < 40:
            score_dist["0-39"] += 1
        elif s < 55:
            score_dist["40-54"] += 1
        elif s < 75:
            score_dist["55-74"] += 1
        else:
            score_dist["75-100"] += 1

    zones_export = []
    for z in enriched:
        zones_export.append({
            "type": z.get("type"),
            "low": round(z.get("low", 0), 5),
            "high": round(z.get("high", 0), 5),
            "index": z.get("index"),
            "zone_score": z.get("zone_score"),
            "strength": z.get("strength"),
            "freshness_bars": z.get("freshness_bars"),
            "stale": z.get("stale", False),
            "test_count": z.get("test_count"),
            "broken": z.get("broken"),
            "mitigated": z.get("mitigated"),
            "consolidation_bars": z.get("consolidation_bars"),
        })

    result = {
        "candle_count": len(candles),
        "demand_count": len(demand),
        "supply_count": len(supply),
        "total_zones": len(enriched),
        "zone_score_distribution": score_dist,
        "zones": zones_export,
    }

    out_path = Path("data/temp/baseline_zones.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Demand: {len(demand)}, Supply: {len(supply)}, Total: {len(enriched)}")
    print(f"Score dist: {score_dist}")
    print(f"\nZones:")
    for z in zones_export:
        print(f"  {z['type']} low={z['low']} high={z['high']} "
              f"score={z['zone_score']} str={z['strength']} "
              f"test={z['test_count']} broken={z['broken']} bars={z['consolidation_bars']}")
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
