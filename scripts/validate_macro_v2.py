#!/usr/bin/env python3
r"""Phase 15G.7.1 — Forward outcome validation for Macro V2 (hardened).

Anti-lookahead by epoch timestamp.  MFE/MAE per horizon.
Schema versioned.  No hardcoded account/symbol data.

Usage::

    python scripts/validate_macro_v2.py record --output data/shadow_records.jsonl
    python scripts/validate_macro_v2.py label --input data/shadow_records.jsonl
    python scripts/validate_macro_v2.py report --input data/shadow_records.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_path():
    r = str(_repo_root())
    if r not in sys.path:
        sys.path.insert(0, r)


def _iso_to_epoch(iso_str: str) -> float:
    """Parse ISO timestamp to epoch seconds.  Returns 0 on failure."""
    try:
        s = str(iso_str).replace("Z", "+00:00")
        return datetime.fromisoformat(s).timestamp()
    except (ValueError, TypeError):
        return 0.0


def _epoch_now() -> float:
    return datetime.now(timezone.utc).timestamp()


def _classify_direction(buy: int, sell: int, gap: int = 5) -> str:
    if buy > sell + gap:
        return "buy"
    if sell > buy + gap:
        return "sell"
    return "neutral"


def _compute_config(mult: float, deadband: int, edge: int) -> tuple[int, int]:
    if abs(edge) <= deadband:
        return 15, 15
    raw = max(0.0, min(30.0, 15.0 + edge * mult))
    b = int(round(raw))
    return b, 30 - b


# ---------------------------------------------------------------------------
# Shadow record (schema v1)
# ---------------------------------------------------------------------------

def _new_record(*, symbol: str, session_id: str, recorded_at: str,
                recorded_epoch: float, price: float, regime: str,
                broker_symbol: str,
                v1_buy: int, v1_sell: int,
                pair_edge: int, v2_confidence: float,
                config_a_buy: int, config_a_sell: int,
                config_b_buy: int, config_b_sell: int) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "symbol": symbol,
        "broker_symbol": broker_symbol,
        "session_id": session_id,
        "recorded_at": recorded_at,
        "recorded_epoch": recorded_epoch,
        "price": price,
        "regime": regime,
        "v1_buy": v1_buy,
        "v1_sell": v1_sell,
        "pair_edge": pair_edge,
        "v2_confidence": v2_confidence,
        "config_a_buy": config_a_buy,
        "config_a_sell": config_a_sell,
        "config_b_buy": config_b_buy,
        "config_b_sell": config_b_sell,
        "label_4h": None,
        "label_24h": None,
        "return_4h_pct": None,
        "return_24h_pct": None,
        "mfe_4h_pct": None,
        "mae_4h_pct": None,
        "mfe_24h_pct": None,
        "mae_24h_pct": None,
        "labeled_at_epoch": None,
    }


# ---------------------------------------------------------------------------
# Record
# ---------------------------------------------------------------------------


def record_shadow(output_path: str) -> int:
    _ensure_path()
    import MetaTrader5 as mt5
    mt5.initialize()

    from services.mt5_service import MT5Service
    from services.settings_service import SettingsService
    from services.news_service import NewsService
    from controllers.scanner_controller import ScannerController
    from core.scanner import ScannerRequest

    NewsService._interest_rates = None
    news_svc = NewsService()
    news_svc._tier_scores_cache = {}
    news_svc._stance_cache = {}
    mt5_svc = MT5Service()
    ctrl = ScannerController(SettingsService(), mt5=mt5_svc, news_service=news_svc)

    symbols_raw = mt5.symbols_get()
    available = mt5_svc.available_symbols(market_watch_only=True)
    seen = set()
    symbols = []
    for s in symbols_raw:
        n = s.name
        clean = n[:-1] if n.endswith("c") else n
        if clean in seen or any(x in clean for x in ("BTC", "ETH", "XAU", "XAG")):
            continue
        seen.add(clean)
        symbols.append(clean)

    request = ScannerRequest(
        symbols=symbols, account_balance=67.53, risk_percent=1.0,
        timezone_name="Asia/Ho_Chi_Minh", auto_trade_enabled=False,
    )
    result = ctrl.run_market_scan(request=request)

    now_epoch = _epoch_now()
    session_id = datetime.fromtimestamp(now_epoch, tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
    records = []
    seen_sym = set()

    for r in result.get("rows", []):
        sym = str(r.get("symbol", ""))
        if sym in seen_sym:
            continue
        ar = r.get("analysis_result")
        if not isinstance(ar, dict):
            continue
        dc = ar.get("macro", {}).get("driver_context", {})
        if not isinstance(dc, dict):
            continue
        v1 = dc.get("macro_alignment_scores")
        v2 = dc.get("macro_v2")
        if not isinstance(v1, dict) or not isinstance(v2, dict):
            continue
        edge = v2.get("pair_edge")
        if not isinstance(edge, (int, float)):
            continue

        tech = ar.get("technical", {})
        price = float(tech.get("price", 0) or 0)
        regime = str(ar.get("market_regime", {}).get("primary", "unknown"))

        # Resolve broker symbol
        bs = str(r.get("broker_symbol", ""))
        if not bs:
            bs = mt5_svc.resolve_symbol(sym, available)

        a_buy, a_sell = _compute_config(1.0, 2, int(edge))
        b_buy, b_sell = _compute_config(1.0, 3, int(edge))

        rec = _new_record(
            symbol=sym, session_id=session_id,
            recorded_at=result.get("timestamp", datetime.now(timezone.utc).isoformat()),
            recorded_epoch=now_epoch, price=price, regime=regime,
            broker_symbol=bs,
            v1_buy=int(v1.get("buy", 0)), v1_sell=int(v1.get("sell", 0)),
            pair_edge=int(edge), v2_confidence=float(v2.get("confidence", 0)),
            config_a_buy=a_buy, config_a_sell=a_sell,
            config_b_buy=b_buy, config_b_sell=b_sell,
        )
        records.append(rec)
        seen_sym.add(sym)

    with open(output_path, "a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, default=str) + "\n")

    mt5.shutdown()
    print(f"[record] {len(records)} records -> {output_path} (session {session_id})")
    return len(records)


# ---------------------------------------------------------------------------
# Label
# ---------------------------------------------------------------------------

def _fetch_candles_range(broker_symbol: str, start_epoch: float,
                          horizon_hours: float) -> list[dict]:
    """Fetch MT5 H1 candles from start_epoch to start_epoch+horizon_hours."""
    import MetaTrader5 as mt5

    if not mt5.initialize():
        return []
    mt5.symbol_select(broker_symbol, True)

    end_epoch = start_epoch + horizon_hours * 3600 + 3600  # +1h margin
    start_dt = datetime.fromtimestamp(start_epoch, tz=timezone.utc)
    end_dt = datetime.fromtimestamp(end_epoch, tz=timezone.utc)

    candles = mt5.copy_rates_range(broker_symbol, mt5.TIMEFRAME_H1, start_dt, end_dt)
    mt5.shutdown()

    if candles is None or len(candles) == 0:
        return []

    result = []
    for c in candles:
        ct = float(c.time)
        # Anti-lookahead: candle must OPEN after recorded_at
        if ct <= start_epoch:
            continue
        result.append({
            "epoch": ct,
            "open": float(c.open), "high": float(c.high),
            "low": float(c.low), "close": float(c.close),
        })
    return result


def _compute_mfe_mae(candles: list[dict], entry_px: float,
                     direction: str = "buy") -> tuple[float, float]:
    """MFE = max favorable excursion, MAE = max adverse excursion.
    BUY: favorable = (high - entry) / entry, adverse = (entry - low) / entry.
    SELL: favorable = (entry - low) / entry, adverse = (high - entry) / entry.
    Both returned as positive percentages."""
    if not candles or entry_px <= 0:
        return 0.0, 0.0
    mfe = 0.0
    mae = 0.0
    for c in candles:
        if direction == "sell":
            fav = (entry_px - c["low"]) / entry_px * 100
            adv = (c["high"] - entry_px) / entry_px * 100
        else:
            fav = (c["high"] - entry_px) / entry_px * 100
            adv = (entry_px - c["low"]) / entry_px * 100
        if fav > mfe:
            mfe = fav
        if adv > mae:
            mae = adv
    return round(max(0, mfe), 4), round(max(0, mae), 4)


def _horizon_complete(candles: list[dict], start_epoch: float,
                      horizon_seconds: float) -> bool:
    """True when the LAST candle closes at or after start + horizon.
    A few partial candles early in the window do NOT trigger labeling."""
    if not candles:
        return False
    target = start_epoch + horizon_seconds
    last = candles[-1]
    # Candle epoch is the OPEN time in MT5; close is epoch + 3600 for H1.
    # We consider horizon complete when last candle OPEN >= target - 3600
    # (meaning the close of that candle covers the target).
    return float(last.get("epoch", 0)) >= target - 3600


def _session_dedupe(records: list[dict]) -> list[dict]:
    """Keep only 1 record per symbol per session (latest epoch wins)."""
    seen: dict[tuple[str, str], dict] = {}
    for r in records:
        key = (str(r.get("symbol", "")), str(r.get("session_id", "")))
        if key not in seen or float(r.get("recorded_epoch", 0)) > float(seen[key].get("recorded_epoch", 0)):
            seen[key] = r
    return list(seen.values())


def _label_outcome(candles: list[dict], entry_px: float) -> tuple[str | None, float | None]:
    """Label: up/down/flat based on last candle close vs entry."""
    if not candles or entry_px <= 0:
        return None, None
    last_close = candles[-1]["close"]
    ret = (last_close - entry_px) / entry_px * 100
    ret = round(ret, 4)
    if ret > 0.1:
        return "up", ret
    if ret < -0.1:
        return "down", ret
    return "flat", ret


def label_outcomes(input_path: str) -> int:
    """Read records, label with MT5 candles if enough time has passed."""
    now_epoch = _epoch_now()
    records = []
    with open(input_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))

    labeled_count = 0
    for rec in records:
        ver = rec.get("schema_version", 0)
        if ver < 1:
            continue  # skip old-format records

        rec_epoch = float(rec.get("recorded_epoch", 0))
        entry_px = float(rec.get("price", 0))
        broker_sym = str(rec.get("broker_symbol", ""))
        if rec_epoch <= 0 or entry_px <= 0 or not broker_sym:
            continue

        elapsed_h = (now_epoch - rec_epoch) / 3600.0
        newly_labeled = False

        # 4H horizon
        if elapsed_h >= 4.0 and rec.get("label_4h") is None:
            candles_4h = _fetch_candles_range(broker_sym, rec_epoch, 4.0)
            if len(candles_4h) >= 1:
                label, ret = _label_outcome(candles_4h, entry_px)
                mfe, mae = _compute_mfe_mae(candles_4h, entry_px)
                rec["label_4h"] = label
                rec["return_4h_pct"] = ret
                rec["mfe_4h_pct"] = mfe
                rec["mae_4h_pct"] = mae
                newly_labeled = True

        # 24H horizon
        if elapsed_h >= 24.0 and rec.get("label_24h") is None:
            candles_24h = _fetch_candles_range(broker_sym, rec_epoch, 24.0)
            if len(candles_24h) >= 4:
                label, ret = _label_outcome(candles_24h, entry_px)
                mfe, mae = _compute_mfe_mae(candles_24h, entry_px)
                rec["label_24h"] = label
                rec["return_24h_pct"] = ret
                rec["mfe_24h_pct"] = mfe
                rec["mae_24h_pct"] = mae
                newly_labeled = True

        if newly_labeled:
            rec["labeled_at_epoch"] = now_epoch
            labeled_count += 1

    with open(input_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, default=str) + "\n")

    print(f"[label] {labeled_count} newly labeled records in {input_path}")
    return labeled_count


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _is_correct(direction: str, label: str) -> bool:
    if direction == "buy" and label == "up":
        return True
    if direction == "sell" and label == "down":
        return True
    if direction == "neutral" and label == "flat":
        return True
    return False


def generate_report(input_path: str) -> None:
    records = []
    with open(input_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))

    labeled_4h = [r for r in records if r.get("label_4h")]
    labeled_24h = [r for r in records if r.get("label_24h")]
    sessions = len(set(r.get("session_id", "") for r in records))
    days = len(set((r.get("recorded_at", "")[:10]) for r in records))

    print(f"Records: {len(records)} | 4H labeled: {len(labeled_4h)} | 24H labeled: {len(labeled_24h)}")
    print(f"Sessions: {sessions} | Days: {days}")

    total_labeled = len(labeled_4h) + len(labeled_24h)
    if total_labeled < 200 or days < 5:
        print(f"\n  ** INSUFFICIENT_DATA ** (need >=200 labeled, >=5 days; have {total_labeled}, {days})")
        return

    def _metrics(rows, buy_key, sell_key, label_key, ret_key, mfe_key, mae_key):
        total = len(rows)
        correct = sum(1 for r in rows if _is_correct(
            _classify_direction(int(r.get(buy_key, 0)), int(r.get(sell_key, 0)), gap=5),
            str(r.get(label_key, ""))))
        directional = sum(1 for r in rows if _classify_direction(
            int(r.get(buy_key, 0)), int(r.get(sell_key, 0)), gap=5) in ("buy", "sell"))
        returns = [float(r[ret_key]) for r in rows if r.get(ret_key) is not None]
        mfes = [float(r[mfe_key]) for r in rows if r.get(mfe_key) is not None]
        maes = [float(r[mae_key]) for r in rows if r.get(mae_key) is not None]
        acc = round(correct / max(1, total) * 100, 1)
        cov = round(directional / max(1, total) * 100, 1)
        mean_ret = round(sum(returns) / len(returns), 4) if returns else 0
        sorted_ret = sorted(returns) if returns else [0]
        median_ret = round(sorted_ret[len(sorted_ret) // 2], 4)
        mean_mfe = round(sum(mfes) / len(mfes), 4) if mfes else 0
        mean_mae = round(sum(maes) / len(maes), 4) if maes else 0
        return acc, cov, mean_ret, median_ret, mean_mfe, mean_mae

    for window, rows, lk, rk, mk, ak in [
        ("4H", labeled_4h, "label_4h", "return_4h_pct", "mfe_4h_pct", "mae_4h_pct"),
        ("24H", labeled_24h, "label_24h", "return_24h_pct", "mfe_24h_pct", "mae_24h_pct"),
    ]:
        print(f"\n--- {window} Horizon ({len(rows)} labeled) ---")
        print(f"{'Config':<8s} {'Acc%':>6s} {'Cov%':>6s} {'Mean%':>8s} {'Med%':>8s} {'MFE%':>8s} {'MAE%':>8s}")
        print("-" * 56)
        for cfg, bk, sk in [("V1", "v1_buy", "v1_sell"),
                             ("A", "config_a_buy", "config_a_sell"),
                             ("B", "config_b_buy", "config_b_sell")]:
            acc, cov, mrn, mdn, mfe, mae = _metrics(rows, bk, sk, lk, rk, mk, ak)
            print(f"{cfg:<8s} {acc:>6.1f} {cov:>6.1f} {mrn:>8.4f} {mdn:>8.4f} {mfe:>8.4f} {mae:>8.4f}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description="Phase 15G.7.1 — Macro V2 outcome validation")
    sub = p.add_subparsers(dest="cmd", required=True)
    rp = sub.add_parser("record")
    rp.add_argument("--output", default="data/shadow_records.jsonl")
    lp = sub.add_parser("label")
    lp.add_argument("--input", required=True)
    sp = sub.add_parser("report")
    sp.add_argument("--input", required=True)
    args = p.parse_args()

    if args.cmd == "record":
        record_shadow(args.output)
    elif args.cmd == "label":
        label_outcomes(args.input)
    elif args.cmd == "report":
        generate_report(args.input)


if __name__ == "__main__":
    main()
