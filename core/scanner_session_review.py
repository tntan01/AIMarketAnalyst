"""Build AI Session Review prompt from scanner results.

Gom top setup + blocked reasons + macro/news context thanh 1 prompt
de AI viet Market Brief — ban tin thi truong ngan bang tieng Viet.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any


def build_market_brief_prompt(
    rows: list[dict[str, Any]],
    *,
    correlation_context: dict[str, Any] | None = None,
    freshness: dict[str, Any] | None = None,
) -> str:
    """Build the market brief prompt from scanner results.

    Args:
        rows: Sorted scanner rows (all symbols, not just top N).
        correlation_context: DXY/VIX/US10Y/US2Y data.
        freshness: Macro freshness status dict.

    Returns:
        A prompt string ready to send to AI.
    """
    now = datetime.now().astimezone().isoformat(timespec="minutes")

    # --- Top setups (ready + waiting, up to 8) ---
    top_setups: list[dict[str, Any]] = []
    ready_rows = [r for r in rows if r.get("scanner_group") == "ready_now"]
    waiting_rows = [r for r in rows if r.get("scanner_group") == "waiting_confirmation"]
    other_rows = [r for r in rows if r.get("scanner_group") not in ("ready_now", "waiting_confirmation", "blocked")]

    for r in ready_rows[:5]:
        top_setups.append(_compact_row(r))
    for r in waiting_rows[:3]:
        if len(top_setups) >= 8:
            break
        top_setups.append(_compact_row(r))
    for r in other_rows[:2]:
        if len(top_setups) >= 8:
            break
        top_setups.append(_compact_row(r))

    # --- Blocked summary ---
    blocked_reasons: dict[str, int] = {}
    blocked_samples: list[dict[str, str]] = []
    for r in rows:
        if r.get("scanner_group") != "blocked":
            continue
        reason = str(r.get("permission_reason") or r.get("short_reason") or "không rõ")
        blocked_reasons[reason] = blocked_reasons.get(reason, 0) + 1
        if len(blocked_samples) < 5:
            blocked_samples.append({
                "symbol": str(r.get("symbol", "")),
                "reason": reason,
                "permission": str(r.get("trade_permission", "")),
                "m15": str(r.get("m15_quality", "")),
            })

    # --- Pipeline stats ---
    # Use pipeline_stats from the first available analysis_result
    pipeline_stats: dict[str, Any] = {}
    for r in rows:
        analysis = r.get("analysis_result")
        if not isinstance(analysis, dict):
            continue
        diags = analysis.get("pipeline_diagnostics")
        if isinstance(diags, list):
            # Aggregate from this single row (for live scan, each row has its own diag)
            for d in diags:
                if isinstance(d, dict) and d.get("step") == "gate":
                    gate_details = d.get("details", {}) if isinstance(d.get("details"), dict) else {}
                    gate_checks = gate_details.get("gate_checks", []) or []
                    for gc in gate_checks:
                        if isinstance(gc, dict) and gc.get("status") in ("block", "warning"):
                            gate_name = gc.get("gate", "?")
                            pipeline_stats[gate_name] = pipeline_stats.get(gate_name, 0) + 1
            break  # chỉ cần 1 row để lấy gate stats

    # --- Group summary ---
    group_counts: dict[str, int] = {}
    for r in rows:
        g = str(r.get("scanner_group", "unknown"))
        group_counts[g] = group_counts.get(g, 0) + 1

    # --- Macro context ---
    macro_summary: dict[str, Any] = {}
    if isinstance(correlation_context, dict):
        macro_summary["correlation"] = {
            "has_dxy": bool(correlation_context.get("dxy_candles")),
            "has_vix": bool(correlation_context.get("vix_candles")),
            "has_us10y": bool(correlation_context.get("us10y_candles")),
            "has_us2y": bool(correlation_context.get("us2y_candles")),
        }
    if isinstance(freshness, dict):
        macro_summary["freshness"] = freshness

    # Collect news context from first few rows
    for r in rows[:3]:
        analysis = r.get("analysis_result")
        if not isinstance(analysis, dict):
            continue
        macro = analysis.get("macro", {})
        if isinstance(macro, dict):
            events = macro.get("driver_context", {}).get("events", []) if isinstance(macro.get("driver_context"), dict) else []
            if events:
                macro_summary["sample_events"] = [
                    {"title": e.get("title", ""), "currency": e.get("currency", ""),
                     "impact": e.get("impact", ""), "time": str(e.get("time", ""))}
                    for e in events[:5] if isinstance(e, dict)
                ]
            macro_summary["macro_alignment"] = macro.get("alignment_source", "unknown")
            break

    # --- Build prompt ---
    prompt_data = {
        "timestamp": now,
        "top_setups": top_setups,
        "blocked_reasons": [
            {"reason": k, "count": v}
            for k, v in sorted(blocked_reasons.items(), key=lambda x: -x[1])
        ],
        "blocked_samples": blocked_samples,
        "group_summary": group_counts,
        "gate_warnings": pipeline_stats,
        "macro_context": macro_summary,
    }

    return (
        "Bạn là AI Market Strategist của AI Market Analyst. "
        "Dựa trên kết quả quét thị trường sau, viết BẢN TIN THỊ TRƯỜNG "
        "ngắn bằng tiếng Việt (5-8 câu), gồm:\n\n"
        "1. TỔNG QUAN PHIÊN: Thị trường hôm nay nghiêng về hướng nào "
        "(USD mạnh/yếu, risk-on/risk-off), có sự kiện nào đáng chú ý không.\n\n"
        "2. NHÓM NÊN ƯU TIÊN: Nhóm tiền tệ/hàng hóa nào đang có nhiều setup "
        "tốt nhất. VD: 'Hôm nay nên tập trung BUY USD.'\n\n"
        "3. NHÓM NÊN TRÁNH: Setup nào đang bị chặn hàng loạt và lý do.\n\n"
        "4. MỨC RỦI RO KHUYẾN NGHỊ: Có nên giảm risk toàn hệ thống không.\n\n"
        "5. SETUP ĐANG CHỜ: Những mã nào đang waiting_confirmation, "
        "cần theo dõi thêm.\n\n"
        "Chỉ dựa vào dữ liệu đã cung cấp, không tự tạo giá/entry/SL/TP. "
        "Viết đầy đủ từng mục, mỗi mục 2-4 câu. Không dùng markdown ** hay *.\n\n"
        "ĐỊNH DẠNG BẮT BUỘC: Mỗi mục PHẢI bắt đầu bằng dòng riêng với số thứ tự "
        "và tiêu đề viết HOA, kết thúc bằng dấu hai chấm. Ví dụ:\n"
        "1. TỔNG QUAN PHIÊN: ...\n"
        "2. NHÓM NÊN ƯU TIÊN: ...\n"
        "3. NHÓM NÊN TRÁNH: ...\n"
        "4. MỨC RỦI RO KHUYẾN NGHỊ: ...\n"
        "5. SETUP ĐANG CHỜ: ...\n\n"
        "TUYỆT ĐỐI không viết thành đoạn văn liên tục không có tiêu đề.\n\n"
        "DỮ LIỆU QUÉT THỊ TRƯỜNG:\n"
        f"{json.dumps(prompt_data, ensure_ascii=False, default=str, indent=2)}"
    )


def _compact_row(row: dict[str, Any]) -> dict[str, Any]:
    """Extract compact summary from a scanner row."""
    return {
        "symbol": row.get("symbol"),
        "scanner_group": row.get("scanner_group"),
        "scanner_action": row.get("scanner_action"),
        "best_side": row.get("best_side"),
        "best_score": row.get("best_score"),
        "final_score": row.get("final_score"),
        "market_regime": row.get("market_regime"),
        "trade_permission": row.get("trade_permission"),
        "entry_status": row.get("entry_status"),
        "m15_quality": row.get("m15_quality"),
        "risk_reward": row.get("risk_reward"),
        "expected_effective_rr": row.get("expected_effective_rr"),
        "macro_bias": row.get("macro_bias"),
        "score_gap": row.get("score_gap"),
        "price_vs_zone": row.get("price_vs_zone"),
        "short_reason": str(row.get("short_reason") or "")[:120],
        "journal_sample_size": row.get("journal_sample_size"),
        "journal_expectancy_r": row.get("journal_expectancy_r"),
    }
