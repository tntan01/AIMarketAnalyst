from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.reason_codes import (
    DAILY_LOSS_LIMIT_REACHED,
    MAX_CONSECUTIVE_LOSSES_REACHED,
    MAX_OPEN_RISK_REACHED,
    WEEKLY_LOSS_LIMIT_REACHED,
    append_code,
)

RISK_INCREASING_ACTIONS = {
    "open_new_trade",
    "increase_position",
    "move_sl_further",
    "add_pending_order",
}

RISK_REDUCING_ACTIONS = {
    "close_trade",
    "partial_close",
    "move_sl_closer",
    "move_sl_to_breakeven",
    "cancel_pending_order",
}

_DEFAULT_SETTINGS: dict[str, object] = {
    "max_daily_loss_pct": 2.0,
    "max_weekly_loss_pct": 5.0,
    "max_consecutive_losses": 3,
    "max_open_risk_pct": 3.0,
    "trader_timezone": "Asia/Ho_Chi_Minh",
}


def _resolve_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, KeyError):
        try:
            return ZoneInfo("Asia/Ho_Chi_Minh")
        except (ZoneInfoNotFoundError, KeyError):
            return ZoneInfo("UTC")


def _ensure_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed
    return None


def get_day_range(
    now: datetime | None = None,
    timezone_name: str = "Asia/Ho_Chi_Minh",
) -> tuple[datetime, datetime]:
    tz = _resolve_timezone(timezone_name)
    now = (now or datetime.now(UTC)).astimezone(tz)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end


def get_week_range(
    now: datetime | None = None,
    timezone_name: str = "Asia/Ho_Chi_Minh",
) -> tuple[datetime, datetime]:
    tz = _resolve_timezone(timezone_name)
    now = (now or datetime.now(UTC)).astimezone(tz)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start -= timedelta(days=start.weekday())
    end = start + timedelta(days=7)
    return start, end


def calculate_loss_stats(
    closed_trades: list[dict[str, object]] | None = None,
    now: datetime | None = None,
    timezone_name: str = "Asia/Ho_Chi_Minh",
) -> dict[str, Any]:
    trades = closed_trades or []

    day_start, day_end = get_day_range(now, timezone_name)
    week_start, week_end = get_week_range(now, timezone_name)

    daily_result_pct = 0.0
    weekly_result_pct = 0.0
    daily_trade_count = 0
    weekly_trade_count = 0

    loss_sequence: list[bool] = []

    for trade in trades:
        if not isinstance(trade, dict):
            continue

        closed_at = _ensure_datetime(trade.get("closed_at"))
        if closed_at is None:
            continue

        try:
            result_pct = float(trade.get("result_pct") or 0.0)
        except (TypeError, ValueError):
            result_pct = 0.0

        try:
            result_r = float(trade.get("result_r") or 0.0)
        except (TypeError, ValueError):
            result_r = 0.0

        is_loss = result_pct < 0.0 if result_pct != 0.0 else result_r < 0.0

        if day_start <= closed_at < day_end:
            daily_result_pct += result_pct
            daily_trade_count += 1

        if week_start <= closed_at < week_end:
            weekly_result_pct += result_pct
            weekly_trade_count += 1

        loss_sequence.append(is_loss)

    consecutive_losses = 0
    for is_loss in reversed(loss_sequence):
        if is_loss:
            consecutive_losses += 1
        else:
            break

    return {
        "daily_result_pct": round(daily_result_pct, 4),
        "weekly_result_pct": round(weekly_result_pct, 4),
        "consecutive_losses": consecutive_losses,
        "daily_trade_count": daily_trade_count,
        "weekly_trade_count": weekly_trade_count,
    }


def calculate_open_risk_pct(open_trades: list[dict[str, object]] | None = None) -> float:
    trades = open_trades or []
    total = 0.0
    for trade in trades:
        if not isinstance(trade, dict):
            continue
        risk = 0.0
        for key in ("risk_pct", "planned_risk_pct", "current_risk_pct"):
            val = trade.get(key)
            if val is not None:
                try:
                    risk = float(val)
                except (TypeError, ValueError):
                    risk = 0.0
                else:
                    break
        total += risk
    return round(total, 4)


def check_account_guard(
    closed_trades: list[dict[str, object]] | None = None,
    open_trades: list[dict[str, object]] | None = None,
    settings: dict[str, object] | None = None,
    action: str = "open_new_trade",
    now: datetime | None = None,
) -> dict[str, Any]:
    cfg = dict(_DEFAULT_SETTINGS)
    if settings:
        cfg.update(settings)

    max_daily_pct = float(cfg.get("max_daily_loss_pct", 2.0))
    max_weekly_pct = float(cfg.get("max_weekly_loss_pct", 5.0))
    max_consecutive = int(cfg.get("max_consecutive_losses", 3))
    max_open_risk = float(cfg.get("max_open_risk_pct", 3.0))
    timezone_name = str(cfg.get("trader_timezone", "Asia/Ho_Chi_Minh"))

    stats = calculate_loss_stats(closed_trades, now=now, timezone_name=timezone_name)
    open_risk = calculate_open_risk_pct(open_trades)
    stats["open_risk_pct"] = open_risk

    block_codes: list[str] = []
    warning_codes: list[str] = []
    reasons: list[str] = []

    daily_pct = float(stats["daily_result_pct"])
    weekly_pct = float(stats["weekly_result_pct"])
    consecutive = int(stats["consecutive_losses"])

    if daily_pct <= -max_daily_pct:
        append_code(block_codes, DAILY_LOSS_LIMIT_REACHED)
        reasons.append(
            f"Đã chạm giới hạn lỗ trong ngày ({daily_pct:.2f}% <= -{max_daily_pct}%), "
            "không được mở thêm lệnh mới."
        )

    if weekly_pct <= -max_weekly_pct:
        append_code(block_codes, WEEKLY_LOSS_LIMIT_REACHED)
        reasons.append(
            f"Đã chạm giới hạn lỗ trong tuần ({weekly_pct:.2f}% <= -{max_weekly_pct}%), "
            "không được mở thêm lệnh mới."
        )

    if consecutive >= max_consecutive:
        append_code(block_codes, MAX_CONSECUTIVE_LOSSES_REACHED)
        reasons.append(
            f"Đã có {consecutive} lệnh thua liên tiếp (giới hạn {max_consecutive}), "
            "nên dừng giao dịch."
        )

    if open_risk >= max_open_risk:
        append_code(block_codes, MAX_OPEN_RISK_REACHED)
        reasons.append(
            f"Tổng rủi ro lệnh đang mở ({open_risk:.2f}%) đã vượt giới hạn ({max_open_risk}%)."
        )

    is_risk_increasing = action in RISK_INCREASING_ACTIONS

    if block_codes and is_risk_increasing:
        allowed = False
        blocked = True
    else:
        allowed = True
        blocked = False

    return {
        "allowed": allowed,
        "blocked": blocked,
        "action": action,
        "block_codes": block_codes,
        "warning_codes": warning_codes,
        "reasons": reasons,
        "stats": stats,
    }
