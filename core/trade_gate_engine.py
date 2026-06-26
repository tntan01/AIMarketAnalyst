from __future__ import annotations

from typing import Any

from core.reason_codes import (
    BUY_SELL_SCORE_GAP_LOW,
    DAILY_LOSS_LIMIT_REACHED,
    DATA_QUALITY_WARNING,
    EXPECTED_RR_TOO_LOW,
    HIGH_IMPACT_NEWS_NEARBY,
    M15_LOOSE_CONFIRMATION,
    M15_NOT_CONFIRMED,
    MT5_NOT_READY,
    SPREAD_ABNORMAL,
    WEEKLY_LOSS_LIMIT_REACHED,
    ZONE_BROKEN,
    append_code,
)

# ---------------------------------------------------------------------------
# Gate check result dataclass-like keys (plain dict for zero-dependency)
# ---------------------------------------------------------------------------

# Cap priority: TRADE_BLOCKED > WATCH_ONLY > WAITING_CONFIRMATION
_CAP_PRIORITY = {
    "TRADE_BLOCKED": 3,
    "WATCH_ONLY": 2,
    "WAITING_CONFIRMATION": 1,
}


def _resolve_cap(current: str | None, candidate: str) -> str:
    """Return the stronger (higher priority) cap of the two."""
    if current is None:
        return candidate
    if _CAP_PRIORITY.get(candidate, 0) > _CAP_PRIORITY.get(current, 0):
        return candidate
    return current


# ---------------------------------------------------------------------------
# Individual gate functions
# ---------------------------------------------------------------------------


def _gate_mt5(context: dict[str, Any], result: dict[str, Any]) -> None:
    terminal_connected = context.get("terminal_connected", True)
    broker_logged_in = context.get("broker_logged_in", True)

    if terminal_connected is False or broker_logged_in is False:
        result["allowed"] = False
        result["decision_cap"] = _resolve_cap(result["decision_cap"], "TRADE_BLOCKED")
        append_code(result["block_codes"], MT5_NOT_READY)
        result["reasons"].append("MT5 chưa sẵn sàng (terminal hoặc broker chưa kết nối).")


def _gate_spread(context: dict[str, Any], result: dict[str, Any]) -> None:
    spread_status = context.get("spread_status", "normal")

    if spread_status == "abnormal":
        result["allowed"] = False
        result["decision_cap"] = _resolve_cap(result["decision_cap"], "TRADE_BLOCKED")
        append_code(result["block_codes"], SPREAD_ABNORMAL)
        result["reasons"].append("Spread bất thường, không nên giao dịch.")


def _gate_data_quality_warning(context: dict[str, Any], result: dict[str, Any]) -> None:
    warning = context.get("data_quality_warning", False)

    if warning:
        result["allowed"] = False
        result["decision_cap"] = _resolve_cap(result["decision_cap"], "TRADE_BLOCKED")
        append_code(result["block_codes"], DATA_QUALITY_WARNING)
        result["reasons"].append("Cảnh báo chất lượng dữ liệu.")


def _gate_high_impact_news(context: dict[str, Any], result: dict[str, Any]) -> None:
    high_impact_event_within_30m = context.get("high_impact_event_within_30m", False)

    if high_impact_event_within_30m:
        result["allowed"] = False
        result["decision_cap"] = _resolve_cap(result["decision_cap"], "TRADE_BLOCKED")
        append_code(result["block_codes"], HIGH_IMPACT_NEWS_NEARBY)
        result["reasons"].append("Tin tức tác động mạnh sắp diễn ra trong vòng 30 phút.")


def _gate_m15(context: dict[str, Any], result: dict[str, Any]) -> None:
    m15_quality = context.get("m15_quality")

    if m15_quality in (None, "none"):
        append_code(result["warning_codes"], M15_NOT_CONFIRMED)
        result["decision_cap"] = _resolve_cap(result["decision_cap"], "WATCH_ONLY")
        result["reasons"].append("M15 không xác nhận tín hiệu vào lệnh.")
    elif m15_quality == "loose":
        append_code(result["warning_codes"], M15_LOOSE_CONFIRMATION)
        result["decision_cap"] = _resolve_cap(result["decision_cap"], "WAITING_CONFIRMATION")
        result["reasons"].append("M15 xác nhận lỏng, cần theo dõi thêm.")


def _gate_expected_effective_rr(context: dict[str, Any], result: dict[str, Any]) -> None:
    expected_effective_rr = context.get("expected_effective_rr")
    if expected_effective_rr is None:
        result["decision_cap"] = _resolve_cap(result["decision_cap"], "WATCH_ONLY")
        result["reasons"].append("Chưa có điểm vào — không tính được R:R kỳ vọng.")
        return

    min_expected_effective_rr = context.get("min_expected_effective_rr", 1.3)

    if expected_effective_rr < min_expected_effective_rr:
        append_code(result["warning_codes"], EXPECTED_RR_TOO_LOW)
        result["decision_cap"] = _resolve_cap(result["decision_cap"], "WATCH_ONLY")
        nominal_rr = context.get("risk_reward", "")
        nominal_info = f" (danh nghĩa {nominal_rr})" if nominal_rr else ""
        result["reasons"].append(
            f"Tỷ lệ R:R kỳ vọng ({expected_effective_rr:.1f} sau spread{nominal_info}) thấp hơn mức tối thiểu ({min_expected_effective_rr:.1f})."
        )


def _gate_daily_weekly_loss(context: dict[str, Any], result: dict[str, Any]) -> None:
    daily_loss_limit_reached = context.get("daily_loss_limit_reached", False)
    weekly_loss_limit_reached = context.get("weekly_loss_limit_reached", False)

    if daily_loss_limit_reached:
        result["allowed"] = False
        result["decision_cap"] = _resolve_cap(result["decision_cap"], "TRADE_BLOCKED")
        append_code(result["block_codes"], DAILY_LOSS_LIMIT_REACHED)
        result["reasons"].append("Đã chạm giới hạn thua lỗ trong ngày.")

    if weekly_loss_limit_reached:
        result["allowed"] = False
        result["decision_cap"] = _resolve_cap(result["decision_cap"], "TRADE_BLOCKED")
        append_code(result["block_codes"], WEEKLY_LOSS_LIMIT_REACHED)
        result["reasons"].append("Đã chạm giới hạn thua lỗ trong tuần.")


def _gate_score_gap(context: dict[str, Any], result: dict[str, Any]) -> None:
    score_gap = context.get("score_gap")
    if score_gap is None:
        return

    min_buy_sell_score_gap = context.get("min_buy_sell_score_gap", 10)

    if score_gap < min_buy_sell_score_gap:
        append_code(result["warning_codes"], BUY_SELL_SCORE_GAP_LOW)
        result["decision_cap"] = _resolve_cap(result["decision_cap"], "WAITING_CONFIRMATION")
        result["reasons"].append(
            f"Khoảng cách điểm buy/sell ({score_gap:.0f}) thấp hơn mức tối thiểu ({min_buy_sell_score_gap:.0f})."
        )


def _gate_zone_broken(context: dict[str, Any], result: dict[str, Any]) -> None:
    zone_broken = context.get("zone_broken", False)

    if zone_broken:
        append_code(result["warning_codes"], ZONE_BROKEN)
        result["decision_cap"] = _resolve_cap(result["decision_cap"], "WATCH_ONLY")
        result["reasons"].append("Vùng giá quan trọng đã bị phá vỡ.")


def _gate_account_guard(context: dict[str, Any], result: dict[str, Any]) -> None:
    """Merge account guard result into trade gate.

    Reads optional ``account_guard`` key from context (output of
    :func:`core.account_guard.check_account_guard`).  If the account guard
    reports a block, this gate sets TRADE_BLOCKED and merges all block /
    warning codes and reasons into the trade gate result.
    """
    account_guard = context.get("account_guard")
    if not isinstance(account_guard, dict):
        return

    # Merge stats for downstream consumers
    result["account_guard_stats"] = account_guard.get("stats", {})

    # Merge warning codes (không trùng lặp)
    for code in account_guard.get("warning_codes", []):
        append_code(result["warning_codes"], code)

    # Merge reasons
    for reason in account_guard.get("reasons", []):
        if reason not in result["reasons"]:
            result["reasons"].append(reason)

    # Account guard block → hard TRADE_BLOCKED
    if account_guard.get("blocked") is True or account_guard.get("allowed") is False:
        result["allowed"] = False
        result["decision_cap"] = _resolve_cap(result["decision_cap"], "TRADE_BLOCKED")
        for code in account_guard.get("block_codes", []):
            append_code(result["block_codes"], code)


def _gate_journal_feedback(context: dict[str, Any], result: dict[str, Any]) -> None:
    feedback = context.get("journal_feedback")
    if not isinstance(feedback, dict):
        return

    result["journal_feedback"] = feedback
    for code in feedback.get("warning_codes", []):
        append_code(result["warning_codes"], code)
    for reason in feedback.get("reasons", []):
        if reason not in result["reasons"]:
            result["reasons"].append(reason)

    for code in feedback.get("block_codes", []):
        append_code(result["block_codes"], code)

    cap = feedback.get("decision_cap")
    if cap == "TRADE_BLOCKED":
        result["allowed"] = False
        result["decision_cap"] = _resolve_cap(result["decision_cap"], "TRADE_BLOCKED")
    elif cap in {"WATCH_ONLY", "WAITING_CONFIRMATION"}:
        result["decision_cap"] = _resolve_cap(result["decision_cap"], str(cap))


# ---------------------------------------------------------------------------
# Ordered gate list (order matters for reasons readability)
# ---------------------------------------------------------------------------

_GATES = [
    _gate_mt5,
    _gate_spread,
    _gate_data_quality_warning,
    _gate_high_impact_news,
    _gate_daily_weekly_loss,
    _gate_account_guard,
    _gate_journal_feedback,
    _gate_m15,
    _gate_expected_effective_rr,
    _gate_score_gap,
    _gate_zone_broken,
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_trade_gates(context: dict[str, Any]) -> dict[str, Any]:
    """Run all trade gates against the provided context.

    Parameters
    ----------
    context : dict
        Dictionary carrying all relevant state. Expected keys (all optional
        with sensible defaults):
        - terminal_connected, broker_logged_in
        - spread_status
        - data_quality_warning
        - high_impact_event_within_30m
        - m15_quality
        - expected_effective_rr, min_expected_effective_rr
        - daily_loss_limit_reached, weekly_loss_limit_reached
        - score_gap, min_buy_sell_score_gap
        - zone_broken

    Returns
    -------
    dict
        {
            "allowed": bool,
            "decision_cap": str | None,
            "block_codes": list[str],
            "warning_codes": list[str],
            "reasons": list[str],
        }
    """
    result: dict[str, Any] = {
        "allowed": True,
        "decision_cap": None,
        "block_codes": [],
        "warning_codes": [],
        "reasons": [],
    }

    for gate in _GATES:
        gate(context, result)

    # Hard override: if allowed is False, decision_cap must be TRADE_BLOCKED
    if not result["allowed"]:
        result["decision_cap"] = "TRADE_BLOCKED"

    return result
