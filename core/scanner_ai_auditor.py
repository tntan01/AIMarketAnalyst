from __future__ import annotations

import json
import re
from typing import Any


AUDIT_AGREEMENTS = {"agree", "caution", "disagree"}


def default_ai_setup_audit(reason: str = "not_audited") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "agreement": "caution",
        "confidence_score": 0,
        "trade_plan_quality": 0,
        "setup_summary": "",
        "market_context_summary": "",
        "risk_flags": [],
        "missing_confirmations": [],
        "do_not_trade_reason": "",
        "auditor_error": reason,
    }


def parse_ai_setup_audit(raw: str) -> dict[str, Any]:
    payload = _extract_json_object(raw)
    if payload is None:
        audit = default_ai_setup_audit("invalid_json")
        audit["raw_response"] = str(raw or "")[:1200]
        return audit
    return normalize_ai_setup_audit(payload)


def normalize_ai_setup_audit(payload: dict[str, Any]) -> dict[str, Any]:
    agreement = str(payload.get("agreement") or "caution").strip().lower()
    if agreement not in AUDIT_AGREEMENTS:
        agreement = "caution"

    return {
        "schema_version": 1,
        "agreement": agreement,
        "confidence_score": _score(payload.get("confidence_score")),
        "trade_plan_quality": _score(payload.get("trade_plan_quality")),
        "setup_summary": _text(payload.get("setup_summary"), 500),
        "market_context_summary": _text(payload.get("market_context_summary"), 500),
        "risk_flags": _text_list(payload.get("risk_flags"), 8, 180),
        "missing_confirmations": _text_list(payload.get("missing_confirmations"), 8, 180),
        "do_not_trade_reason": _text(payload.get("do_not_trade_reason"), 500),
    }


def summarize_ai_setup_audit(audit: dict[str, Any]) -> str:
    if not isinstance(audit, dict) or audit.get("auditor_error"):
        return ""
    agreement = str(audit.get("agreement") or "caution")
    label = {
        "agree": "AI đồng thuận",
        "caution": "AI cảnh báo",
        "disagree": "AI không đồng thuận",
    }.get(agreement, "AI kiểm định")
    summary = str(audit.get("setup_summary") or audit.get("market_context_summary") or "").strip()
    reason = str(audit.get("do_not_trade_reason") or "").strip()
    if reason:
        summary = reason if not summary else f"{summary} {reason}"
    if not summary:
        return label
    return f"{label}: {summary}"


def build_ai_setup_audit_prompt(row: dict[str, Any]) -> str:
    analysis = row.get("analysis_result") if isinstance(row.get("analysis_result"), dict) else {}
    scenario = _best_scenario(row)
    audit_input = {
        "symbol": row.get("symbol"),
        "broker_symbol": row.get("broker_symbol"),
        "scanner_group": row.get("scanner_group"),
        "scanner_decision": row.get("scanner_decision"),
        "scanner_action": row.get("scanner_action"),
        "trade_permission": row.get("trade_permission"),
        "permission_reason": row.get("permission_reason"),
        "market_regime": row.get("market_regime"),
        "direction_bias": row.get("direction_bias"),
        "best_side": row.get("best_side"),
        "buy_score": row.get("buy_score"),
        "sell_score": row.get("sell_score"),
        "best_score": row.get("best_score"),
        "final_score": row.get("final_score"),
        "score_gap": row.get("score_gap"),
        "opportunity_score": row.get("opportunity_score"),
        "entry_status": row.get("entry_status"),
        "price_vs_zone": row.get("price_vs_zone"),
        "m15_quality": row.get("m15_quality"),
        "risk_reward": row.get("risk_reward"),
        "expected_effective_rr": row.get("expected_effective_rr"),
        "macro_score": row.get("macro_score"),
        "macro_bias": row.get("macro_bias"),
        "macro_confidence": row.get("macro_confidence"),
        "journal_sample_size": row.get("journal_sample_size"),
        "journal_expectancy_r": row.get("journal_expectancy_r"),
        "short_reason": row.get("short_reason"),
        "gate": analysis.get("trade_gate") if isinstance(analysis, dict) else {},
        "data_quality": _compact_dict(analysis.get("data_quality") if isinstance(analysis, dict) else {}),
        "macro": _compact_dict(analysis.get("macro") if isinstance(analysis, dict) else {}),
        "selected_scenario": _compact_dict(scenario),
        "entry_checklist": _compact_list(analysis.get("entry_checklist") if isinstance(analysis, dict) else [], 10),
        "reason_codes": _compact_list(analysis.get("reason_codes") if isinstance(analysis, dict) else [], 12),
        "warning_codes": _compact_list(analysis.get("warning_codes") if isinstance(analysis, dict) else [], 12),
        "block_codes": _compact_list(analysis.get("block_codes") if isinstance(analysis, dict) else [], 12),
    }
    return (
        "Bạn là AI Setup Auditor của AI Market Analyst. Nhiệm vụ: kiểm định setup đã được rule engine tạo ra, "
        "không được tự tạo entry/SL/TP mới và không được ra lệnh giao dịch.\n"
        "Chỉ trả về JSON object hợp lệ, không markdown, không giải thích ngoài JSON.\n"
        "Schema bắt buộc:\n"
        "{\n"
        '  "agreement": "agree|caution|disagree",\n'
        '  "confidence_score": 0-100,\n'
        '  "trade_plan_quality": 0-100,\n'
        '  "setup_summary": "1 câu ngắn tiếng Việt",\n'
        '  "market_context_summary": "1 câu ngắn tiếng Việt",\n'
        '  "risk_flags": ["tối đa 8 cảnh báo"],\n'
        '  "missing_confirmations": ["tối đa 8 điều cần chờ"],\n'
        '  "do_not_trade_reason": "để trống nếu không có lý do đứng ngoài"\n'
        "}\n"
        "Quy tắc: agreement=agree chỉ khi setup sạch, gate không block, entry/M15/RR hợp lý. "
        "agreement=caution nếu cần chờ hoặc có xung đột nhỏ. agreement=disagree nếu rủi ro/gate/data/news làm setup không nên giao dịch.\n"
        "Dữ liệu setup:\n"
        f"{json.dumps(audit_input, ensure_ascii=False, default=str)}"
    )


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        try:
            value = json.loads(fenced.group(1))
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            value = json.loads(text[start:end + 1])
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _score(value: object) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    if number != number:
        return 0
    return max(0, min(100, int(round(number))))


def _text(value: object, limit: int) -> str:
    if value is None:
        return ""
    return str(value).strip()[:limit]


def _text_list(value: object, max_items: int, limit: int) -> list[str]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        items = []
    return [_text(item, limit) for item in items[:max_items] if _text(item, limit)]


def _compact_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _compact_list(value: object, max_items: int) -> list[Any]:
    return list(value[:max_items]) if isinstance(value, list) else []


def _best_scenario(row: dict[str, Any]) -> dict[str, Any]:
    analysis = row.get("analysis_result") if isinstance(row.get("analysis_result"), dict) else {}
    scenarios = analysis.get("scenarios") if isinstance(analysis, dict) else None
    if not isinstance(scenarios, list):
        return {}
    best_side = str(row.get("best_side") or "")
    for scenario in scenarios:
        if isinstance(scenario, dict) and scenario.get("type") == best_side:
            return scenario
    for scenario in scenarios:
        if isinstance(scenario, dict) and scenario.get("type") in {"buy", "sell"}:
            return scenario
    return {}
