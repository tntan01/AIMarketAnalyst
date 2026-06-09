from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


from core.scanner_ranking_engine import (
    enrich_scanner_row_with_ranking,
    READY_NOW,
    WAITING_CONFIRMATION,
    WATCH_ZONE,
    BLOCKED,
)


ACTION_PRIORITY = {"ready": 0, "watch": 1, "wait": 2, "skip": 3}
PERMISSION_PRIORITY = {"allowed": 0, "caution": 1, "blocked": 2}
GROUP_PRIORITY_NEW = {
    READY_NOW: 0,
    WAITING_CONFIRMATION: 1,
    WATCH_ZONE: 2,
    BLOCKED: 3,
}


@dataclass(frozen=True, slots=True)
class ScannerRequest:
    symbols: list[str]
    account_balance: float
    risk_percent: float
    timezone_name: str
    max_ai_details: int = 3
    auto_trade_enabled: bool = False


def classify_scanner_action(
    *,
    best_score: int,
    permission: str,
    has_trade_plan: bool,
    price_in_entry_zone: bool = False,
    h1_confirmation: bool = False,
) -> str:
    if permission == "blocked" or best_score < 60:
        return "skip"
    if best_score >= 80 and permission == "allowed" and has_trade_plan and (price_in_entry_zone or h1_confirmation):
        return "ready"
    if best_score >= 75 and permission != "blocked":
        return "watch"
    return "wait"


def scanner_row_from_analysis(result: dict[str, Any], *, broker_symbol: str | None = None) -> dict[str, Any]:
    scores = result.get("scenario_scores", {})
    buy_score = int(scores.get("buy", {}).get("signal_score", scores.get("buy", {}).get("total", 0)))
    sell_score = int(scores.get("sell", {}).get("signal_score", scores.get("sell", {}).get("total", 0)))
    best_side = "buy" if buy_score >= sell_score else "sell"
    best_score = max(buy_score, sell_score)
    permission = str(result.get("trade_permission", {}).get("status", "blocked"))
    scenarios = [item for item in result.get("scenarios", []) if item.get("type") in {"buy", "sell"}]
    best_plan = next((item for item in scenarios if item.get("type") == best_side), scenarios[0] if scenarios else None)
    risk_reward = best_plan.get("risk_reward") if best_plan else None
    technical = result.get("technical", {}) if isinstance(result.get("technical"), dict) else {}
    price_vs_zone = price_vs_entry_zone(
        technical.get("price"),
        best_plan.get("entry_zone") if best_plan else None,
        technical.get("atr_h4") or technical.get("atr_d1") or 0.0,
    )
    ready_to_trade = bool(best_plan and best_plan.get("ready_to_trade"))
    action = classify_scanner_action(
        best_score=best_score,
        permission=permission,
        has_trade_plan=ready_to_trade,
        price_in_entry_zone=bool(best_plan and best_plan.get("price_in_entry_zone")),
        h1_confirmation=bool(best_plan and best_plan.get("h1_confirmation")),
    )

    # Extract macro info
    macro_buy = int(scores.get("buy", {}).get("macro_alignment", 15))
    macro_sell = int(scores.get("sell", {}).get("macro_alignment", 15))
    macro_score = macro_buy if best_side == "buy" else macro_sell
    macro_confidence = float(scores.get("buy", {}).get("macro_confidence", 1.0))
    macro_bias = _classify_macro_bias(result, best_side)

    # ---- Phase 15: new ranking metadata ----
    decision_engine = result.get("decision_engine", {})
    if not isinstance(decision_engine, dict):
        decision_engine = {}
    row_final_score = result.get("final_score", best_score)
    m15_quality = best_plan.get("m15_quality") if best_plan else None
    expected_effective_rr = best_plan.get("expected_effective_rr") if best_plan else None
    score_gap = result.get("decision_summary", {}).get("score_gap")

    row = {
        "rank": 0,
        "symbol": result.get("symbol", ""),
        "broker_symbol": broker_symbol or result.get("data_quality", {}).get("broker_symbol", ""),
        "market_regime": result.get("market_regime", {}).get("primary", "unknown"),
        "direction_bias": result.get("direction_bias", "stand_aside"),
        "trade_permission": permission,
        "permission_reason": result.get("trade_permission", {}).get("reason", ""),
        "buy_score": buy_score,
        "sell_score": sell_score,
        "best_side": best_side if best_score >= 50 else "stand_aside",
        "best_score": best_score,
        "scanner_action": action,
        "entry_status": best_plan.get("entry_status") if best_plan else "waiting_for_confirmation",
        "price_vs_zone": price_vs_zone,
        "risk_reward": risk_reward,
        "macro_score": macro_score,
        "macro_bias": macro_bias,
        "macro_confidence": round(macro_confidence, 2),
        "short_reason": build_short_reason(result, best_side, best_score, permission, best_plan),
        "ai_summary_available": False,
        "detail_action": "View Detail",
        "analysis_result": result,
        # ---- Phase 15 ranking fields ----
        "final_score": row_final_score,
        "scanner_decision": decision_engine.get("decision", ""),
        "legacy_action": decision_engine.get("legacy_action", ""),
        "score_gap": score_gap,
        "m15_quality": m15_quality,
        "expected_effective_rr": expected_effective_rr,
    }

    return enrich_scanner_row_with_ranking(row)


def blocked_scanner_row(symbol: str, reason: str, *, broker_symbol: str = "") -> dict[str, Any]:
    row = {
        "rank": 0,
        "symbol": symbol,
        "broker_symbol": broker_symbol,
        "market_regime": "unknown",
        "direction_bias": "stand_aside",
        "trade_permission": "blocked",
        "permission_reason": reason,
        "buy_score": 0,
        "sell_score": 0,
        "best_side": "stand_aside",
        "best_score": 0,
        "scanner_action": "skip",
        "entry_status": "data_unavailable",
        "price_vs_zone": "unknown",
        "risk_reward": None,
        "macro_score": 15,
        "macro_bias": "neutral",
        "macro_confidence": 0.0,
        "short_reason": reason,
        "ai_summary_available": False,
        "detail_action": "View Detail",
        "analysis_result": None,
        # Phase 15 ranking fields
        "final_score": 0,
        "scanner_decision": "TRADE_BLOCKED",
        "legacy_action": "stand_aside",
        "score_gap": 0,
        "m15_quality": None,
        "expected_effective_rr": None,
    }
    return enrich_scanner_row_with_ranking(row)


def sort_scanner_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            GROUP_PRIORITY_NEW.get(
                str(row.get("scanner_group")),
                ACTION_PRIORITY.get(str(row.get("scanner_action")), 99),
            ),
            -int(row.get("opportunity_score", 0)),
            -int(row.get("final_score", row.get("best_score", 0))),
            -_safe_rr(row),
            str(row.get("symbol", "")),
        ),
    )
    for index, row in enumerate(sorted_rows, start=1):
        row["rank"] = index
    return sorted_rows


def _safe_rr(row: dict[str, Any]) -> float:
    """Get best available R:R value for sorting."""
    e_rr = row.get("expected_effective_rr")
    if e_rr is not None:
        try:
            return float(e_rr)
        except (ValueError, TypeError):
            pass
    return risk_reward_value(row.get("risk_reward"))


def ai_targets(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []

    # Filter: not blocked
    eligible = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        # Check blocked status
        group = str(row.get("scanner_group", ""))
        permission = str(row.get("trade_permission", ""))
        if group == BLOCKED or permission == "blocked":
            continue

        # Legacy fallback for rows without scanner_group
        if not group:
            if int(row.get("best_score", 0)) < 75:
                continue

        eligible.append(row)

    # Sort by: group priority > opportunity_score > final_score > best_score
    eligible.sort(
        key=lambda r: (
            GROUP_PRIORITY_NEW.get(
                str(r.get("scanner_group")),
                99,
            ),
            -int(r.get("opportunity_score", 0)),
            -int(r.get("final_score", r.get("best_score", 0))),
            -int(r.get("best_score", 0)),
        ),
    )

    return eligible[: max(0, limit)]


def scanner_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    # Legacy counts (unchanged)
    ready_count = sum(1 for row in rows if row.get("scanner_action") == "ready")
    watch_count = sum(1 for row in rows if row.get("scanner_action") == "watch")
    wait_count = sum(1 for row in rows if row.get("scanner_action") == "wait")
    skip_count = sum(1 for row in rows if row.get("scanner_action") == "skip")

    # Phase 15: group-based counts
    ready_now = 0
    waiting = 0
    watch_zone = 0
    blocked = 0
    scores: list[int] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        group = row.get("scanner_group")
        if not group:
            # fallback from legacy scanner_action
            action = str(row.get("scanner_action", "")).strip().lower()
            if action == "ready":
                group = READY_NOW
            elif action in ("wait", "wait_for_confirmation"):
                group = WAITING_CONFIRMATION
            elif action == "watch":
                group = WATCH_ZONE
            elif action == "skip":
                group = BLOCKED
            else:
                group = WATCH_ZONE

        if group == READY_NOW:
            ready_now += 1
        elif group == WAITING_CONFIRMATION:
            waiting += 1
        elif group == WATCH_ZONE:
            watch_zone += 1
        elif group == BLOCKED:
            blocked += 1

        score = row.get("opportunity_score")
        if isinstance(score, (int, float)):
            scores.append(int(score))

    top = max(scores) if scores else None
    avg = round(sum(scores) / len(scores), 2) if scores else 0

    return {
        "ready_count": ready_count,
        "watch_count": watch_count,
        "wait_count": wait_count,
        "skip_count": skip_count,
        "ready_now_count": ready_now,
        "waiting_confirmation_count": waiting,
        "watch_zone_count": watch_zone,
        "blocked_count": blocked,
        "top_opportunity_score": top,
        "average_opportunity_score": avg,
    }


def build_scanner_output(rows: list[dict[str, Any]], request: ScannerRequest, ai_called: int) -> dict[str, Any]:
    return {
        "mode": "scanner",
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "symbols_scanned": len(rows),
        "ai_details_limit": request.max_ai_details,
        "ai_called": ai_called,
        "summary": scanner_summary(rows),
        "rows": rows,
    }


def build_short_reason(
    result: dict[str, Any],
    best_side: str,
    best_score: int,
    permission: str,
    best_plan: dict[str, Any] | None,
) -> str:
    smc_score = best_plan_score_smc(result, best_side)
    smc_note = f" SMC {smc_score}/15." if smc_score is not None else ""
    if permission == "blocked":
        return str(result.get("trade_permission", {}).get("reason", "Bị chặn vì dữ liệu hoặc rủi ro chưa đạt."))
    if best_plan:
        side_text = "mua" if best_side == "buy" else "bán"
        if not best_plan.get("ready_to_trade"):
            return (
                f"Ưu tiên {side_text}, điểm {best_score}/100; "
                f"{best_plan.get('invalid_reason') or 'đang theo dõi vùng vào lệnh, chưa đủ xác nhận H1.'}{smc_note}"
            )
        return f"Ưu tiên {side_text}, điểm {best_score}/100; {best_plan.get('condition', 'chờ xác nhận H1.')}{smc_note}"
    if best_score >= 75:
        return "Điểm tốt nhưng chưa có vùng vào lệnh đủ sạch, cần theo dõi thêm."
    if best_score >= 60:
        return "Setup chưa rõ, chờ thêm xác nhận từ D1/H4/H1."
    return "Điểm thấp hoặc rủi ro cao, nên bỏ qua."


def best_plan_score_smc(result: dict[str, Any], best_side: str) -> int | None:
    scores = result.get("scenario_scores", {})
    if not isinstance(scores, dict):
        return None
    side_score = scores.get(best_side, {})
    if not isinstance(side_score, dict) or "smc_quality" not in side_score:
        return None
    try:
        return int(side_score["smc_quality"])
    except (TypeError, ValueError):
        return None


def risk_reward_value(value: object) -> float:
    if not value:
        return 0.0
    text = str(value)
    if ":" not in text:
        return 0.0
    try:
        return float(text.split(":", 1)[1])
    except ValueError:
        return 0.0


def price_vs_entry_zone(price: object, entry_zone: object, atr_value: object) -> str:
    if not isinstance(price, (int, float)) or not isinstance(entry_zone, list) or len(entry_zone) != 2:
        return "unknown"
    try:
        current = float(price)
        low = float(min(entry_zone))
        high = float(max(entry_zone))
        atr = float(atr_value or 0.0)
    except (TypeError, ValueError):
        return "unknown"
    if low <= current <= high:
        return "in_zone"
    distance = low - current if current < low else current - high
    if atr > 0 and distance <= atr * 0.5:
        return "near_zone"
    return "far"


def _classify_macro_bias(result: dict[str, Any], best_side: str) -> str:
    """Classify macro bias relative to the best technical side.

    Returns one of: 'aligned' (macro agrees with technical),
    'neutral' (macro is neutral or unclear),
    'divergent' (macro disagrees with technical — warning flag).
    """
    scores = result.get("scenario_scores", {})
    macro_buy = int(scores.get("buy", {}).get("macro_alignment", 15))
    macro_sell = int(scores.get("sell", {}).get("macro_alignment", 15))
    macro_diff = macro_buy - macro_sell

    if abs(macro_diff) < 5:
        return "neutral"
    if best_side == "buy" and macro_diff >= 5:
        return "aligned"
    if best_side == "sell" and macro_diff <= -5:
        return "aligned"
    return "divergent"
