#!/usr/bin/env python3
r"""Bước 5 — Prompt 3: Kiểm chứng chất lượng dự đoán priced_in.

Pattern record/label/report từ scripts/validate_macro_v2.py.
Journal đã được NewsService ghi ở bước trước (data/event_assessment_journal.jsonl).
Script này chỉ đọc, không ghi journal.

Usage::

    python scripts/validate_event_assessment.py label
    python scripts/validate_event_assessment.py report
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(iso_str: str) -> datetime | None:
    """Parse ISO timestamp to timezone-aware datetime. Returns None on failure."""
    try:
        s = str(iso_str).replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _read_journal_lines(journal_path: Path) -> list[dict[str, Any]]:
    """Đọc toàn bộ dòng JSON hợp lệ từ file journal. Không ném exception."""
    if not journal_path.exists():
        return []
    lines: list[dict[str, Any]] = []
    try:
        with open(journal_path, encoding="utf-8") as fh:
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


def _read_labels(labels_path: Path) -> dict[str, dict[str, Any]]:
    """Đọc file labels, trả dict {event_key: label_obj}. Không ném exception."""
    if not labels_path.exists():
        return {}
    labels: dict[str, dict[str, Any]] = {}
    try:
        with open(labels_path, encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                    if isinstance(obj, dict) and isinstance(obj.get("event_key"), str):
                        labels[obj["event_key"]] = obj
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    return labels


def _append_label(labels_path: Path, label: dict[str, Any]) -> None:
    """Append 1 dòng label vào file jsonl."""
    labels_path.parent.mkdir(parents=True, exist_ok=True)
    with open(labels_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(label, ensure_ascii=False) + "\n")


def _latest_by_event_key(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Dedup theo event_key, giữ dòng MUỘN NHẤT theo thứ tự file.

    Journal có thể chứa nhiều dòng cho cùng 1 event: bản ghi trùng từ các chu
    kỳ preload trước khi có dedup (Bước 5 review fix), hoặc dự đoán mới khi
    trường priced_in hết hạn 6h và AI được gọi refresh. Ma trận kiểm chứng chỉ
    được đếm MỖI EVENT MỘT LẦN theo dự đoán mới nhất — nếu không, số chu kỳ
    chạy scan thổi phồng mọi ô ma trận, và 1 event refresh đổi prediction sẽ
    rơi vào nhiều ô.
    """
    latest: dict[str, dict[str, Any]] = {}
    for entry in entries:
        event_key = str(entry.get("event_key", ""))
        if event_key:
            latest[event_key] = entry
    return list(latest.values())


# ---------------------------------------------------------------------------
# label
# ---------------------------------------------------------------------------

def _label_past_events(journal_path: Path, labels_path: Path) -> int:
    """Liệt kê assessment đã diễn ra, hỏi người dùng nhập nhãn thực tế."""
    now = _now()
    journal = _read_journal_lines(journal_path)
    if not journal:
        print("Chưa có dữ liệu — journal rỗng hoặc chưa tồn tại.")
        print(f"Đường dẫn mong đợi: {journal_path}")
        return 0

    # Lọc sự kiện đã diễn ra (time_utc < now), sắp xếp theo thời gian.
    past: list[dict[str, Any]] = []
    for entry in journal:
        ev_time = _parse_iso(str(entry.get("time_utc", "")))
        if ev_time is None:
            continue
        if ev_time < now:
            past.append(entry)
    # Mỗi event chỉ liệt kê 1 lần theo dự đoán mới nhất (dedup dòng trùng).
    past = _latest_by_event_key(past)
    past.sort(key=lambda e: str(e.get("time_utc", "")))

    if not past:
        print("Chưa có dữ liệu — tất cả sự kiện trong journal đều chưa diễn ra.")
        return 0

    existing = _read_labels(labels_path)
    new_count = 0

    for idx, entry in enumerate(past, start=1):
        event_key = str(entry.get("event_key", ""))
        if event_key in existing:
            continue  # Đã label rồi — bỏ qua.

        print(f"\n{'─' * 60}")
        print(f"[{idx}/{len(past)}] {entry.get('event_name', '?')}  ({entry.get('currency', '?')})")
        print(f"  Giờ diễn ra (UTC): {entry.get('time_utc', '?')}")
        print(f"  Dự đoán priced_in: {entry.get('priced_in', '?')}")
        print(f"  Dự đoán hướng:    {entry.get('expected_direction', '?')}")
        print(f"  AI confidence:    {entry.get('ai_confidence', '?')}")
        evidence = entry.get("evidence", [])
        if evidence:
            print(f"  Evidence:         {'; '.join(str(e) for e in evidence)}")
        print(f"  Source:           {entry.get('source', '?')}")
        print()

        # Hỏi người dùng
        volatile = _ask_yn("  Thị trường có biến động mạnh quanh sự kiện không? (y/n)")
        direction = _ask_direction("  Giá chạy có đúng expected_direction không? (y/n/?): ")
        price_in = _ask_price_in("  Đánh giá: sự kiện đã được price-in trước đó? (y=yes / p=partial / n=no): ")

        label = {
            "event_key": event_key,
            "labeled_at_utc": _now().isoformat(timespec="seconds"),
            "currency": entry.get("currency", ""),
            "event_name": entry.get("event_name", ""),
            "time_utc": entry.get("time_utc", ""),
            "predicted_priced_in": entry.get("priced_in", ""),
            "predicted_direction": entry.get("expected_direction", ""),
            "volatile": volatile,
            "direction_correct": direction,
            "actual_priced_in": price_in,
        }
        _append_label(labels_path, label)
        existing[event_key] = label
        new_count += 1

    print(f"\n✓ Đã thêm {new_count} nhãn mới vào {labels_path}")
    if new_count == 0:
        print("  (tất cả sự kiện đã diễn ra đều đã được label trước đó)")
    return 0


def _ask_yn(prompt: str) -> str:
    while True:
        ans = input(prompt).strip().lower()
        if ans in {"y", "yes"}:
            return "yes"
        if ans in {"n", "no"}:
            return "no"
        print("  Vui lòng nhập y hoặc n.")


def _ask_direction(prompt: str) -> str:
    while True:
        ans = input(prompt).strip().lower()
        if ans in {"y", "yes"}:
            return "yes"
        if ans in {"n", "no"}:
            return "no"
        if ans in {"?", "không rõ", "khong ro", "unknown"}:
            return "không rõ"
        print("  Vui lòng nhập y, n, hoặc ?.")


def _ask_price_in(prompt: str) -> str:
    while True:
        ans = input(prompt).strip().lower()
        if ans in {"y", "yes"}:
            return "yes"
        if ans in {"p", "partial"}:
            return "partial"
        if ans in {"n", "no"}:
            return "no"
        print("  Vui lòng nhập y (yes), p (partial), hoặc n (no).")


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def _report(journal_path: Path, labels_path: Path) -> int:
    """Đọc journal + labels, in bảng tổng hợp."""
    now = _now()
    journal = _read_journal_lines(journal_path)
    if not journal:
        print("Chưa có dữ liệu — journal rỗng hoặc chưa tồn tại.")
        print(f"Đường dẫn mong đợi: {journal_path}")
        return 0

    # Lọc sự kiện đã diễn ra.
    past: list[dict[str, Any]] = []
    for entry in journal:
        ev_time = _parse_iso(str(entry.get("time_utc", "")))
        if ev_time is None:
            continue
        if ev_time < now:
            past.append(entry)
    # Mỗi event chỉ đếm 1 lần theo dự đoán mới nhất — xem _latest_by_event_key.
    past = _latest_by_event_key(past)
    past.sort(key=lambda e: str(e.get("time_utc", "")))

    if not past:
        print("Chưa có dữ liệu — tất cả sự kiện trong journal đều chưa diễn ra.")
        return 0

    labels = _read_labels(labels_path)
    labeled_count = 0
    labeled_events: list[dict[str, Any]] = []
    unlabeled_count = 0

    for entry in past:
        ek = str(entry.get("event_key", ""))
        if ek in labels:
            labeled_count += 1
            labeled_events.append(entry)
        else:
            unlabeled_count += 1

    total = len(past)
    print(f"\nTổng sự kiện đã diễn ra: {total}")
    print(f"  Đã label: {labeled_count}")
    print(f"  Chưa label: {unlabeled_count}")
    print()

    if labeled_count == 0:
        print("Chưa có nhãn nào được gán — chạy 'python scripts/validate_event_assessment.py label' trước.")
        return 0

    # --- Ma trận 3x3: predicted priced_in vs actual ---
    # Cả predicted và actual đều có 3 giá trị: priced_in / partial / not_priced_in
    categories = ["priced_in", "partial", "not_priced_in"]
    # Map alias về canonical: label dùng y/n/p, prediction dùng priced_in/...
    _canon = {
        # Label values
        "yes": "priced_in",
        "no": "not_priced_in",
        "partial": "partial",
        # Prediction values
        "priced_in": "priced_in",
        "not_priced_in": "not_priced_in",
        "unknown": "not_priced_in",  # fallback: unknown → not_priced_in
    }

    matrix: dict[str, dict[str, int]] = {pred: {act: 0 for act in categories} for pred in categories}
    wrong_details: list[dict[str, Any]] = []

    direction_correct = 0
    direction_wrong = 0
    direction_unknown = 0

    for entry in labeled_events:
        ek = str(entry.get("event_key", ""))
        lab = labels.get(ek, {})
        pred_raw = str(entry.get("priced_in", "")).lower()
        pred = _canon.get(pred_raw, "not_priced_in")
        act_raw = str(lab.get("actual_priced_in", "")).lower()
        act = _canon.get(act_raw, "not_priced_in")

        matrix[pred][act] += 1

        if pred != act:
            wrong_details.append({
                "event_name": entry.get("event_name", "?"),
                "currency": entry.get("currency", "?"),
                "time_utc": entry.get("time_utc", "?"),
                "predicted": pred,
                "actual": act,
                "evidence": entry.get("evidence", []),
            })

        # Direction accuracy
        dir_val = str(lab.get("direction_correct", "")).lower()
        if dir_val == "yes":
            direction_correct += 1
        elif dir_val == "no":
            direction_wrong += 1
        else:
            direction_unknown += 1

    # In ma trận
    print("Ma trận trùng khớp priced_in (dự đoán → thực tế):")
    print()
    header = "                    " + "  ".join(f"{c:>14}" for c in categories)
    print(header)
    print("─" * len(header))
    for pred in categories:
        row = [f"{matrix[pred][act]:>14}" for act in categories]
        print(f"  {pred:<18}" + "  ".join(row))
    print()

    # Tính accuracy
    total_labeled = sum(matrix[p][a] for p in categories for a in categories)
    correct = sum(matrix[c][c] for c in categories)
    if total_labeled > 0:
        print(f"Độ chính xác priced_in: {correct}/{total_labeled} ({100 * correct / total_labeled:.1f}%)")
    print()

    # Direction accuracy
    dir_total = direction_correct + direction_wrong + direction_unknown
    if dir_total > 0:
        dir_known = direction_correct + direction_wrong
        print(f"Độ chính xác hướng (expected_direction):")
        print(f"  Đúng:     {direction_correct}")
        print(f"  Sai:      {direction_wrong}")
        print(f"  Không rõ: {direction_unknown}")
        if dir_known > 0:
            print(f"  Tỉ lệ đúng / đã biết: {direction_correct}/{dir_known} ({100 * direction_correct / dir_known:.1f}%)")
    print()

    # Liệt kê dự đoán sai rõ ràng
    if wrong_details:
        print("Các sự kiện dự đoán priced_in sai (để xem lại evidence):")
        print()
        for wd in wrong_details:
            print(f"  • {wd['event_name']} ({wd['currency']}) — {wd['time_utc']}")
            print(f"    Dự đoán: {wd['predicted']}  |  Thực tế: {wd['actual']}")
            if wd["evidence"]:
                print(f"    Evidence: {'; '.join(str(e) for e in wd['evidence'])}")
            print()
    else:
        print("✓ Tất cả dự đoán priced_in đều khớp với thực tế.")

    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Kiểm chứng chất lượng dự đoán priced_in của Bước 5 (AI Event Impact Assessment).",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("label", help="Nhập nhãn thực tế cho các sự kiện đã diễn ra.")
    sub.add_parser("report", help="In báo cáo tổng hợp: ma trận priced_in, độ chính xác hướng.")

    return p


def main() -> int:
    # Windows console thường dùng cp1252/cp1258 — không encode được tiếng Việt.
    # Reconfigure stdout sang UTF-8; nếu stdout là pipe/file thì bỏ qua.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    args = _parser().parse_args()
    root = _repo_root()
    journal_path = root / "data" / "event_assessment_journal.jsonl"
    labels_path = root / "data" / "event_assessment_labels.jsonl"

    if args.command == "label":
        return _label_past_events(journal_path, labels_path)
    if args.command == "report":
        return _report(journal_path, labels_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())