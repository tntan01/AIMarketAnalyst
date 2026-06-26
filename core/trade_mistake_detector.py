"""Trade mistake detector — auto-detect trader behavioral mistakes from journal data.

Phase 12: this module automatically detects common trading mistakes from
trade journal entries.  It reads trade data (planned vs actual lots, entry
prices, stop loss, timing, M15 quality, news context, etc.) and produces a
structured result with auto-detected mistake tags and codes.

Design principles
-----------------
* **Detection only.**  This module only detects and tags mistakes.  It does
  NOT change any scoring, final_score, decision, or gate logic.
* **No Phase 13.**  It does not compute a new final_score.
* **No Phase 14.**  It does not create a decision_engine.
* **No migration.**  It does not touch database schemas.
* **Safe on dirty data.**  Never raises on malformed input — returns a
  safe default result instead.
* **Manual tags preserved.**  Any pre-existing ``manual_mistake_tags`` are
  passed through, never overwritten.  Auto-detected tags are separate from
  manual tags.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from core.reason_codes import (
    MISTAKE_CHASED_PRICE,
    MISTAKE_CLOSED_TOO_EARLY,
    MISTAKE_DATA_INCOMPLETE,
    MISTAKE_DETECTOR_OK,
    MISTAKE_ENTERED_TOO_EARLY,
    MISTAKE_IGNORED_M15,
    MISTAKE_IGNORED_NEWS,
    MISTAKE_MOVED_STOP_LOSS,
    MISTAKE_OVERSIZED_POSITION,
    MISTAKE_REVENGE_TRADE_CONFIRMED,
    MISTAKE_REVENGE_TRADE_WARNING,
)
from core.safe_types import normalize_tags, safe_float, truthy

# ---------------------------------------------------------------------------
# Default detector settings
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS: dict[str, object] = {
    "oversized_lot_multiplier": 1.2,
    "revenge_trade_minutes": 5,
    "revenge_lot_multiplier": 1.5,
    "chased_price_tolerance_pct": 0.10,
    "closed_too_early_min_planned_r_multiple": 1.0,
    "closed_too_early_actual_r_threshold": 0.5,
}



def safe_datetime(value: object) -> datetime | None:
    """Safely parse *value* into a timezone-aware datetime.

    Accepts datetime objects (returned as-is), ISO-8601 strings
    (with or without timezone offset), and ``Z``-suffixed UTC
    strings.  Strings without timezone info are treated as UTC.

    Returns ``None`` for invalid / empty / unparseable input.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        normalized = stripped.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed
    return None




def add_unique(items: list[str], value: str) -> None:
    """Append *value* to *items* if it is non-empty and not already present.

    Does not change the order of existing elements.
    """
    if not value:
        return
    if value not in items:
        items.append(value)


def default_mistake_detection_result(reason: str = "no_mistake_detected") -> dict[str, Any]:
    """Return a safe default result when no mistakes are detected."""
    return {
        "auto_mistake_tags": [],
        "manual_mistake_tags": [],
        "all_mistake_tags": [],
        "mistake_codes": [],
        "warning_codes": [],
        "reason_codes": [MISTAKE_DETECTOR_OK],
        "score_breakdown": {},
        "reason": reason,
        "summary": "Không phát hiện lỗi hành vi rõ ràng.",
    }


def detect_oversized_position(
    trade: dict[str, object],
    settings: dict[str, object] | None = None,
) -> dict[str, object]:
    """Detect whether *trade* has an oversized position vs the plan.

    Returns a partial result dict with *triggered* bool and *score_breakdown*
    info.  The caller merges this into the main result.
    """
    cfg = dict(DEFAULT_SETTINGS)
    if settings:
        cfg.update(settings)

    planned_lot = safe_float(trade.get("planned_lot"))
    actual_lot = safe_float(trade.get("actual_lot"))
    threshold = float(cfg.get("oversized_lot_multiplier", 1.2))

    triggered = False
    tags: list[str] = []
    codes: list[str] = []
    warnings: list[str] = []

    if planned_lot > 0 and actual_lot > 0:
        if actual_lot > planned_lot * threshold:
            triggered = True
            tags.append("oversized_position")
            codes.append(MISTAKE_OVERSIZED_POSITION)
    elif actual_lot > 0 and planned_lot <= 0:
        # Có actual lot nhưng không có planned lot → không kết luận được
        pass

    return {
        "triggered": triggered,
        "tags": tags,
        "codes": codes,
        "warnings": warnings,
        "breakdown": {
            "oversized_position": {
                "planned_lot": planned_lot,
                "actual_lot": actual_lot,
                "threshold_multiplier": threshold,
                "triggered": triggered,
            }
        },
    }


def _resolve_direction(trade: dict[str, object]) -> str:
    """Extract a canonical direction ('buy' / 'sell' / '') from a trade dict."""
    for key in ("direction", "selected_scenario", "side", "type"):
        raw = trade.get(key)
        if raw is None:
            continue
        v = str(raw).strip().lower()
        if v in ("buy", "long"):
            return "buy"
        if v in ("sell", "short"):
            return "sell"
    return ""


def detect_moved_stop_loss(
    trade: dict[str, object],
    settings: dict[str, object] | None = None,
) -> dict[str, object]:
    """Detect whether SL was moved further (increasing risk) vs the plan.

    - BUY: actual_sl < planned_sl  → moved further down (wider risk).
    - SELL: actual_sl > planned_sl → moved further up (wider risk).
    """
    direction = _resolve_direction(trade)
    planned_sl = safe_float(trade.get("planned_sl") or trade.get("stop_loss"))
    actual_sl = safe_float(trade.get("actual_sl"))

    triggered = False
    tags: list[str] = []
    codes: list[str] = []

    if direction and planned_sl > 0 and actual_sl > 0:
        if direction == "buy" and actual_sl < planned_sl:
            triggered = True
        elif direction == "sell" and actual_sl > planned_sl:
            triggered = True

    if triggered:
        tags.append("moved_stop_loss")
        codes.append(MISTAKE_MOVED_STOP_LOSS)

    return {
        "triggered": triggered,
        "tags": tags,
        "codes": codes,
        "warnings": [],
        "breakdown": {
            "moved_stop_loss": {
                "direction": direction,
                "planned_sl": planned_sl,
                "actual_sl": actual_sl,
                "triggered": triggered,
            }
        },
    }


def is_loss_trade(trade: dict[str, object]) -> bool:
    """Determine whether a trade is a loss from available result fields."""
    if not isinstance(trade, dict):
        return False
    result_r = safe_float(trade.get("result_r"), default=None)
    if result_r is not None and result_r != 0.0:
        return result_r < 0
    result_pct = safe_float(trade.get("result_pct"), default=None)
    if result_pct is not None and result_pct != 0.0:
        return result_pct < 0
    label = str(trade.get("result") or trade.get("result_label") or "").strip().lower()
    if label in ("loss", "thua", "lỗ"):
        return True
    return False


def _current_open_time(trade: dict[str, object]) -> datetime | None:
    """Extract the open / entry time of the current trade."""
    for key in ("opened_at", "entry_time", "timestamp", "open_time", "created_at"):
        dt = safe_datetime(trade.get(key))
        if dt is not None:
            return dt
    return None


def find_previous_closed_trade(
    current_trade: dict[str, object],
    previous_trades: list[dict[str, object]] | None,
) -> dict[str, object] | None:
    """Find the most recent closed trade that closed before *current_trade* was opened."""
    if not isinstance(previous_trades, list):
        return None
    open_time = _current_open_time(current_trade)
    if open_time is None:
        return None

    best: dict[str, object] | None = None
    best_time: datetime | None = None
    for trade in previous_trades:
        if not isinstance(trade, dict):
            continue
        closed_at = safe_datetime(trade.get("closed_at"))
        if closed_at is None:
            continue
        if closed_at >= open_time:
            continue
        if best_time is None or closed_at > best_time:
            best_time = closed_at
            best = trade
    return best


def detect_revenge_trade_time(
    trade: dict[str, object],
    previous_trades: list[dict[str, object]] | None = None,
    settings: dict[str, object] | None = None,
) -> dict[str, object]:
    """Detect revenge trade warning based on short time after a loss."""
    cfg = dict(DEFAULT_SETTINGS)
    if settings:
        cfg.update(settings)

    triggered = False
    tags: list[str] = []
    codes: list[str] = []

    prev = find_previous_closed_trade(trade, previous_trades)
    if prev is not None and is_loss_trade(prev):
        open_time = _current_open_time(trade)
        prev_close = safe_datetime(prev.get("closed_at"))
        if open_time is not None and prev_close is not None:
            minutes = float(cfg.get("revenge_trade_minutes", 5))
            if open_time - prev_close <= timedelta(minutes=minutes):
                triggered = True
                tags.append("revenge_trade_warning")
                codes.append(MISTAKE_REVENGE_TRADE_WARNING)

    return {
        "triggered": triggered,
        "tags": tags,
        "codes": codes,
        "warnings": [],
        "breakdown": {
            "revenge_trade_time": {
                "triggered": triggered,
                "previous_loss": prev is not None and is_loss_trade(prev) if prev else False,
            }
        },
    }


def _resolve_lot(trade: dict[str, object]) -> float:
    """Extract the most specific lot size from a trade dict.

    Tries in order: actual_lot, planned_lot, suggested_lot.
    Returns 0.0 when none are available.
    """
    for key in ("actual_lot", "planned_lot", "suggested_lot"):
        val = safe_float(trade.get(key))
        if val > 0:
            return val
    return 0.0


def detect_revenge_trade_lot(
    trade: dict[str, object],
    previous_trades: list[dict[str, object]] | None = None,
    settings: dict[str, object] | None = None,
) -> dict[str, object]:
    """Detect revenge trade warning based on lot increase after a loss."""
    cfg = dict(DEFAULT_SETTINGS)
    if settings:
        cfg.update(settings)

    triggered = False
    tags: list[str] = []
    codes: list[str] = []
    prev_lot = 0.0
    curr_lot = 0.0

    prev = find_previous_closed_trade(trade, previous_trades)
    if prev is not None and is_loss_trade(prev):
        prev_lot = _resolve_lot(prev)
        curr_lot = _resolve_lot(trade)
        multiplier = float(cfg.get("revenge_lot_multiplier", 1.5))
        if prev_lot > 0 and curr_lot > prev_lot * multiplier:
            triggered = True
            tags.append("revenge_trade_warning")
            codes.append(MISTAKE_REVENGE_TRADE_WARNING)

    return {
        "triggered": triggered,
        "tags": tags,
        "codes": codes,
        "warnings": [],
        "breakdown": {
            "revenge_trade_lot": {
                "previous_lot": prev_lot,
                "current_lot": curr_lot,
                "threshold_multiplier": float(cfg.get("revenge_lot_multiplier", 1.5)),
                "triggered": triggered,
            }
        },
    }


def detect_revenge_trade_confirmed(
    trade: dict[str, object],
    previous_trades: list[dict[str, object]] | None = None,
    settings: dict[str, object] | None = None,
) -> dict[str, object]:
    """Detect confirmed revenge trade: both short time AND increased lot after a loss."""
    cfg = dict(DEFAULT_SETTINGS)
    if settings:
        cfg.update(settings)

    time_condition = False
    lot_condition = False
    triggered = False
    tags: list[str] = []
    codes: list[str] = []

    prev = find_previous_closed_trade(trade, previous_trades)
    if prev is not None and is_loss_trade(prev):
        # Time condition
        open_time = _current_open_time(trade)
        prev_close = safe_datetime(prev.get("closed_at"))
        if open_time is not None and prev_close is not None:
            minutes = float(cfg.get("revenge_trade_minutes", 5))
            if open_time - prev_close <= timedelta(minutes=minutes):
                time_condition = True

        # Lot condition
        prev_lot = _resolve_lot(prev)
        curr_lot = _resolve_lot(trade)
        multiplier = float(cfg.get("revenge_lot_multiplier", 1.5))
        if prev_lot > 0 and curr_lot > prev_lot * multiplier:
            lot_condition = True

        if time_condition and lot_condition:
            triggered = True
            tags.append("revenge_trade_confirmed")
            codes.append(MISTAKE_REVENGE_TRADE_CONFIRMED)

    return {
        "triggered": triggered,
        "tags": tags,
        "codes": codes,
        "warnings": [],
        "breakdown": {
            "revenge_trade_confirmed": {
                "time_condition": time_condition,
                "lot_condition": lot_condition,
                "triggered": triggered,
            }
        },
    }


def _has_real_entry(trade: dict[str, object]) -> bool:
    """Determine whether the trader actually entered this trade."""
    if not isinstance(trade, dict):
        return False
    user_action = str(trade.get("user_action") or trade.get("action") or "").strip().lower()
    if user_action in {"opened", "open", "entered", "trade_opened", "vào lệnh", "da_vao_lenh"}:
        return True
    if safe_float(trade.get("actual_entry")) > 0:
        return True
    if safe_datetime(trade.get("opened_at")) is not None:
        return True
    order_status = str(trade.get("order_status") or "").strip().lower()
    if order_status in {"filled", "executed", "opened"}:
        return True
    return False


def detect_ignored_m15(
    trade: dict[str, object],
    settings: dict[str, object] | None = None,
) -> dict[str, object]:
    """Detect whether trader entered despite M15 not confirming."""
    triggered = False
    tags: list[str] = []
    codes: list[str] = []
    m15_quality = None
    entry_status = None
    has_entry = _has_real_entry(trade)

    if has_entry:
        m15_quality = str(trade.get("m15_quality") or "").strip().lower()
        entry_status = str(trade.get("entry_status") or "").strip().lower()

        if m15_quality == "none":
            triggered = True
        elif entry_status in ("watch_zone", "waiting_confirmation"):
            triggered = True

        if m15_quality == "strict" or entry_status == "confirmed_entry":
            triggered = False

    if triggered:
        tags.append("ignored_m15")
        codes.append(MISTAKE_IGNORED_M15)

    return {
        "triggered": triggered,
        "tags": tags,
        "codes": codes,
        "warnings": [],
        "breakdown": {
            "ignored_m15": {
                "m15_quality": m15_quality or "",
                "entry_status": entry_status or "",
                "has_real_entry": has_entry,
                "triggered": triggered,
            }
        },
    }


def detect_ignored_news(
    trade: dict[str, object],
    settings: dict[str, object] | None = None,
) -> dict[str, object]:
    """Detect whether trader entered despite high-impact news warnings/blocks."""
    triggered = False
    tags: list[str] = []
    codes: list[str] = []
    has_entry = _has_real_entry(trade)
    news_risk = False

    if has_entry:
        # Check boolean flags
        for key in ("high_impact_news_within_30m", "high_impact_event_within_30m"):
            if truthy(trade.get(key)):
                news_risk = True
                break

        # Check news_risk string
        news_risk_val = str(trade.get("news_risk") or "").strip().lower()
        if news_risk_val in ("high", "blocked", "nearby", "red"):
            news_risk = True

        # Check codes in block_codes / warning_codes / gate_result
        for list_key in ("block_codes", "warning_codes"):
            codes_val = trade.get(list_key)
            if isinstance(codes_val, list):
                for c in codes_val:
                    if isinstance(c, str) and "HIGH_IMPACT_NEWS" in c.upper():
                        news_risk = True
                        break

        gate = trade.get("gate_result")
        if isinstance(gate, dict):
            for list_key in ("block_codes", "warning_codes"):
                codes_val = gate.get(list_key)
                if isinstance(codes_val, list):
                    for c in codes_val:
                        if isinstance(c, str) and "HIGH_IMPACT_NEWS" in c.upper():
                            news_risk = True
                            break

        if news_risk:
            triggered = True
            tags.append("ignored_news")
            codes.append(MISTAKE_IGNORED_NEWS)

    return {
        "triggered": triggered,
        "tags": tags,
        "codes": codes,
        "warnings": [],
        "breakdown": {
            "ignored_news": {
                "has_real_entry": has_entry,
                "news_risk_detected": news_risk,
                "triggered": triggered,
            }
        },
    }


def detect_chased_price(
    trade: dict[str, object],
    settings: dict[str, object] | None = None,
) -> dict[str, object]:
    """Detect whether actual entry price is worse than planned beyond tolerance."""
    cfg = dict(DEFAULT_SETTINGS)
    if settings:
        cfg.update(settings)

    triggered = False
    tags: list[str] = []
    codes: list[str] = []
    direction = _resolve_direction(trade)
    tolerance_pct = float(cfg.get("chased_price_tolerance_pct", 0.10))
    planned_entry = 0.0
    actual_entry = 0.0

    if direction:
        for key in ("planned_entry", "entry", "suggested_entry"):
            planned_entry = safe_float(trade.get(key))
            if planned_entry > 0:
                break
        actual_entry = safe_float(trade.get("actual_entry"))

        if planned_entry > 0 and actual_entry > 0:
            if direction == "buy":
                limit = planned_entry * (1 + tolerance_pct / 100)
                if actual_entry > limit:
                    triggered = True
            else:  # sell
                limit = planned_entry * (1 - tolerance_pct / 100)
                if actual_entry < limit:
                    triggered = True

    if triggered:
        tags.append("chased_price")
        codes.append(MISTAKE_CHASED_PRICE)

    return {
        "triggered": triggered,
        "tags": tags,
        "codes": codes,
        "warnings": [],
        "breakdown": {
            "chased_price": {
                "direction": direction,
                "planned_entry": planned_entry,
                "actual_entry": actual_entry,
                "tolerance_pct": tolerance_pct,
                "triggered": triggered,
            }
        },
    }


def detect_entered_too_early(
    trade: dict[str, object],
    settings: dict[str, object] | None = None,
) -> dict[str, object]:
    """Detect whether trader entered before entry_status allowed or price wasn't in zone."""
    triggered = False
    tags: list[str] = []
    codes: list[str] = []
    has_entry = _has_real_entry(trade)
    entry_status = ""
    in_zone = None

    if has_entry:
        entry_status = str(trade.get("entry_status") or "").strip().lower()

        if entry_status in ("watch_zone", "waiting_confirmation"):
            triggered = True
        elif entry_status == "confirmed_entry":
            triggered = False
        else:
            # Check zone flags
            for key in ("in_entry_zone", "price_in_entry_zone"):
                val = trade.get(key)
                if val is not None:
                    if isinstance(val, bool):
                        in_zone = val
                    else:
                        in_zone = truthy(val)
                    break

            if in_zone is False:
                triggered = True

    if triggered:
        tags.append("entered_too_early")
        codes.append(MISTAKE_ENTERED_TOO_EARLY)

    return {
        "triggered": triggered,
        "tags": tags,
        "codes": codes,
        "warnings": [],
        "breakdown": {
            "entered_too_early": {
                "has_real_entry": has_entry,
                "entry_status": entry_status,
                "in_entry_zone": in_zone,
                "triggered": triggered,
            }
        },
    }


_VALID_EXIT_REASONS = frozenset({
    "news_exit", "manual_risk_reduce", "breakeven", "system_exit",
    "tp_hit", "sl_hit", "take_profit", "stop_loss",
})
_EXPLICIT_EARLY_EXIT = frozenset({
    "closed_early", "manual_close", "chot_non", "chốt non",
})


def _parse_risk_reward(value: object) -> float:
    """Parse a '1:2.0' style R:R string into the reward part (2.0)."""
    text = str(value or "")
    if ":" in text:
        try:
            return float(text.split(":", 1)[1])
        except (ValueError, IndexError):
            pass
    try:
        return float(text)
    except (ValueError, TypeError):
        pass
    return 0.0


def detect_closed_too_early(
    trade: dict[str, object],
    settings: dict[str, object] | None = None,
) -> dict[str, object]:
    """Detect whether trader closed too early — positive but small R vs planned R:R."""
    cfg = dict(DEFAULT_SETTINGS)
    if settings:
        cfg.update(settings)

    triggered = False
    tags: list[str] = []
    codes: list[str] = []
    result_r = 0.0
    planned_rr = 0.0
    exit_reason = ""

    # Only check closed trades
    has_closed = (
        safe_datetime(trade.get("closed_at")) is not None
        or safe_float(trade.get("actual_exit")) > 0
    )
    if not has_closed:
        return {
            "triggered": False, "tags": [], "codes": [], "warnings": [],
            "breakdown": {"closed_too_early": {
                "result_r": 0.0, "risk_reward": 0.0, "exit_reason": "", "triggered": False,
            }},
        }

    result_r = safe_float(trade.get("result_r"))
    planned_rr = _parse_risk_reward(trade.get("risk_reward"))
    exit_reason = str(trade.get("exit_reason") or "").strip().lower()

    if planned_rr <= 0:
        planned_rr = float(cfg.get("closed_too_early_min_planned_r_multiple", 1.0))

    threshold = float(cfg.get("closed_too_early_actual_r_threshold", 0.5))

    if result_r > 0 and planned_rr >= 1.0 and result_r < threshold:
        if exit_reason in _VALID_EXIT_REASONS:
            triggered = False
        else:
            triggered = True

    if triggered:
        tags.append("closed_too_early")
        codes.append(MISTAKE_CLOSED_TOO_EARLY)

    return {
        "triggered": triggered,
        "tags": tags,
        "codes": codes,
        "warnings": [],
        "breakdown": {
            "closed_too_early": {
                "result_r": result_r,
                "risk_reward": planned_rr,
                "exit_reason": exit_reason,
                "triggered": triggered,
            }
        },
    }


def detect_trade_mistakes(
    trade: dict[str, object] | None = None,
    previous_trades: list[dict[str, object]] | None = None,
    settings: dict[str, object] | None = None,
) -> dict[str, Any]:
    """Detect trading mistakes from a trade dict and optional previous trades.

    Parameters
    ----------
    trade : dict | None
        A single trade journal entry (or planned-trade payload).
    previous_trades : list[dict] | None
        Recently closed trades for context (revenge detection, etc.).
    settings : dict | None
        Optional detector settings (thresholds, timeouts, etc.).

    Returns
    -------
    dict
        Structured result with keys: auto_mistake_tags, manual_mistake_tags,
        mistake_codes, warning_codes, reason_codes, score_breakdown, reason.
    """
    if not isinstance(trade, dict):
        result = default_mistake_detection_result("no_trade_data")
        result["warning_codes"] = [MISTAKE_DATA_INCOMPLETE]
        result["reason_codes"] = []
        result["reason"] = "Không có dữ liệu giao dịch để phát hiện lỗi hành vi."
        result["summary"] = "Không đủ dữ liệu để phát hiện lỗi hành vi."
        return result

    result = default_mistake_detection_result()
    cfg = dict(DEFAULT_SETTINGS)
    if settings:
        cfg.update(settings)

    # ---- oversized position ----
    oversized = detect_oversized_position(trade, cfg)
    for tag in oversized["tags"]:
        add_unique(result["auto_mistake_tags"], tag)
    for code in oversized["codes"]:
        add_unique(result["mistake_codes"], code)
    result["score_breakdown"].update(oversized["breakdown"])

    # ---- moved stop loss ----
    moved_sl = detect_moved_stop_loss(trade, cfg)
    for tag in moved_sl["tags"]:
        add_unique(result["auto_mistake_tags"], tag)
    for code in moved_sl["codes"]:
        add_unique(result["mistake_codes"], code)
    result["score_breakdown"].update(moved_sl["breakdown"])

    # ---- revenge trade time ----
    revenge_time = detect_revenge_trade_time(trade, previous_trades, cfg)
    for tag in revenge_time["tags"]:
        add_unique(result["auto_mistake_tags"], tag)
    for code in revenge_time["codes"]:
        add_unique(result["mistake_codes"], code)
    result["score_breakdown"].update(revenge_time["breakdown"])

    # ---- revenge trade lot ----
    revenge_lot = detect_revenge_trade_lot(trade, previous_trades, cfg)
    for tag in revenge_lot["tags"]:
        add_unique(result["auto_mistake_tags"], tag)
    for code in revenge_lot["codes"]:
        add_unique(result["mistake_codes"], code)
    result["score_breakdown"].update(revenge_lot["breakdown"])

    # ---- revenge trade confirmed (time + lot) ----
    revenge_confirmed = detect_revenge_trade_confirmed(trade, previous_trades, cfg)
    for tag in revenge_confirmed["tags"]:
        add_unique(result["auto_mistake_tags"], tag)
    for code in revenge_confirmed["codes"]:
        add_unique(result["mistake_codes"], code)
    result["score_breakdown"].update(revenge_confirmed["breakdown"])

    # ---- ignored M15 ----
    ignored_m15 = detect_ignored_m15(trade, cfg)
    for tag in ignored_m15["tags"]:
        add_unique(result["auto_mistake_tags"], tag)
    for code in ignored_m15["codes"]:
        add_unique(result["mistake_codes"], code)
    result["score_breakdown"].update(ignored_m15["breakdown"])

    # ---- ignored news ----
    ignored_news = detect_ignored_news(trade, cfg)
    for tag in ignored_news["tags"]:
        add_unique(result["auto_mistake_tags"], tag)
    for code in ignored_news["codes"]:
        add_unique(result["mistake_codes"], code)
    result["score_breakdown"].update(ignored_news["breakdown"])

    # ---- chased price ----
    chased = detect_chased_price(trade, cfg)
    for tag in chased["tags"]:
        add_unique(result["auto_mistake_tags"], tag)
    for code in chased["codes"]:
        add_unique(result["mistake_codes"], code)
    result["score_breakdown"].update(chased["breakdown"])

    # ---- entered too early ----
    too_early = detect_entered_too_early(trade, cfg)
    for tag in too_early["tags"]:
        add_unique(result["auto_mistake_tags"], tag)
    for code in too_early["codes"]:
        add_unique(result["mistake_codes"], code)
    result["score_breakdown"].update(too_early["breakdown"])

    # ---- closed too early ----
    closed_early = detect_closed_too_early(trade, cfg)
    for tag in closed_early["tags"]:
        add_unique(result["auto_mistake_tags"], tag)
    for code in closed_early["codes"]:
        add_unique(result["mistake_codes"], code)
    result["score_breakdown"].update(closed_early["breakdown"])

    # Update reason if any mistakes found
    if result["auto_mistake_tags"]:
        result["reason_codes"] = result["mistake_codes"][:]
        result["reason"] = f"Phát hiện lỗi hành vi: {', '.join(result['auto_mistake_tags'])}."

    # ---- merge manual tags from trade ----
    raw_manual: list[str] = []
    for key in ("manual_mistake_tags", "mistake_tags", "user_mistake_tags"):
        raw_manual = normalize_tags(trade.get(key))
        if raw_manual:
            break
    result["manual_mistake_tags"] = raw_manual

    # ---- all_mistake_tags: auto + manual, no duplicates ----
    all_tags: list[str] = list(result["auto_mistake_tags"])
    for tag in raw_manual:
        add_unique(all_tags, tag)
    result["all_mistake_tags"] = all_tags

    # ---- summary ----
    result["summary"] = build_mistake_summary(result)

    return result


_TAG_LABELS_VI: dict[str, str] = {
    "oversized_position": "vào khối lượng lớn hơn kế hoạch",
    "moved_stop_loss": "dời stop loss làm tăng rủi ro",
    "revenge_trade_warning": "có dấu hiệu revenge trade",
    "revenge_trade_confirmed": "revenge trade rõ ràng",
    "ignored_m15": "bỏ qua xác nhận M15",
    "ignored_news": "bỏ qua cảnh báo tin tức",
    "chased_price": "đuổi giá",
    "entered_too_early": "vào lệnh quá sớm",
    "closed_too_early": "chốt lệnh quá sớm",
}


def build_mistake_summary(result: dict[str, object]) -> str:
    """Build a short Vietnamese summary from a detector result dict."""
    auto_tags: list[str] = result.get("auto_mistake_tags", []) or []
    manual_tags: list[str] = result.get("manual_mistake_tags", []) or []

    if not auto_tags and not manual_tags:
        return "Không phát hiện lỗi hành vi rõ ràng."

    parts: list[str] = []
    if auto_tags:
        translated = [_TAG_LABELS_VI.get(t, t) for t in auto_tags]
        parts.append("Phát hiện lỗi: " + ", ".join(translated) + ".")
    if manual_tags:
        parts.append("Có tag thủ công từ journal.")
    return " ".join(parts)


def apply_detected_mistakes_to_trade(
    trade: dict[str, object],
    detection_result: dict[str, object],
) -> dict[str, object]:
    """Apply detector output tags to a trade dict copy.

    Returns a shallow copy of *trade* with auto_mistake_tags,
    manual_mistake_tags, all_mistake_tags, and mistake_codes
    injected from *detection_result*.  Does NOT mutate the original trade.
    """
    result = dict(trade)
    result["auto_mistake_tags"] = list(detection_result.get("auto_mistake_tags", []) or [])
    result["manual_mistake_tags"] = list(detection_result.get("manual_mistake_tags", []) or [])
    result["all_mistake_tags"] = list(detection_result.get("all_mistake_tags", []) or [])
    result["mistake_codes"] = list(detection_result.get("mistake_codes", []) or [])
    return result
