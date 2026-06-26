"""Decision engine — produce the final trading decision from score, gate, and entry status.

Phase 14: this module takes the final_score, gate_result, and entry_status
(produced by other modules) and outputs a standardised decision with
reason/warning/block codes.

Design principles
-----------------
* **Does not compute signal_score.**  That stays in :mod:`core.signal_engine`.
* **Does not compute final_score.**  That stays in :mod:`core.final_score_engine`.
* **Does not call MT5, AI, database, services, or UI.**
* **Does not replace scanner ranking in Phase 14.**
* **Gate-controlled.**  A ``TRADE_BLOCKED`` gate always overrides a high
  final_score.
* **Safe on dirty data.**  Missing or invalid inputs return
  ``STAND_ASIDE`` with ``DECISION_DATA_INCOMPLETE``.

Decision states
---------------
* ``READY_TO_TRADE`` — setup is clean, entry confirmed, gate allows.
* ``WAITING_CONFIRMATION`` — score is decent but entry/M15 not yet confirmed.
* ``AGGRESSIVE_SETUP`` — higher risk, may enter with reduced size.
* ``WATCH_ONLY`` — interesting but not actionable yet.
* ``TRADE_BLOCKED`` — gate has blocked trading.
* ``STAND_ASIDE`` — no actionable setup.

Public API
----------
* ``make_final_decision(final_score, gate_result, entry_status)`` — primary entry.
* ``make_decision(final_score_result, gate_result, entry_status)`` — compatibility
  wrapper that delegates to ``make_final_decision``.
* ``default_decision_result()`` — safe fallback.
"""

from __future__ import annotations

from typing import Any

from core.reason_codes import (
    DECISION_READY_TO_TRADE,
    DECISION_WAITING_CONFIRMATION,
    DECISION_AGGRESSIVE_SETUP,
    DECISION_WATCH_ONLY,
    DECISION_TRADE_BLOCKED,
    DECISION_STAND_ASIDE,
    DECISION_DATA_INCOMPLETE,
    DECISION_GATE_BLOCKED,
    DECISION_GATE_CAPPED,
    DECISION_SCORE_GAP_LOW,
    DECISION_ENTRY_NOT_CONFIRMED,
    DECISION_FINAL_SCORE_STRONG,
    DECISION_FINAL_SCORE_MODERATE,
    DECISION_FINAL_SCORE_WEAK,
    merge_unique_codes,
)
from core.normalization import normalize_choice, normalize_entry_status
from core.safe_types import clamp_score

# ---------------------------------------------------------------------------
# Decision-state constants
# ---------------------------------------------------------------------------

READY_TO_TRADE = "READY_TO_TRADE"
WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
AGGRESSIVE_SETUP = "AGGRESSIVE_SETUP"
WATCH_ONLY = "WATCH_ONLY"
TRADE_BLOCKED = "TRADE_BLOCKED"
STAND_ASIDE = "STAND_ASIDE"

VALID_DECISIONS = frozenset({
    READY_TO_TRADE,
    WAITING_CONFIRMATION,
    AGGRESSIVE_SETUP,
    WATCH_ONLY,
    TRADE_BLOCKED,
    STAND_ASIDE,
})

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

DEFAULT_DECISION_THRESHOLDS: dict[str, int] = {
    "ready": 80,
    "watch": 65,
    "wait": 50,
    "min_score_gap": 10,
}

# ---------------------------------------------------------------------------
# Label mapping
# ---------------------------------------------------------------------------

DECISION_LABELS: dict[str, str] = {
    READY_TO_TRADE: "Sẵn sàng",
    WAITING_CONFIRMATION: "Chờ xác nhận",
    AGGRESSIVE_SETUP: "Mạo hiểm",
    WATCH_ONLY: "Theo dõi",
    TRADE_BLOCKED: "Bị chặn",
    STAND_ASIDE: "Đứng ngoài",
}

# ---------------------------------------------------------------------------
# Reason-code mapping per decision state
# ---------------------------------------------------------------------------

_DECISION_REASON_CODES: dict[str, str] = {
    READY_TO_TRADE: DECISION_READY_TO_TRADE,
    WAITING_CONFIRMATION: DECISION_WAITING_CONFIRMATION,
    AGGRESSIVE_SETUP: DECISION_AGGRESSIVE_SETUP,
    WATCH_ONLY: DECISION_WATCH_ONLY,
    TRADE_BLOCKED: DECISION_TRADE_BLOCKED,
    STAND_ASIDE: DECISION_STAND_ASIDE,
}

# ---------------------------------------------------------------------------
# Cap alias mapping (case-insensitive)
# ---------------------------------------------------------------------------

_CAP_ALIASES: dict[str, str] = {
    "blocked": TRADE_BLOCKED,
    "watch": WATCH_ONLY,
    "wait": WAITING_CONFIRMATION,
    "ready": READY_TO_TRADE,
    "stand_aside": STAND_ASIDE,
    "trade_blocked": TRADE_BLOCKED,
    "watch_only": WATCH_ONLY,
    "waiting_confirmation": WAITING_CONFIRMATION,
    "ready_to_trade": READY_TO_TRADE,
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_decision_cap(value: object) -> str | None:
    """Normalise a decision-cap string to a canonical constant.

    Accepts common aliases (case-insensitive):
    - ``"blocked"`` / ``"TRADE_BLOCKED"`` → ``TRADE_BLOCKED``
    - ``"watch"`` / ``"WATCH_ONLY"`` → ``WATCH_ONLY``
    - ``"wait"`` / ``"WAITING_CONFIRMATION"`` → ``WAITING_CONFIRMATION``
    - ``"ready"`` / ``"READY_TO_TRADE"`` → ``READY_TO_TRADE``
    - ``"stand_aside"`` / ``"STAND_ASIDE"`` → ``STAND_ASIDE``

    Returns ``None`` for unrecognised, empty, or non-string input.
    """
    return normalize_choice(
        value,
        VALID_DECISIONS,
        aliases=_CAP_ALIASES,
        default=None,
        case="upper",
        null_values=frozenset({"none", "null", "n/a"}),
    )

def gate_allows_trade(
    gate_result: dict[str, object] | None,
    trade_permission: dict[str, object] | None = None,
) -> bool:
    """Check whether the gate layer permits trading.

    - If *gate_result* has ``allowed`` → ``bool(allowed)``.
    - If *trade_permission* has ``status == "blocked"`` → ``False``.
    - No clear data → ``False`` (safe default).

    Never raises.
    """
    if isinstance(gate_result, dict):
        allowed = gate_result.get("allowed")
        if isinstance(allowed, bool):
            return allowed
        decision_cap = gate_result.get("decision_cap")
        if decision_cap == "TRADE_BLOCKED":
            return False

    if isinstance(trade_permission, dict):
        status = str(trade_permission.get("status", "")).strip().lower()
        if status == "blocked":
            return False

    return False

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def default_decision_result(reason: str = "decision_not_calculated") -> dict[str, Any]:
    """Return a safe default result when the decision cannot be computed."""
    return {
        "decision": STAND_ASIDE,
        "final_score": 0,
        "decision_label": DECISION_LABELS[STAND_ASIDE],
        "legacy_action": decision_to_legacy_action(STAND_ASIDE),
        "reason_codes": [],
        "warning_codes": [DECISION_DATA_INCOMPLETE],
        "block_codes": [],
        "decision_cap": None,
        "allowed": False,
        "score_breakdown": {},
        "reason": reason,
    }


def make_decision(
    final_score_result: dict[str, Any] | None,
    gate_result: dict[str, Any] | None,
    entry_status: str | None,
    *,
    thresholds: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Produce a final trading decision from the three core inputs.

    Parameters
    ----------
    final_score_result : dict | None
        Output from :func:`core.final_score_engine.calculate_final_score`.
        If ``None`` or missing ``final_score``, ``STAND_ASIDE`` is returned.
    gate_result : dict | None
        Output from :func:`core.trade_gate_engine.check_trade_gates`.
        If ``None`` or ``allowed`` is ``False``, ``TRADE_BLOCKED`` is returned.
    entry_status : str | None
        Entry confirmation status.  ``"confirmed_entry"`` is required for
        ``READY_TO_TRADE``, otherwise ``WAITING_CONFIRMATION``.
    thresholds : dict | None
        Optional override of ``DEFAULT_DECISION_THRESHOLDS``.

    Returns
    -------
    dict
        Standardised decision result.  Never raises.
    """
    if not isinstance(final_score_result, dict):
        return default_decision_result("missing_final_score_result")
    if not isinstance(gate_result, dict):
        return default_decision_result("missing_gate_result")

    # Compatibility wrapper: keep the old import surface while ensuring
    # make_final_decision remains the single authoritative decision path.
    return make_final_decision(
        final_score=final_score_result.get("final_score", 0),
        gate_result=gate_result,
        entry_status=entry_status,
        thresholds=thresholds,
    )


# ---------------------------------------------------------------------------
# High-level decision entry point
# ---------------------------------------------------------------------------


def make_final_decision(
    *,
    final_score: object,
    gate_result: dict[str, object] | None = None,
    entry_status: object = None,
    score_gap: object = None,
    trade_permission: dict[str, object] | None = None,
    thresholds: dict[str, int] | None = None,
    allow_aggressive_setup: bool = False,
) -> dict[str, Any]:
    """Produce the final trading decision using gate > cap > gap > entry > score.

    Decision layers in priority order
    ----------------------------------
    A. **Gate block** — ``gate_result.allowed == False`` or
       ``trade_permission.status == "blocked"`` → ``TRADE_BLOCKED``.
    B. **Decision cap == TRADE_BLOCKED** → ``TRADE_BLOCKED``.
    C. **Decision cap == WATCH_ONLY** → ``WATCH_ONLY``.
    D. **Decision cap == WAITING_CONFIRMATION** → ``WAITING_CONFIRMATION``.
    E. **Score gap too low** — ``score_gap < min_score_gap`` →
       ``WAITING_CONFIRMATION`` (unclear bias).
    F. **Entry not confirmed** — maps directly to ``WATCH_ONLY`` /
       ``WAITING_CONFIRMATION`` / ``STAND_ASIDE``.
    G. **Entry confirmed + score** — uses ``ready`` / ``watch`` /
       ``wait`` thresholds.

    Never raises.
    """
    t = thresholds or DEFAULT_DECISION_THRESHOLDS
    score = clamp_score(final_score, default=0)
    norm_entry = normalize_entry_status(entry_status)
    norm_cap = normalize_decision_cap(
        gate_result.get("decision_cap") if isinstance(gate_result, dict) else None
    )
    gap = None
    if score_gap is not None:
        try:
            gap = int(float(str(score_gap))) if isinstance(score_gap, (int, float, str)) else None
        except (ValueError, TypeError):
            gap = None

    gate_allowed = gate_allows_trade(gate_result, trade_permission)
    tp_blocked = False
    if isinstance(trade_permission, dict):
        tp_blocked = str(trade_permission.get("status", "")).strip().lower() == "blocked"

    reason_codes: list[str] = []
    warning_codes: list[str] = []
    block_codes: list[str] = []
    applied_rule = "initial"

    # ---- A. Gate / trade_permission block ----
    if not gate_allowed or tp_blocked:
        block_codes.append(DECISION_GATE_BLOCKED)
        if isinstance(gate_result, dict):
            for c in (gate_result.get("block_codes") or []):
                block_codes.append(str(c))
        return {
            "decision": TRADE_BLOCKED,
            "final_score": score,
            "decision_label": _label_for(TRADE_BLOCKED),
            "legacy_action": decision_to_legacy_action(TRADE_BLOCKED),
            "reason_codes": [DECISION_TRADE_BLOCKED],
            "warning_codes": merge_unique_codes(warning_codes),
            "block_codes": merge_unique_codes(block_codes),
            "decision_cap": norm_cap,
            "allowed": False,
            "score_breakdown": _breakdown(norm_entry, gap, t, gate_allowed, "Gate blocked"),
            "reason": "Gate hoặc trade_permission chặn giao dịch.",
        }

    # ---- B / C / D. Decision cap layers ----
    if norm_cap == TRADE_BLOCKED:
        block_codes.append(DECISION_GATE_BLOCKED)
        return {
            "decision": TRADE_BLOCKED,
            "final_score": score,
            "decision_label": _label_for(TRADE_BLOCKED),
            "legacy_action": decision_to_legacy_action(TRADE_BLOCKED),
            "reason_codes": [DECISION_TRADE_BLOCKED],
            "warning_codes": merge_unique_codes(warning_codes),
            "block_codes": merge_unique_codes(block_codes),
            "decision_cap": norm_cap,
            "allowed": False,
            "score_breakdown": _breakdown(norm_entry, gap, t, gate_allowed, "Cap = TRADE_BLOCKED"),
            "reason": "Decision cap là TRADE_BLOCKED.",
        }

    if norm_cap == WATCH_ONLY:
        warning_codes.append(DECISION_GATE_CAPPED)
        return {
            "decision": WATCH_ONLY,
            "final_score": score,
            "decision_label": _label_for(WATCH_ONLY),
            "legacy_action": decision_to_legacy_action(WATCH_ONLY),
            "reason_codes": [DECISION_WATCH_ONLY],
            "warning_codes": merge_unique_codes(warning_codes),
            "block_codes": merge_unique_codes(block_codes),
            "decision_cap": norm_cap,
            "allowed": True,
            "score_breakdown": _breakdown(norm_entry, gap, t, gate_allowed, "Cap = WATCH_ONLY"),
            "reason": "Gate giới hạn quyết định ở mức WATCH_ONLY.",
        }

    if norm_cap == WAITING_CONFIRMATION:
        warning_codes.append(DECISION_GATE_CAPPED)
        return {
            "decision": WAITING_CONFIRMATION,
            "final_score": score,
            "decision_label": _label_for(WAITING_CONFIRMATION),
            "legacy_action": decision_to_legacy_action(WAITING_CONFIRMATION),
            "reason_codes": [DECISION_WAITING_CONFIRMATION],
            "warning_codes": merge_unique_codes(warning_codes),
            "block_codes": merge_unique_codes(block_codes),
            "decision_cap": norm_cap,
            "allowed": True,
            "score_breakdown": _breakdown(norm_entry, gap, t, gate_allowed, "Cap = WAITING_CONFIRMATION"),
            "reason": "Gate giới hạn quyết định ở mức WAITING_CONFIRMATION.",
        }

    # ---- E. Score gap ----
    min_gap = t.get("min_score_gap", 10)
    if gap is not None and gap < min_gap:
        warning_codes.append(DECISION_SCORE_GAP_LOW)
        return {
            "decision": WAITING_CONFIRMATION,
            "final_score": score,
            "decision_label": _label_for(WAITING_CONFIRMATION),
            "legacy_action": decision_to_legacy_action(WAITING_CONFIRMATION),
            "reason_codes": [DECISION_WAITING_CONFIRMATION],
            "warning_codes": merge_unique_codes(warning_codes),
            "block_codes": merge_unique_codes(block_codes),
            "decision_cap": norm_cap,
            "allowed": True,
            "score_breakdown": _breakdown(norm_entry, gap, t, gate_allowed, "Score gap too low"),
            "reason": f"Khoảng cách điểm Buy/Sell quá thấp ({gap} < {min_gap}), chưa rõ hướng.",
        }

    # ---- E2. Aggressive setup (optional) ----
    if (
        allow_aggressive_setup
        and norm_entry == "waiting_confirmation"
        and score >= t.get("ready", 80)
        and norm_cap is None
    ):
        code = [DECISION_AGGRESSIVE_SETUP]
        warn = merge_unique_codes(warning_codes, [DECISION_ENTRY_NOT_CONFIRMED])
        return {
            "decision": AGGRESSIVE_SETUP,
            "final_score": score,
            "decision_label": _label_for(AGGRESSIVE_SETUP),
            "legacy_action": decision_to_legacy_action(AGGRESSIVE_SETUP),
            "reason_codes": merge_unique_codes(code),
            "warning_codes": warn,
            "block_codes": merge_unique_codes(block_codes),
            "decision_cap": norm_cap,
            "allowed": True,
            "score_breakdown": _breakdown(
                norm_entry, gap, t, gate_allowed,
                "Aggressive setup (caller allowed)",
            ),
            "reason": (
                "Setup mạo hiểm: entry chưa confirmed nhưng score rất cao. "
                "KHÔNG phải READY — trader tự quyết định có vào lệnh với khối lượng nhỏ hơn không."
            ),
        }

    # ---- F. Entry not confirmed ----
    if norm_entry != "confirmed_entry":
        warning_codes.append(DECISION_ENTRY_NOT_CONFIRMED)
        if norm_entry == "watch_zone":
            return {
                "decision": WATCH_ONLY,
                "final_score": score,
                "decision_label": _label_for(WATCH_ONLY),
                "legacy_action": decision_to_legacy_action(WATCH_ONLY),
                "reason_codes": [DECISION_WATCH_ONLY],
                "warning_codes": merge_unique_codes(warning_codes),
                "block_codes": merge_unique_codes(block_codes),
                "decision_cap": norm_cap,
                "allowed": True,
                "score_breakdown": _breakdown(norm_entry, gap, t, gate_allowed, "Entry watch_zone"),
                "reason": "Entry status = watch_zone.",
            }
        if norm_entry in ("invalidated", "no_setup"):
            return {
                "decision": STAND_ASIDE,
                "final_score": score,
                "decision_label": _label_for(STAND_ASIDE),
                "legacy_action": decision_to_legacy_action(STAND_ASIDE),
                "reason_codes": [DECISION_STAND_ASIDE],
                "warning_codes": merge_unique_codes(warning_codes),
                "block_codes": merge_unique_codes(block_codes),
                "decision_cap": norm_cap,
                "allowed": True,
                "score_breakdown": _breakdown(norm_entry, gap, t, gate_allowed, "Entry invalidated/no_setup"),
                "reason": f"Entry status = {norm_entry}, không có setup.",
            }
        # waiting_confirmation or unknown
        return {
            "decision": WAITING_CONFIRMATION,
            "final_score": score,
            "decision_label": _label_for(WAITING_CONFIRMATION),
            "legacy_action": decision_to_legacy_action(WAITING_CONFIRMATION),
            "reason_codes": [DECISION_WAITING_CONFIRMATION],
            "warning_codes": merge_unique_codes(warning_codes),
            "block_codes": merge_unique_codes(block_codes),
            "decision_cap": norm_cap,
            "allowed": True,
            "score_breakdown": _breakdown(norm_entry, gap, t, gate_allowed, "Entry not confirmed"),
            "reason": f"Entry status = {norm_entry}, chờ xác nhận.",
        }

    # ---- G. Entry confirmed — score-based ----
    if score >= t.get("ready", 80):
        reason_codes = [DECISION_READY_TO_TRADE, DECISION_FINAL_SCORE_STRONG]
        return {
            "decision": READY_TO_TRADE,
            "final_score": score,
            "decision_label": _label_for(READY_TO_TRADE),
            "legacy_action": decision_to_legacy_action(READY_TO_TRADE),
            "reason_codes": merge_unique_codes(reason_codes),
            "warning_codes": merge_unique_codes(warning_codes),
            "block_codes": merge_unique_codes(block_codes),
            "decision_cap": norm_cap,
            "allowed": True,
            "score_breakdown": _breakdown(norm_entry, gap, t, gate_allowed, "Entry confirmed + score ≥ ready"),
            "reason": "Entry confirmed và final score đủ mạnh.",
        }

    if score >= t.get("watch", 65):
        reason_codes = [DECISION_WATCH_ONLY, DECISION_FINAL_SCORE_MODERATE]
        return {
            "decision": WATCH_ONLY,
            "final_score": score,
            "decision_label": _label_for(WATCH_ONLY),
            "legacy_action": decision_to_legacy_action(WATCH_ONLY),
            "reason_codes": merge_unique_codes(reason_codes),
            "warning_codes": merge_unique_codes(warning_codes),
            "block_codes": merge_unique_codes(block_codes),
            "decision_cap": norm_cap,
            "allowed": True,
            "score_breakdown": _breakdown(norm_entry, gap, t, gate_allowed, "Entry confirmed + score 65-79"),
            "reason": "Entry confirmed nhưng score ở mức watch.",
        }

    if score >= t.get("wait", 50):
        reason_codes = [DECISION_WAITING_CONFIRMATION]
        return {
            "decision": WAITING_CONFIRMATION,
            "final_score": score,
            "decision_label": _label_for(WAITING_CONFIRMATION),
            "legacy_action": decision_to_legacy_action(WAITING_CONFIRMATION),
            "reason_codes": merge_unique_codes(reason_codes),
            "warning_codes": merge_unique_codes(warning_codes),
            "block_codes": merge_unique_codes(block_codes),
            "decision_cap": norm_cap,
            "allowed": True,
            "score_breakdown": _breakdown(norm_entry, gap, t, gate_allowed, "Entry confirmed + score 50-64"),
            "reason": "Entry confirmed nhưng score chưa đủ watch.",
        }

    reason_codes = [DECISION_STAND_ASIDE, DECISION_FINAL_SCORE_WEAK]
    return {
        "decision": STAND_ASIDE,
        "final_score": score,
        "decision_label": _label_for(STAND_ASIDE),
        "legacy_action": decision_to_legacy_action(STAND_ASIDE),
        "reason_codes": merge_unique_codes(reason_codes),
        "warning_codes": merge_unique_codes(warning_codes),
        "block_codes": merge_unique_codes(block_codes),
        "decision_cap": norm_cap,
        "allowed": True,
        "score_breakdown": _breakdown(norm_entry, gap, t, gate_allowed, "Entry confirmed + score < wait"),
        "reason": "Score quá thấp, đứng ngoài.",
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _label_for(decision: str) -> str:
    """Return the Vietnamese label for a decision constant."""
    labels: dict[str, str] = {
        READY_TO_TRADE: "Sẵn sàng giao dịch",
        WAITING_CONFIRMATION: "Chờ xác nhận",
        AGGRESSIVE_SETUP: "Setup mạo hiểm",
        WATCH_ONLY: "Chỉ theo dõi",
        TRADE_BLOCKED: "Bị chặn giao dịch",
        STAND_ASIDE: "Đứng ngoài",
    }
    return labels.get(decision, DECISION_LABELS.get(decision, decision))


# ---------------------------------------------------------------------------
# Legacy action mapping
# ---------------------------------------------------------------------------

# Map decision-engine constants → legacy action strings
_DECISION_TO_LEGACY: dict[str, str] = {
    READY_TO_TRADE: "ready",
    WATCH_ONLY: "watch",
    WAITING_CONFIRMATION: "wait_for_confirmation",
    AGGRESSIVE_SETUP: "wait_for_confirmation",
    TRADE_BLOCKED: "stand_aside",
    STAND_ASIDE: "stand_aside",
}

def decision_to_legacy_action(decision: object) -> str:
    """Map a decision-engine constant to a legacy action string.

    - ``READY_TO_TRADE`` → ``"ready"``
    - ``WATCH_ONLY`` → ``"watch"``
    - ``WAITING_CONFIRMATION`` / ``AGGRESSIVE_SETUP`` → ``"wait_for_confirmation"``
    - ``TRADE_BLOCKED`` / ``STAND_ASIDE`` → ``"stand_aside"``
    - Unknown → ``"stand_aside"`` (safe default)
    """
    if not isinstance(decision, str):
        return "stand_aside"
    cleaned = decision.strip()
    return _DECISION_TO_LEGACY.get(cleaned, "stand_aside")


def _breakdown(
    entry_status: str,
    score_gap: int | None,
    thresholds: dict[str, int],
    gate_allowed: bool,
    applied_rule: str,
) -> dict[str, object]:
    return {
        "entry_status": entry_status,
        "score_gap": score_gap,
        "thresholds": thresholds,
        "gate_allowed": gate_allowed,
        "applied_rule": applied_rule,
    }


# ---------------------------------------------------------------------------
# Payload readers
# ---------------------------------------------------------------------------


def pick_final_score(payload: dict[str, Any] | None) -> int:
    """Extract a final_score from an analysis-result payload.

    Precedence:
    1. ``payload["final_score"]``
    2. ``payload["final_score_detail"]["final_score"]``
    3. ``payload["decision_summary"]["best_score"]`` (temporary fallback)
    4. 0

    Never raises.
    """
    if not isinstance(payload, dict):
        return 0
    direct = payload.get("final_score")
    if isinstance(direct, (int, float)):
        return clamp_score(direct, default=0)
    detail = payload.get("final_score_detail")
    if isinstance(detail, dict):
        fs = detail.get("final_score")
        if isinstance(fs, (int, float)):
            return clamp_score(fs, default=0)
    decision = payload.get("decision_summary")
    if isinstance(decision, dict):
        best = decision.get("best_score")
        if isinstance(best, (int, float)):
            return clamp_score(best, default=0)
    return 0


def pick_gate_result(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Extract the gate result dict from an analysis-result payload.

    Precedence: ``payload["trade_gate"]`` → ``payload["gate"]`` → ``None``.
    """
    if not isinstance(payload, dict):
        return None
    trade_gate = payload.get("trade_gate")
    if isinstance(trade_gate, dict):
        return trade_gate
    gate = payload.get("gate")
    if isinstance(gate, dict):
        return gate
    return None


def pick_entry_status(payload: dict[str, Any] | None) -> str:
    """Extract the best-side entry_status from a payload.

    Precedence:
    1. First buy/sell scenario in ``payload["scenarios"]`` → ``entry_status``.
    2. ``payload["entry_status"]``.
    3. ``"unknown"``.
    """
    if not isinstance(payload, dict):
        return "unknown"
    scenarios = payload.get("scenarios")
    if isinstance(scenarios, list):
        for s in scenarios:
            if isinstance(s, dict) and s.get("type") in ("buy", "sell"):
                es = s.get("entry_status")
                if isinstance(es, str) and es.strip():
                    return normalize_entry_status(es)
    es = payload.get("entry_status")
    if isinstance(es, str) and es.strip():
        return normalize_entry_status(es)
    return "unknown"


def pick_score_gap(payload: dict[str, Any] | None) -> int | None:
    """Extract the Buy/Sell score gap from a payload.

    Precedence:
    1. ``payload["decision_summary"]["score_gap"]``
    2. ``payload["direction_bias"]["score_gap"]``
    3. ``payload["score_gap"]``
    4. ``None``

    Never raises.
    """
    if not isinstance(payload, dict):
        return None
    # decision_summary.score_gap
    ds = payload.get("decision_summary")
    if isinstance(ds, dict):
        gap = ds.get("score_gap")
        if gap is not None:
            try:
                return int(float(str(gap)))
            except (ValueError, TypeError):
                pass
    # direction_bias.score_gap
    db = payload.get("direction_bias")
    if isinstance(db, dict):
        gap = db.get("score_gap")
        if gap is not None:
            try:
                return int(float(str(gap)))
            except (ValueError, TypeError):
                pass
    # top-level score_gap
    gap = payload.get("score_gap")
    if gap is not None:
        try:
            return int(float(str(gap)))
        except (ValueError, TypeError):
            pass
    return None


# ---------------------------------------------------------------------------
# Payload-level entry point
# ---------------------------------------------------------------------------


def calculate_decision_from_payload(
    payload: dict[str, Any] | None,
    *,
    thresholds: dict[str, int] | None = None,
    allow_aggressive_setup: bool = False,
) -> dict[str, Any]:
    """Produce a final decision from an analysis-result or scanner-row payload.

    Uses :func:`pick_final_score`, :func:`pick_gate_result`,
    :func:`pick_entry_status`, and :func:`pick_score_gap` to extract values,
    then delegates to :func:`make_final_decision`.

    Does **not** mutate *payload*.
    """
    score = pick_final_score(payload)
    gate = pick_gate_result(payload)
    entry = pick_entry_status(payload)
    gap = pick_score_gap(payload)
    tp = payload.get("trade_permission") if isinstance(payload, dict) else None
    if not isinstance(tp, dict):
        tp = None

    result = make_final_decision(
        final_score=score,
        gate_result=gate,
        entry_status=entry,
        score_gap=gap,
        trade_permission=tp,
        thresholds=thresholds,
        allow_aggressive_setup=allow_aggressive_setup,
    )

    breakdown = result.setdefault("score_breakdown", {})
    if isinstance(breakdown, dict):
        breakdown["source"] = "payload"

    return result
