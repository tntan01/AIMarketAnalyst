#!/usr/bin/env python3
r"""Bước 6 — Prompt 8: Khép vòng phản hồi V8 — đối chiếu AI Macro Verdict với kết quả lệnh.

Journal (data/macro_verdict_journal.jsonl) ghi record JSONL mỗi lần AI trả
verdict, nhưng `trade_result_r`/`trade_outcome` vĩnh viễn None (Major 8 —
vòng phản hồi hở cả hai đầu). Script này:

- ``label``: ĐÓNG ĐẦU OUTCOME — join journal với trade DB (journal.db) theo
  (pair, date, best_side) để điền `trade_result_r`/`trade_outcome` thẳng vào
  dòng journal. Không cần nhập liệu thủ công: kết quả lệnh đã có trong DB.
- ``report``: ĐÓNG ĐẦU ĐÁNH GIÁ — in ma trận chính xác: tỉ lệ thắng theo bias,
  hiệu quả của veto, trung bình R-multiple theo adjustment, độ phủ dữ liệu.

Pattern record/label/report từ scripts/validate_event_assessment.py (Bước 5).

Usage::

    python scripts/validate_macro_verdict.py label
    python scripts/validate_macro_verdict.py report
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _journal_path() -> Path:
    return _repo_root() / "data" / "macro_verdict_journal.jsonl"


def _trade_db_path() -> Path:
    """Trade DB = journal.db (migration 001 — journal_entries là trade store)."""
    base = Path(__file__).resolve().parents[1]
    # Ưu tiên == repo config.paths.app_data_dir()/journal.db; nếu không tồn tại
    # (dev/test) thì rơi về APPDATA hoặc ~/.ai-market-analyst.
    try:
        sys.path.insert(0, str(base))
        from config.paths import journal_db_path  # type: ignore
        return journal_db_path()
    except Exception:
        import os
        appdir = os.getenv("APPDATA")
        if appdir:
            return Path(appdir) / "ai-market-analyst" / "journal.db"
        return Path.home() / ".ai-market-analyst" / "journal.db"


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

def _read_journal_lines(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines: list[dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                    if isinstance(obj, dict):
                        lines.append(obj)
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    return lines


def _load_closed_trades(db_path: Path) -> list[dict[str, Any]]:
    """Đọc lệnh đã đóng từ journal_entries (cùng filter như JournalService).

    Cột join: symbol=pair, opened_at/timestamp_utc=ngày, selected_scenario=side.
    Outcome: ưu tiên result_r (R-multiple) khi non-NULL; mt5_sync rows thường
    KHÔNG có result_r (không có cột SL để tính R) → dùng result_amount (sign).
    """
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "SELECT id, symbol, selected_scenario,"
            "       timestamp_utc, opened_at, closed_at,"
            "       result, result_r, result_pct, result_amount, mode"
            "  FROM journal_entries"
            " WHERE closed_at IS NOT NULL AND closed_at != ''"
            " ORDER BY closed_at"
        )
        return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []
    finally:
        conn.close()


def _normalize_side(value: Any) -> str:
    s = str(value or "").strip().lower()
    return s if s in ("buy", "sell") else ""


def _trade_date(row: dict[str, Any]) -> str:
    """Ngày giao dịch "YYYY-MM-DD" từ opened_at hoặc timestamp_utc (UTC ISO)."""
    for key in ("opened_at", "timestamp_utc"):
        raw = row.get(key)
        if isinstance(raw, str) and raw:
            return raw[:10]
    return ""


def _match_trade(
    journal_record: dict[str, Any],
    trades: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Join journal record với lệnh đã đóng theo (pair, ngày, side).

    Trả None nếu không có lệnh nào khớp. Nếu nhiều lệnh khớp (hiếm), lấy lệnh
    đóng muộn nhất — đại diện cuối cùng của ngày đó.
    """
    pair = str(journal_record.get("pair", "")).strip().upper()
    date = str(journal_record.get("date", "")).strip()
    side = _normalize_side(journal_record.get("best_side"))
    if not pair or not date or not side:
        return None
    candidates: list[dict[str, Any]] = []
    for trade in trades:
        if str(trade.get("symbol", "")).strip().upper() != pair:
            continue
        if _trade_date(trade) != date:
            continue
        if _normalize_side(trade.get("selected_scenario")) != side:
            continue
        candidates.append(trade)
    if not candidates:
        return None
    candidates.sort(key=lambda t: str(t.get("closed_at", "")))
    return candidates[-1]


def _trade_outcome(trade: dict[str, Any]) -> tuple[float | None, str]:
    """(result_r, outcome_label) từ row trade. outcome: win/loss/breakeven/unknown."""
    outcome_code = _normalize_side_outcome(trade)
    r = trade.get("result_r")
    if isinstance(r, (int, float)):
        return float(r), outcome_code
    if outcome_code == "unknown":
        return None, "unknown"
    return None, outcome_code


def _normalize_side_outcome(trade: dict[str, Any]) -> str:
    """Xác định thắng/thua từ tín hiệu có sẵn.

    Ưu tiên label `result` (win/loss/breakeven); nếu trống thì suy từ
    result_amount (dương=win, âm=loss) hoặc result_pct.
    """
    res = str(trade.get("result") or "").strip().lower()
    if res in ("win", "loss", "breakeven"):
        return res
    amount = trade.get("result_amount")
    if isinstance(amount, (int, float)) and amount != 0:
        return "win" if amount > 0 else "loss"
    pct = trade.get("result_pct")
    if isinstance(pct, (int, float)) and pct != 0:
        return "win" if pct > 0 else "loss"
    return "unknown"


# ---------------------------------------------------------------------------
# label — backfill outcome vào journal
# ---------------------------------------------------------------------------

def _label(journal: list[dict[str, Any]], trades: list[dict[str, Any]]) -> int:
    path = _journal_path()
    if not journal:
        print("Chưa có dữ liệu — journal rỗng hoặc chưa tồn tại.")
        print(f"Đường dẫn mong đợi: {path}")
        return 0

    updated = 0
    already = 0
    unmatched = 0
    lines_out: list[str] = []

    for record in journal:
        # Đã có outcome rồi → giữ nguyên (không đè).
        has_outcome = record.get("trade_outcome") in ("win", "loss", "breakeven")
        changed = False
        trade = _match_trade(record, trades)
        if trade is not None:
            r, outcome = _trade_outcome(trade)
            if outcome != "unknown" and not has_outcome:
                record["trade_result_r"] = r
                record["trade_outcome"] = outcome
                record["backfilled_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                changed = True
                updated += 1
            elif has_outcome:
                already += 1
            else:
                unmatched += 1  # có trade nhưng outcome unknown
        else:
            unmatched += 1
        lines_out.append(json.dumps(record, ensure_ascii=False))

    if updated or already:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines_out) + "\n")
        except OSError as exc:
            print(f"LỖI: không ghi được journal: {exc}")
            return 1

    print(f"Tổng record trong journal: {len(journal)}")
    print(f"  Đã backfill outcome:     {updated}")
    print(f"  Đã có outcome trước đó:  {already}")
    print(f"  Chưa có lệnh khớp:       {unmatched}")
    if updated:
        print(f"\n✓ Đã ghi outcome vào {path}")
    return 0


# ---------------------------------------------------------------------------
# report — ma trận chính xác
# ---------------------------------------------------------------------------

def _report(journal: list[dict[str, Any]], trades: list[dict[str, Any]]) -> int:
    if not journal:
        print("Chưa có dữ liệu — journal rỗng hoặc chưa tồn tại.")
        print(f"Đường dẫn mong đợi: {_journal_path()}")
        return 0

    # Đảm bảo outcome có sẵn (nếu journal cũ chưa backfill thì tính tạm).
    for record in journal:
        if record.get("trade_outcome") not in ("win", "loss", "breakeven"):
            trade = _match_trade(record, trades)
            if trade is not None:
                r, outcome = _trade_outcome(trade)
                record["_r"] = r
                record["_outcome"] = outcome
            else:
                record["_outcome"] = "unknown"
        else:
            record["_outcome"] = record.get("trade_outcome")
            record["_r"] = record.get("trade_result_r")

    ai_verdicts = [r for r in journal if r.get("source") == "ai"]
    total = len(journal)
    ai_total = len(ai_verdicts)
    other = total - ai_total

    print(f"\nTổng record journal: {total}")
    print(f"  Verdict AI (source='ai'): {ai_total}")
    print(f"  Fallback/skip:           {other}")
    print()

    if ai_total == 0:
        print("Chưa có verdict AI nào — chạy scan với flag Bước 6 bật trước.")
        return 0

    known = [r for r in ai_verdicts if r.get("_outcome") in ("win", "loss", "breakeven")]
    print(f"Verdict AI có outcome đã biết: {len(known)}/{ai_total}")
    print()

    if not known:
        print("Chưa có outcome nào — chạy 'python scripts/validate_macro_verdict.py label' trước,")
        print("hoặc đợi thêm lệnh đóng để có dữ liệu.")
        return 0

    # --- Tỉ lệ thắng theo bias ---
    print("1) Tỉ lệ thắng theo bias (best_side có thắng không):")
    print()
    by_bias: dict[str, dict[str, int]] = {}
    for r in known:
        bias = str(r.get("bias", "unclear"))
        bucket = by_bias.setdefault(bias, {"win": 0, "loss": 0, "breakeven": 0})
        bucket[r["_outcome"]] += 1
    for bias in ("aligned", "conflict", "unclear"):
        if bias not in by_bias:
            continue
        b = by_bias[bias]
        n = b["win"] + b["loss"] + b["breakeven"]
        wr = 100 * b["win"] / n if n else 0.0
        print(f"  {bias:<9} win={b['win']:>3}  loss={b['loss']:>3}  be={b['breakeven']:>3}  "
              f"→ win rate {wr:.1f}%  (n={n})")
    print()

    # --- Hiệu quả veto ---
    vetoed = [r for r in known if r.get("veto")]
    if vetoed:
        veto_loss = sum(1 for r in vetoed if r["_outcome"] == "loss")
        veto_win = sum(1 for r in vetoed if r["_outcome"] == "win")
        print(f"2) Veto (phe phủ quyết): {len(vetoed)} verdict veto")
        print(f"     Lệnh theo hướng bị veto mà LỖ: {veto_loss}  (veto ĐÚNG nếu lệnh này lỗ)")
        print(f"     Lệnh theo hướng bị veto mà THẮNG: {veto_win}  (veto SAI — bỏ lỡ lệnh ngon)")
        print()
    else:
        print("2) Veto: chưa có verdict nào veto.")
        print()

    # --- Trung bình R theo adjustment ---
    adj_groups: dict[int, list[float]] = {}
    for r in known:
        adj = int(r.get("adjustment", 0))
        if r["_r"] is not None:
            adj_groups.setdefault(adj, []).append(r["_r"])
    if adj_groups:
        print("3) Trung bình R-multiple theo adjustment (chỉ làm khó):")
        print()
        for adj in sorted(adj_groups):
            rs = adj_groups[adj]
            avg = sum(rs) / len(rs)
            print(f"  adjustment={adj:>2}  avg_R={avg:+.2f}  (n={len(rs)})")
        print()

    # --- Độ phủ theo nguồn ---
    src_counts: dict[str, int] = {}
    for r in journal:
        s = str(r.get("source", "unknown"))
        src_counts[s] = src_counts.get(s, 0) + 1
    print("4) Phân bố nguồn verdict (theo dõi 'đốt token vs giá trị'):")
    for s, c in sorted(src_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {s:<24} {c}")

    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Bước 6: đối chiếu AI Macro Verdict journal với kết quả lệnh thực tế.",
    )
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("label", help="Backfill trade_result_r/trade_outcome vào journal từ trade DB.")
    sub.add_parser("report", help="In báo cáo chính xác: bias, veto, adjustment, nguồn.")
    return p


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows console
    except Exception:
        pass
    args = _parser().parse_args()
    trades = _load_closed_trades(_trade_db_path())
    journal = _read_journal_lines(_journal_path())

    if args.command == "label":
        return _label(journal, trades)
    if args.command == "report":
        return _report(journal, trades)
    return 0


if __name__ == "__main__":
    sys.exit(main())