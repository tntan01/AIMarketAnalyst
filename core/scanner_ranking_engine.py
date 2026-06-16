"""Scanner ranking engine — compute opportunity scores and group scanner rows.

Phase 15: this module ranks scanner rows by combining final_score with
proximity, readiness, R:R, spread and news factors into an
``opportunity_score``, then assigns each row to a ``scanner_group``.

Design principles
-----------------
* **Does not compute signal_score.**  That stays in :mod:`core.signal_engine`.
* **Does not compute final_score.**  That stays in :mod:`core.final_score_engine`.
* **Does not make trade decisions.**  That stays in :mod:`core.decision_engine`.
* **Does not call MT5, AI, database, network, services, or UI.**
* **Does not change the decision engine.**
* **Safe on dirty data.**  Missing or invalid inputs fall back to defaults.

Scanner groups
--------------
* ``ready_now`` — entry confirmed, gate allows, score sufficient.
* ``waiting_confirmation`` — interesting setup waiting for trigger.
* ``watch_zone`` — worth monitoring but not yet actionable.
* ``blocked`` — gate or data quality blocks consideration.

Public API
----------
* ``calculate_opportunity_score(row)`` — compute opportunity from a scanner row.
* ``calculate_scanner_ranking(rows)`` — rank and group a list of rows.
* ``default_opportunity_result()`` — safe fallback.
"""

from __future__ import annotations

from typing import Any

from core.reason_codes import (
    SCANNER_OPPORTUNITY_SCORE_OK,
    SCANNER_OPPORTUNITY_DATA_INCOMPLETE,
    SCANNER_RANKING_READY_NOW,
    SCANNER_RANKING_WAITING_CONFIRMATION,
    SCANNER_RANKING_WATCH_ZONE,
    SCANNER_RANKING_BLOCKED,
    SCANNER_PROXIMITY_IN_ZONE,
    SCANNER_PROXIMITY_NEAR_ZONE,
    SCANNER_PROXIMITY_FAR,
    SCANNER_RR_STRONG,
    SCANNER_RR_WEAK,
    SCANNER_NEWS_PENALTY,
    SCANNER_SPREAD_PENALTY,
)
from core.normalization import normalize_choice
from core.safe_types import clamp_score as _shared_clamp_score
from core.safe_types import safe_float as _shared_safe_float

# ---------------------------------------------------------------------------
# Scanner-group constants
# ---------------------------------------------------------------------------

READY_NOW = "ready_now"
WAITING_CONFIRMATION = "waiting_confirmation"
WATCH_ZONE = "watch_zone"
BLOCKED = "blocked"

VALID_SCANNER_GROUPS = frozenset({
    READY_NOW,
    WAITING_CONFIRMATION,
    WATCH_ZONE,
    BLOCKED,
})

# ---------------------------------------------------------------------------
# Group labels
# ---------------------------------------------------------------------------

SCANNER_GROUP_LABELS: dict[str, str] = {
    READY_NOW: "Sẵn sàng ngay",
    WAITING_CONFIRMATION: "Chờ xác nhận",
    WATCH_ZONE: "Theo dõi",
    BLOCKED: "Bị chặn",
}

SCANNER_GROUP_DISPLAY_ACTIONS: dict[str, str] = {
    READY_NOW: "ready",
    WAITING_CONFIRMATION: "wait",
    WATCH_ZONE: "watch",
    BLOCKED: "skip",
}

# ---------------------------------------------------------------------------
# Opportunity-score weights
# ---------------------------------------------------------------------------

DEFAULT_OPPORTUNITY_WEIGHTS: dict[str, float] = {
    "final_score": 1.0,
    "proximity_bonus": 8.0,
    "readiness_bonus": 10.0,
    "rr_bonus": 5.0,
    "spread_penalty": 8.0,
    "news_penalty": 10.0,
}

# Proximity thresholds (in ATR units)
_PROXIMITY_IN_ZONE_ATR = 0.0
_PROXIMITY_NEAR_ATR = 1.0

# R:R thresholds
_RR_STRONG = 2.0
_RR_WEAK = 1.3

# ---------------------------------------------------------------------------
# Group mapping from decision-engine decisions
# ---------------------------------------------------------------------------

_DECISION_TO_SCANNER_GROUP: dict[str, str] = {
    "READY_TO_TRADE": READY_NOW,
    "WAITING_CONFIRMATION": WAITING_CONFIRMATION,
    "AGGRESSIVE_SETUP": WAITING_CONFIRMATION,
    "WATCH_ONLY": WATCH_ZONE,
    "TRADE_BLOCKED": BLOCKED,
    "STAND_ASIDE": WATCH_ZONE,
}

# ---------------------------------------------------------------------------
# Reason-code mapping per group
# ---------------------------------------------------------------------------

_GROUP_REASON_CODES: dict[str, str] = {
    READY_NOW: SCANNER_RANKING_READY_NOW,
    WAITING_CONFIRMATION: SCANNER_RANKING_WAITING_CONFIRMATION,
    WATCH_ZONE: SCANNER_RANKING_WATCH_ZONE,
    BLOCKED: SCANNER_RANKING_BLOCKED,
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def clamp_score(
    value: object, default: int = 0, minimum: int = 0, maximum: int = 100
) -> int:
    """Safely read a score value, clamping to [*minimum*, *maximum*].

    - None, "", "abc", NaN, ±Inf → *default* (already clamped).
    - Never raises.
    """
    return _shared_clamp_score(value, minimum, maximum, default=default)


def safe_float(value: object, default: float = 0.0) -> float:
    """Safely convert a value to float.

    - None, "", "abc", NaN, ±Inf → *default*.
    - Never raises.
    """
    result = _shared_safe_float(value, default=default)
    return default if result is None else result


def parse_risk_reward(value: object) -> float:
    """Parse a risk/reward ratio string.

    - ``"1:1.8"`` → 1.8
    - ``"1:2"`` → 2.0
    - ``"2.5"`` → 2.5
    - None or dirty → 0.0
    - Never raises.
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        f = float(value)
        return max(f, 0.0) if f == f else 0.0
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return 0.0
        if ":" in s:
            parts = s.split(":", 1)
            try:
                risk = float(parts[0].strip())
                reward = float(parts[1].strip())
                if risk == 0:
                    return 0.0
                return max(reward / risk, 0.0)
            except (ValueError, OverflowError):
                pass
        try:
            f = float(s)
            return max(f, 0.0) if f == f else 0.0
        except (ValueError, OverflowError):
            pass
    return 0.0


_PROXIMITY_ALIASES: dict[str, str] = {
    "in_zone": "in_zone",
    "in": "in_zone",
    "inside": "in_zone",
    "near_zone": "near_zone",
    "near": "near_zone",
    "far": "far",
    "far_zone": "far",
}


def normalize_price_vs_zone(value: object) -> str:
    """Normalise a price-vs-zone string or boolean.

    Returns one of ``"in_zone"``, ``"near_zone"``, ``"far"``, or ``"unknown"``.
    """
    if isinstance(value, bool):
        return "in_zone" if value else "far"
    if not isinstance(value, str):
        return "unknown"
    cleaned = value.strip().lower()
    if not cleaned:
        return "unknown"
    return _PROXIMITY_ALIASES.get(cleaned, "unknown")


_ENTRY_STATUS_SET = frozenset({
    "confirmed_entry", "waiting_confirmation", "watch_zone",
    "invalidated", "no_setup", "data_unavailable",
})


def normalize_entry_status(value: object) -> str:
    """Normalise an entry-status string to a canonical value."""
    return normalize_choice(value, _ENTRY_STATUS_SET, default="unknown") or "unknown"


_DECISION_ALIASES: dict[str, str] = {
    "ready": "READY_TO_TRADE",
    "ready_to_trade": "READY_TO_TRADE",
    "watch": "WATCH_ONLY",
    "watch_only": "WATCH_ONLY",
    "wait": "WAITING_CONFIRMATION",
    "waiting_confirmation": "WAITING_CONFIRMATION",
    "wait_for_confirmation": "WAITING_CONFIRMATION",
    "aggressive_setup": "AGGRESSIVE_SETUP",
    "trade_blocked": "TRADE_BLOCKED",
    "blocked": "TRADE_BLOCKED",
    "skip": "TRADE_BLOCKED",
    "stand_aside": "STAND_ASIDE",
}


def normalize_decision(value: object) -> str:
    """Normalise a decision string to an uppercase decision-engine constant.

    Accepts both engine constants and legacy action strings.
    Unknown → ``""``.
    """
    return normalize_choice(
        value,
        frozenset({
            "READY_TO_TRADE", "WAITING_CONFIRMATION", "AGGRESSIVE_SETUP",
            "WATCH_ONLY", "TRADE_BLOCKED", "STAND_ASIDE",
        }),
        aliases=_DECISION_ALIASES,
        default="",
        case="upper",
    ) or ""


def merge_unique_codes(*groups: object) -> list[str]:
    """Merge multiple code lists, deduplicating while preserving order."""
    seen: set[str] = set()
    result: list[str] = []
    for group in groups:
        if group is None:
            continue
        if not isinstance(group, (list, tuple, set)):
            continue
        for code in group:
            if code is None:
                continue
            s = str(code).strip()
            if not s:
                continue
            if s not in seen:
                seen.add(s)
                result.append(s)
    return result

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_scanner_group(
    *,
    decision: object = None,
    scanner_action: object = None,
    trade_permission: object = None,
    entry_status: object = None,
    ready_to_trade: object = None,
) -> str:
    """Assign a scanner row to a group based on decision, action, and entry.

    Priority order:
    1. Hard block: TRADE_BLOCKED decision or trade_permission blocked → BLOCKED.
    2. Decision engine (wins over legacy scanner_action):
       READY_TO_TRADE → READY_NOW.
       AGGRESSIVE_SETUP / WAITING_CONFIRMATION → WAITING_CONFIRMATION.
       WATCH_ONLY / STAND_ASIDE → WATCH_ZONE.
    3. Legacy scanner_action (only when no decision engine override):
       "ready" + ready_to_trade truthy → READY_NOW.
       "wait" / "wait_for_confirmation" → WAITING_CONFIRMATION.
       "watch" → WATCH_ZONE.
    4. Entry status:
       waiting_confirmation → WAITING_CONFIRMATION.
       watch_zone → WATCH_ZONE.
       invalidated / no_setup / data_unavailable → BLOCKED.
    5. Legacy "skip" (no decision or entry override) → BLOCKED.
    6. Fallback → WATCH_ZONE.

    Never raises.
    """
    norm_decision = normalize_decision(decision)
    norm_entry = normalize_entry_status(entry_status)
    norm_action = str(scanner_action or "").strip().lower()
    tp_blocked = False
    if isinstance(trade_permission, dict):
        tp_blocked = str(trade_permission.get("status", "")).strip().lower() == "blocked"
    elif isinstance(trade_permission, str):
        tp_blocked = trade_permission.strip().lower() == "blocked"

    # ---- 1. Hard block (gate level) ----
    if norm_decision == "TRADE_BLOCKED":
        return BLOCKED
    if tp_blocked:
        return BLOCKED

    # ---- 2. Decision engine (wins over legacy scanner_action) ----
    if norm_decision == "READY_TO_TRADE":
        return READY_NOW
    if norm_decision in ("WAITING_CONFIRMATION", "AGGRESSIVE_SETUP"):
        return WAITING_CONFIRMATION
    if norm_decision in ("WATCH_ONLY", "STAND_ASIDE"):
        return WATCH_ZONE

    # ---- 3. Legacy fallback (rows without decision engine result) ----
    if norm_action == "ready" and _truthy(ready_to_trade):
        return READY_NOW
    if norm_action in ("wait", "wait_for_confirmation"):
        return WAITING_CONFIRMATION
    if norm_action == "watch":
        return WATCH_ZONE

    # ---- 4. Entry status ----
    if norm_entry == "waiting_confirmation":
        return WAITING_CONFIRMATION
    if norm_entry == "watch_zone":
        return WATCH_ZONE
    if norm_entry in ("invalidated", "no_setup", "data_unavailable"):
        return BLOCKED

    # ---- 5. Legacy skip / stand_aside ----
    if norm_action in ("skip", "stand_aside"):
        return BLOCKED

    # ---- 6. Fallback ----
    return WATCH_ZONE


def _truthy(value: object) -> bool:
    """Interpret a loosely-typed value as boolean."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        s = value.strip().lower()
        return s in ("true", "yes", "1", "có", "co")
    return False


def default_opportunity_result(reason: str = "opportunity_not_calculated") -> dict[str, Any]:
    """Return a safe default result when opportunity cannot be computed."""
    return {
        "opportunity_score": 0,
        "scanner_group": WATCH_ZONE,
        "reason_codes": [],
        "warning_codes": [SCANNER_OPPORTUNITY_DATA_INCOMPLETE],
        "penalty_codes": [],
        "score_breakdown": {},
        "reason": reason,
    }


def map_decision_to_scanner_group(decision: str | None) -> str:
    """Map a decision-engine decision to a scanner group.

    - ``READY_TO_TRADE`` → ``READY_NOW``
    - ``WAITING_CONFIRMATION`` / ``AGGRESSIVE_SETUP`` → ``WAITING_CONFIRMATION``
    - ``WATCH_ONLY`` / ``STAND_ASIDE`` → ``WATCH_ZONE``
    - ``TRADE_BLOCKED`` → ``BLOCKED``
    - Unknown → ``WATCH_ZONE``
    """
    if not isinstance(decision, str):
        return WATCH_ZONE
    return _DECISION_TO_SCANNER_GROUP.get(decision.strip(), WATCH_ZONE)


def calculate_opportunity_score(
    row: dict[str, Any] | None,
    *,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Compute an opportunity_score for a scanner row.

    Formula::

        opportunity = final_score
                    + proximity_bonus  (+8 in_zone, +4 near, 0 far)
                    + readiness_bonus  (+10 ready, +3 waiting, 0 watch)
                    + rr_bonus         (+5 rr≥2.0, +3 rr≥1.5, +1 rr≥1.3)
                    - spread_penalty   (-8 abnormal, -4 caution)
                    - news_penalty     (-10 high-impact 30m, -5 news in 3h)

    BLOCKED rows are capped at 20.  Result is clamped to 0–120.
    Never mutates *row*.  Never raises.
    """
    if not isinstance(row, dict):
        return default_opportunity_result("row_not_a_dict")

    w = weights or DEFAULT_OPPORTUNITY_WEIGHTS

    # ---- base score ----
    base = clamp_score(row.get("final_score") or row.get("best_score"), 0)

    # ---- scanner group ----
    decision_val = row.get("scanner_decision") or row.get("decision")
    group = classify_scanner_group(
        decision=decision_val,
        scanner_action=row.get("scanner_action"),
        trade_permission=row.get("trade_permission"),
        entry_status=row.get("entry_status"),
        ready_to_trade=row.get("ready_to_trade"),
    )
    journal_feedback = row.get("journal_feedback") if isinstance(row.get("journal_feedback"), dict) else {}
    journal_cap = str(journal_feedback.get("decision_cap") or "").strip()
    if journal_cap == "TRADE_BLOCKED":
        group = BLOCKED
    elif journal_cap == "WATCH_ONLY" and group in {READY_NOW, WAITING_CONFIRMATION}:
        group = WATCH_ZONE
    elif journal_cap == "WAITING_CONFIRMATION" and group == READY_NOW:
        group = WAITING_CONFIRMATION

    # ---- proximity ----
    prox = normalize_price_vs_zone(
        row.get("price_vs_zone") if "price_vs_zone" in row else row.get("price_in_entry_zone")
    )
    proximity_code: str | None = None
    if prox == "in_zone":
        prox_bonus = int(w.get("proximity_bonus", 8.0))
        proximity_code = SCANNER_PROXIMITY_IN_ZONE
    elif prox == "near_zone":
        prox_bonus = int(w.get("proximity_bonus", 8.0) * 0.5)
        proximity_code = SCANNER_PROXIMITY_NEAR_ZONE
    else:
        prox_bonus = 0
        proximity_code = SCANNER_PROXIMITY_FAR

    # ---- readiness ----
    if group == READY_NOW:
        readiness_bonus = int(w.get("readiness_bonus", 10.0))
    elif group == WAITING_CONFIRMATION:
        readiness_bonus = int(w.get("readiness_bonus", 10.0) * 0.3)
    else:
        readiness_bonus = 0

    # ---- R:R ----
    rr_raw = row.get("expected_effective_rr") or row.get("risk_reward")
    rr = parse_risk_reward(rr_raw)
    rr_code: str | None = None
    if rr >= _RR_STRONG:
        rr_bonus = int(w.get("rr_bonus", 5.0))
        rr_code = SCANNER_RR_STRONG
    elif rr >= 1.5:
        rr_bonus = int(w.get("rr_bonus", 5.0) * 0.6)
    elif rr >= _RR_WEAK:
        rr_bonus = int(w.get("rr_bonus", 5.0) * 0.2)
    else:
        rr_bonus = 0

    # ---- spread ----
    spread_raw = str(row.get("spread_status", "")).strip().lower()
    spread_pen = 0
    if spread_raw == "abnormal":
        spread_pen = -int(w.get("spread_penalty", 8.0))
    elif spread_raw == "caution":
        spread_pen = -int(w.get("spread_penalty", 8.0) * 0.5)

    # ---- news ----
    news_pen = 0
    if _truthy(row.get("high_impact_event_within_30m")):
        news_pen = -int(w.get("news_penalty", 10.0))
    elif _truthy(row.get("news_in_3h")):
        news_pen = -int(w.get("news_penalty", 10.0) * 0.5)

    journal_pen = int(safe_float(journal_feedback.get("opportunity_penalty"), 0.0))

    # ---- total ----
    raw = float(base) + prox_bonus + readiness_bonus + rr_bonus + spread_pen + news_pen + journal_pen
    score = int(max(0, min(round(raw), 120)))

    # ---- block cap ----
    if group == BLOCKED:
        score = min(score, 20)

    # ---- reason / codes ----
    reason_codes: list[str] = [SCANNER_OPPORTUNITY_SCORE_OK]
    penalty_codes: list[str] = []
    warning_codes: list[str] = []

    group_code = _GROUP_REASON_CODES.get(group)
    if group_code:
        reason_codes.append(group_code)

    if proximity_code:
        reason_codes.append(proximity_code)
    if rr_code:
        reason_codes.append(rr_code)
    if rr < _RR_WEAK and rr_raw is not None:
        penalty_codes.append(SCANNER_RR_WEAK)
    if spread_raw == "abnormal":
        penalty_codes.append(SCANNER_SPREAD_PENALTY)
    if _truthy(row.get("high_impact_event_within_30m")):
        penalty_codes.append(SCANNER_NEWS_PENALTY)
    for code in journal_feedback.get("warning_codes", []):
        warning_codes.append(str(code))
    for code in journal_feedback.get("block_codes", []):
        penalty_codes.append(str(code))

    return {
        "opportunity_score": score,
        "scanner_group": group,
        "reason_codes": merge_unique_codes(reason_codes),
        "warning_codes": merge_unique_codes(warning_codes),
        "penalty_codes": merge_unique_codes(penalty_codes),
        "score_breakdown": {
            "base_final_score": base,
            "proximity_bonus": prox_bonus,
            "readiness_bonus": readiness_bonus,
            "rr_bonus": rr_bonus,
            "spread_penalty": spread_pen,
            "news_penalty": news_pen,
            "journal_feedback_penalty": journal_pen,
            "raw_score": round(raw, 2),
        },
        "reason": f"opportunity_score={score}, group={group}",
    }


def enrich_scanner_row_with_ranking(row: dict[str, Any] | None) -> dict[str, Any]:
    """Enrich a scanner row with ranking fields without mutating the original.

    Reads ``final_score``, ``decision``, ``score_gap``, and
    ``expected_effective_rr`` from the row, falling back to nested
    ``analysis_result`` fields when available.

    Never mutates *row* or ``analysis_result``.  Never raises.
    """
    if not isinstance(row, dict):
        return _empty_ranking_enrichment()

    enriched = dict(row)  # shallow copy — non-mutating

    # Pull missing fields from analysis_result if present
    ar = row.get("analysis_result")
    if isinstance(ar, dict):
        if "final_score" not in enriched and "final_score" in ar:
            enriched["final_score"] = ar["final_score"]
        if "scanner_decision" not in enriched and "decision" not in enriched:
            de = ar.get("decision_engine")
            if isinstance(de, dict) and "decision" in de:
                enriched["scanner_decision"] = de["decision"]
        if "score_gap" not in enriched:
            ds = ar.get("decision_summary")
            if isinstance(ds, dict) and "score_gap" in ds:
                enriched["score_gap"] = ds["score_gap"]
        if "expected_effective_rr" not in enriched:
            scenarios = ar.get("scenarios")
            if isinstance(scenarios, list) and len(scenarios) > 0:
                best = scenarios[0]
                if isinstance(best, dict):
                    e_rr = best.get("expected_effective_rr")
                    if e_rr is not None:
                        enriched["expected_effective_rr"] = e_rr
        if "entry_status" not in enriched:
            es = ar.get("entry_status")
            if es is not None:
                enriched["entry_status"] = es
        if "decision" not in enriched and "scanner_decision" not in enriched:
            de = ar.get("decision_engine")
            if isinstance(de, dict) and "decision" in de:
                enriched["scanner_decision"] = de["decision"]

    opportunity = calculate_opportunity_score(enriched)

    enriched["opportunity_score"] = opportunity["opportunity_score"]
    enriched["scanner_group"] = opportunity["scanner_group"]
    enriched["display_action"] = SCANNER_GROUP_DISPLAY_ACTIONS.get(
        str(opportunity["scanner_group"]),
        str(enriched.get("scanner_action") or "skip"),
    )
    enriched["ranking_reason_codes"] = opportunity["reason_codes"]
    enriched["ranking_warning_codes"] = opportunity["warning_codes"]
    enriched["ranking_penalty_codes"] = opportunity["penalty_codes"]
    enriched["ranking_score_breakdown"] = opportunity["score_breakdown"]
    enriched["ranking_reason"] = opportunity["reason"]

    return enriched


def enrich_scanner_rows(
    rows: list[dict[str, Any] | None] | None,
) -> list[dict[str, Any]]:
    """Enrich a list of scanner rows with ranking fields.

    Non-list input → ``[]``.  Never raises.
    """
    if not isinstance(rows, list):
        return []
    return [enrich_scanner_row_with_ranking(r) for r in rows]


def _empty_ranking_enrichment() -> dict[str, Any]:
    return {
        "opportunity_score": 0,
        "scanner_group": BLOCKED,
        "display_action": SCANNER_GROUP_DISPLAY_ACTIONS[BLOCKED],
        "ranking_reason_codes": [],
        "ranking_warning_codes": [SCANNER_OPPORTUNITY_DATA_INCOMPLETE],
        "ranking_penalty_codes": [],
    }
