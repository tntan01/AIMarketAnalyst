"""Scanner V4 → UI row adapter (Bước 12 C2a; target-only, must-stay).

This is the SINGLE place that converts a ``V4ReleasePair`` (the release wiring's
one-symbol artefact set: composition → exact-identity row → candidate) into the
UI/aftercare-facing row **dict** the live controller and ``scanner_screen``
consume.  It exists so the controller/UI never interpret V4 internals and never
fall back to the V3 row contract.

Mapping discipline (owner rules, Bước 5):

* a key is emitted from a REAL V4 source where one exists — never invented:
  ``setup_score``, ``candidate_status``, ``selected_side``, ``score_gap``,
  ``decision_cap``, ``evidence_score``, ``execution_quality_score``,
  ``risk_reward_ratio``, ``market_regime``, macro/safety status + reason codes,
  gate/reason/block codes, the selected-side scenario's ``entry``/``stop_loss``/
  ``take_profit``, the retained-technical ``price``/``atr_h1`` passthrough, and
  the exact version identity block;
* a key that only existed in V3 and has NO V4 equivalent is set to a documented
  neutral (``None`` / ``0`` / ``{}`` / ``"none"``) — never fabricated;
* identity is validated EXACT before any mapping: a V3/mixed/unknown pair or row
  version is refused (raises ``AdapterContractError``) — never coerced.

The routed candidate stays INTENT ONLY (``sends_real_order=False``); this adapter
never dispatches and never fabricates an executable flag.
"""

from __future__ import annotations

from datetime import datetime, timezone
from fractions import Fraction
from typing import Any

from core.scanner_v4_candidate import ScannerV4CandidateDecision
from core.scanner_v4_composition import (
    COMPOSITION_POLICY_VERSION,
    ScannerV4CompositionResult,
)
from core.scanner_v4_models import (
    BLOCKED,
    DATA_UNAVAILABLE,
    OUT_OF_STRATEGY,
    READY_NOW,
    SCANNER_V4_FEATURE_VERSION,
    SCANNER_V4_MACRO_POLICY_VERSION,
    SCANNER_V4_OUTPUT_SCHEMA_VERSION,
    SCANNER_V4_SAFETY_POLICY_VERSION,
    SCANNER_V4_SCORING_VERSION,
    SCANNER_V4_SNAPSHOT_VERSION,
    WAITING_CONFIRMATION,
    WATCH_ZONE,
)
from core.scanner_v4_release import V4ReleasePair
from core.scanner_v4_row import SCANNER_V4_ROW_VERSION, ScannerV4Row

# The one row/identity stamp this adapter produces (same locked constants the V4
# models use; never a literal).
ADAPTER_VERSION = "scanner-v4-ui-adapter-v1"

# Stable outcome label for a successfully-analyzed V4 row (never "structural_reject"
# — the V4 model has no OUT_OF_STRATEGY / structural-reject classification).
ANALYSIS_OK = "ok"

# Statuses that make a pair an auto-trade candidate in the V4 model (kept from
# the candidate statuses; never DATA_UNAVAILABLE / BLOCKED / WATCH_ZONE).
AUTO_TRADE_CANDIDATE_STATUSES = frozenset({READY_NOW, WAITING_CONFIRMATION})

# V4-only → UI keys with a real V4 source are mapped inside ``pair_to_ui_row``.
# These V3-era keys have NO V4 equivalent and are emitted as a documented neutral
# (fail-closed; never an optimistic number).
V3_ONLY_NEUTRAL_KEYS = (
    "opportunity_rank",            # V3 had a composite rank; V4 has no composite rank
    "auto_trade_branch",           # V3 backtest-config branch; V4 has no backtest config
    "strategy_config_status",      # V3 strategy-config status; V4 config invalidates by fingerprint
    "entry_zone_scoring_version",  # V3 zone-scorer version; V4 has no zone scorer
    "ranking_score_breakdown",     # V3 composite ranking breakdown; V4 has no composite
    "journal_sample_size",         # V3 journal feedback metric; V4 journal is a state gate
    "journal_expectancy_r",        # V3 journal expectancy; not produced by V4
    "journal_feedback",            # V3 journal feedback dict; V4 journal is a state gate
    "journal_evidence_score",      # V3 journal score; not produced by V4
    "journal_opportunity_penalty", # V3 journal penalty; not produced by V4
    "m15_quality",                 # V3 M15 quality; V4 derives from D1/H4/H1 only
    "entry_status",                # V3 entry-zone status; V4 has no entry-zone model
    "price_vs_zone",               # V3 zone-relative price; V4 has no zone model
    "direction_bias",              # V3 directional-bias dict; V4 exposes selected side only
    "zone_origin_class",           # V3 zone origin; V4 has no zone-origin concept -> "none"
    "risk_score",                  # V3 risk-score restriction; V4 has no risk scored component
    "scanner_action",              # V3 legacy action label; V4 uses candidate_status
    "best_side",                   # V3 composite best side; V4 exposes selected_side only
    "best_score",                  # V3 composite best score; V4 has no composite
)

# Documented neutral values for the V3-only keys (fail closed, never optimistic).
_V3_ONLY_NEUTRAL: dict[str, Any] = {
    "opportunity_rank": None,
    "auto_trade_branch": None,
    "strategy_config_status": None,
    "entry_zone_scoring_version": None,
    "ranking_score_breakdown": None,
    "journal_sample_size": 0,
    "journal_expectancy_r": None,
    "journal_feedback": {},
    "journal_evidence_score": None,
    "journal_opportunity_penalty": None,
    "m15_quality": None,
    "entry_status": None,
    "price_vs_zone": None,
    "direction_bias": None,
    "zone_origin_class": "none",
    "risk_score": None,
    "scanner_action": None,
    "best_side": None,
    "best_score": None,
}

# Exact V4 version a row must carry (row_version handled separately).
_ROW_VERSION_EXPECTED: dict[str, str] = {
    "composition_version": COMPOSITION_POLICY_VERSION,
    "scoring_version": SCANNER_V4_SCORING_VERSION,
    "feature_version": SCANNER_V4_FEATURE_VERSION,
    "output_schema_version": SCANNER_V4_OUTPUT_SCHEMA_VERSION,
    "safety_policy_version": SCANNER_V4_SAFETY_POLICY_VERSION,
    "macro_policy_version": SCANNER_V4_MACRO_POLICY_VERSION,
    "snapshot_version": SCANNER_V4_SNAPSHOT_VERSION,
}


class AdapterContractError(ValueError):
    """Fail-closed error when the input is not an exact-identity V4 pair/row."""


def pair_to_ui_row(
    pair: object,
    *,
    broker_symbol: str = "",
    scan_id: str = "",
    row_id: str = "",
    settings_hash: str = "",
    rollout_stage: str = "",
    latency_ms: float | None = None,
    technical: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Map an exact-identity ``V4ReleasePair`` into the UI/aftercare row dict.

    ``technical`` is the retained live technical snapshot dict (from
    ``derive_live_analysis``) so the adapter can carry the REAL ``price`` /
    ``atr_h1`` the controller still reads for sizing/position registration.  It
    is optional; when absent (or missing a key) those values are ``None``.
    """
    pair = _require_v4_pair(pair)
    row = _require_v4_row(pair.row)
    candidate = _require_v4_candidate(pair.candidate)
    _require_v4_composition(pair.composition)

    selected_side = row.selected_side
    technical_score = row.selected_technical_signal_score
    setup_score = row.selected_setup_score

    # --- exact version identity block (mirrors the row; JSON-safe) -----------
    identity = {
        "row_version": row.row_version,
        "composition_version": row.composition_version,
        "scoring_version": row.scoring_version,
        "feature_version": row.feature_version,
        "output_schema_version": row.output_schema_version,
        "safety_policy_version": row.safety_policy_version,
        "macro_policy_version": row.macro_policy_version,
        "snapshot_version": row.snapshot_version,
        "adapter_version": ADAPTER_VERSION,
    }

    # --- candidate-sourced values (fail closed to None when no candidate) ----
    evidence_score = candidate.evidence_score if candidate else None
    execution_quality_score = candidate.execution_quality_score if candidate else None
    risk_reward_ratio = candidate.risk_reward_ratio if candidate else None

    # --- market regime: from the selected side's technical result -----------
    regime = _regime_of(pair.composition, selected_side) if selected_side else None

    # --- scenario plan (selected side only; real, never fabricated) ----------
    plan = pair.composition.scenario.plan if (selected_side is not None) else None
    entry_price = plan.entry if plan else None
    stop_loss = plan.stop_loss if plan else None
    take_profit = plan.take_profit if plan else None

    # --- compat shim the controller still reads (REAL values or None) --------
    price = None
    atr_h1 = None
    if isinstance(technical, dict):
        raw_price = technical.get("price")
        raw_atr = technical.get("atr_h1")
        if isinstance(raw_price, (int, float)):
            price = raw_price
        if isinstance(raw_atr, (int, float)):
            atr_h1 = raw_atr
    analysis_result = {
        "status": ANALYSIS_OK,
        "technical": {"price": price, "atr_h1": atr_h1},
        "scenarios": _scenarios_of(pair.composition, selected_side),
    }

    # --- order payload (INTENT ONLY; never sends a real order) ---------------
    order_payload = candidate.order_payload if candidate else None
    candidate_order_payload = None if order_payload is None else order_payload.to_dict()

    # --- candidate decision shape for the UI's reason-code chain -------------
    scanner_candidate_decision = {
        "strategy": {
            "reason_codes": list(row.reason_codes),
            "score_value": technical_score,
            "setup_score": setup_score,
            "expected_effective_rr": _fraction_to_number(risk_reward_ratio),
        },
        "reason_codes": list(row.reason_codes),
        "candidate_status": row.candidate_status,
        "selected_side": selected_side,
    }

    row_dict: dict[str, Any] = {
        **identity,
        "symbol": row.symbol,
        "broker_symbol": broker_symbol or row.symbol,
        "snapshot_id": row.snapshot_id,
        "captured_at": _iso(row.captured_at),
        "capture_source": row.capture_source,
        "analysis_status": ANALYSIS_OK,
        "pipeline_route": "scanner-v4",
        "candidate_status": row.candidate_status,
        "selected_side": selected_side,
        "score_gap": row.score_gap,
        "decision_cap": row.decision_cap,
        "final_score": setup_score,  # documented: V4 has no composite; emit the setup score
        "setup_score": setup_score,
        "technical_signal_score": technical_score,
        "evidence_score": evidence_score,
        "evidence_confidence": evidence_score,
        "execution_quality_score": execution_quality_score,
        "execution_readiness": execution_quality_score,  # fail closed to None
        "expected_effective_rr": _fraction_to_number(risk_reward_ratio),
        "risk_reward_ratio": _fraction_to_number(risk_reward_ratio),
        "market_regime": regime,
        "macro_status": row.macro_status,
        "macro_reason_codes": list(row.macro_reason_codes),
        "safety_status": row.safety_status,
        "safety_reason_codes": list(row.safety_reason_codes),
        "gate_codes": list(row.gate_codes),
        "reason_codes": list(row.reason_codes),
        "block_codes": list(row.block_codes),
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "entry_zone": entry_price,
        "analysis_result": analysis_result,
        "scanner_candidate_decision": scanner_candidate_decision,
        "candidate_order_payload": candidate_order_payload,
        "auto_trade_candidate": bool(
            candidate is not None
            and candidate.candidate_status in AUTO_TRADE_CANDIDATE_STATUSES
        ),
        "scan_id": scan_id,
        "row_id": row_id,
        "settings_hash": settings_hash,
        "rollout_stage": rollout_stage,
        "analysis_latency_ms": latency_ms,
    }
    for key in V3_ONLY_NEUTRAL_KEYS:
        row_dict.setdefault(key, _V3_ONLY_NEUTRAL[key])
    return row_dict


def _require_v4_pair(pair: object) -> V4ReleasePair:
    if type(pair) is not V4ReleasePair:
        raise AdapterContractError(
            f"expected a V4ReleasePair (got {type(pair).__name__}); "
            "refusing V3/mixed identity"
        )
    return pair


def _require_v4_row(row: object) -> ScannerV4Row:
    if type(row) is not ScannerV4Row:
        raise AdapterContractError(
            f"expected a ScannerV4Row (got {type(row).__name__})"
        )
    if row.row_version != SCANNER_V4_ROW_VERSION:
        raise AdapterContractError(
            f"row_version {row.row_version!r} != {SCANNER_V4_ROW_VERSION!r}"
        )
    for field, expected_version in _ROW_VERSION_EXPECTED.items():
        actual = getattr(row, field)
        if actual != expected_version:
            raise AdapterContractError(
                f"row.{field} {actual!r} != locked {expected_version!r} — refusing V3/mixed"
            )
    return row


def _require_v4_candidate(candidate: object) -> ScannerV4CandidateDecision | None:
    if candidate is None:
        return None
    if type(candidate) is not ScannerV4CandidateDecision:
        raise AdapterContractError(
            f"expected ScannerV4CandidateDecision or None (got {type(candidate).__name__})"
        )
    return candidate


def _require_v4_composition(composition: object) -> ScannerV4CompositionResult:
    if type(composition) is not ScannerV4CompositionResult:
        raise AdapterContractError(
            f"expected a ScannerV4CompositionResult (got {type(composition).__name__})"
        )
    return composition


def _regime_of(composition: ScannerV4CompositionResult, side: str | None) -> str | None:
    technical = composition.technical.get(side) if side is not None else None
    if technical is None:
        return None
    regime = getattr(technical, "regime", None)
    return regime if isinstance(regime, str) else None


def _scenarios_of(
    composition: ScannerV4CompositionResult, side: str | None
) -> list[dict[str, Any]]:
    """The UI's ``zone_origin_from_row`` reads ``analysis_result.scenarios``.

    V4 has no zone model, so this lists the single selected-side scenario plan
    (real, when present) — enough for the pure ``zone_origin`` mapper to classify
    a real plan without any zone-origin concept.
    """
    if side is None:
        return []
    plan = composition.scenario.plan
    if plan is None:
        return []
    return [
        {
            "side": plan.direction,
            "entry": plan.entry,
            "stop_loss": plan.stop_loss,
            "take_profit": plan.take_profit,
            "source": plan.source,
        }
    ]


def _fraction_to_number(value: Fraction | None) -> float | None:
    return None if value is None else float(value)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Scanner output envelope + fail-closed blocked-row (C2b controller helpers)
# ---------------------------------------------------------------------------

_OUT_OF_SCOPE = frozenset()


def scanner_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Same-shaped V4 summary (C2b): count rows by real candidate_status.

    Reads ONLY the V4 ``candidate_status`` the adapter emits (never V3
    ``scanner_action``/``scanner_group``); rows without one are ``None``-safe.
    No score/rank is fabricated — ``top_opportunity_*``/``average_opportunity_*``
    stay ``None``/``0`` because V4 has no composite opportunity score.
    """
    counts: dict[str, int] = {
        "ready_now": 0,
        "waiting_confirmation": 0,
        "watch_zone": 0,
        "out_of_strategy": 0,
        "blocked": 0,
        "data_unavailable": 0,
    }
    structural_reject = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        status = str(row.get("candidate_status", "") or "").strip().upper()
        if status == READY_NOW:
            counts["ready_now"] += 1
        elif status == WAITING_CONFIRMATION:
            counts["waiting_confirmation"] += 1
        elif status == WATCH_ZONE:
            counts["watch_zone"] += 1
        elif status == OUT_OF_STRATEGY:
            counts["out_of_strategy"] += 1
        elif status == BLOCKED:
            counts["blocked"] += 1
        else:
            counts["data_unavailable"] += 1
        if str(row.get("analysis_status", "") or "").strip().lower() == (
            "structural_reject"
        ):
            structural_reject += 1
    attempted = sum(counts.values())
    return {
        "ready_count": counts["ready_now"],
        "watch_count": counts["watch_zone"],
        "wait_count": counts["waiting_confirmation"],
        "skip_count": counts["blocked"] + counts["data_unavailable"],
        "ready_now_count": counts["ready_now"],
        "waiting_confirmation_count": counts["waiting_confirmation"],
        "watch_zone_count": counts["watch_zone"],
        "out_of_strategy_count": counts["out_of_strategy"],
        "blocked_count": counts["blocked"],
        "data_unavailable_count": counts["data_unavailable"],
        "structural_reject_count": structural_reject,
        "top_opportunity_score": None,
        "average_opportunity_score": None,
        "top_opportunity_rank": None,
        "average_opportunity_rank": 0,
        "symbols_analyzed": attempted,
    }


def build_scanner_output(
    rows: list[dict[str, Any]], request: object, ai_called: int
) -> dict[str, Any]:
    """Same-shaped V4 scanner output envelope (C2b).

    Preserves the wrapper keys the persistence/observability layer reads
    (``mode``, ``timestamp``, ``symbols_scanned``, ``summary``, ``rows``) and
    stamps the locked V4 identity. ``request`` is duck-typed (only
    ``max_ai_details`` / ``feature_flags`` are read, when present).
    """
    import datetime as _dt

    flags = dict(request.feature_flags) if hasattr(request, "feature_flags") else {}
    max_ai = getattr(request, "max_ai_details", len(rows))
    return {
        "mode": "scanner",
        "timestamp": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "symbols_scanned": len(rows),
        "ai_details_limit": max_ai,
        "ai_called": int(ai_called or 0),
        "scanner_contract_version": SCANNER_V4_OUTPUT_SCHEMA_VERSION,
        "strategy_router_version": ADAPTER_VERSION,
        "portfolio_engine_version": ADAPTER_VERSION,
        "ranking_version": SCANNER_V4_SCORING_VERSION,
        "scoring_version": SCANNER_V4_SCORING_VERSION,
        "feature_version": SCANNER_V4_FEATURE_VERSION,
        "output_schema_version": SCANNER_V4_OUTPUT_SCHEMA_VERSION,
        "snapshot_version": SCANNER_V4_SNAPSHOT_VERSION,
        "safety_policy_version": SCANNER_V4_SAFETY_POLICY_VERSION,
        "macro_policy_version": SCANNER_V4_MACRO_POLICY_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "feature_flags": flags,
        "summary": scanner_summary(rows),
        "rows": rows,
    }


def blocked_ui_row(
    symbol: str,
    reason: str,
    *,
    broker_symbol: str = "",
    analysis_latency_ms: float | None = None,
    input_timestamps: dict[str, Any] | None = None,
    analysis_error: str = "",
) -> dict[str, Any]:
    """Fail-closed V4 blocked row (C2b) for the analysis/error path.

    Emits the same neutral V3-only keys + identity the adapter documents so
    downstream (filters, observability, persistence, alerts) see a well-formed
    row that is NOT an auto-trade candidate and carries no order intent.
    """
    row: dict[str, Any] = {
        "row_version": SCANNER_V4_ROW_VERSION,
        "composition_version": COMPOSITION_POLICY_VERSION,
        "scoring_version": SCANNER_V4_SCORING_VERSION,
        "feature_version": SCANNER_V4_FEATURE_VERSION,
        "output_schema_version": SCANNER_V4_OUTPUT_SCHEMA_VERSION,
        "safety_policy_version": SCANNER_V4_SAFETY_POLICY_VERSION,
        "macro_policy_version": SCANNER_V4_MACRO_POLICY_VERSION,
        "snapshot_version": SCANNER_V4_SNAPSHOT_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "pipeline_route": "scanner-v4",
        "analysis_status": ANALYSIS_OK,
        "symbol": symbol,
        "broker_symbol": broker_symbol or symbol,
        "snapshot_id": None,
        "captured_at": None,
        "capture_source": None,
        "candidate_status": DATA_UNAVAILABLE,
        "selected_side": None,
        "score_gap": None,
        "decision_cap": None,
        "final_score": None,
        "setup_score": None,
        "technical_signal_score": None,
        "evidence_score": None,
        "evidence_confidence": None,
        "execution_quality_score": None,
        "execution_readiness": None,
        "expected_effective_rr": None,
        "risk_reward_ratio": None,
        "market_regime": None,
        "macro_status": None,
        "macro_reason_codes": [],
        "safety_status": None,
        "safety_reason_codes": [],
        "gate_codes": [],
        "reason_codes": [],
        "block_codes": [],
        "entry_price": None,
        "stop_loss": None,
        "take_profit": None,
        "entry_zone": None,
        "analysis_result": {
            "status": ANALYSIS_OK,
            "technical": {"price": None, "atr_h1": None},
            "scenarios": [],
        },
        "scanner_candidate_decision": {
            "strategy": {
                "reason_codes": [],
                "score_value": None,
                "setup_score": None,
                "expected_effective_rr": None,
            },
            "reason_codes": [],
            "candidate_status": DATA_UNAVAILABLE,
            "selected_side": None,
        },
        "candidate_order_payload": None,
        "auto_trade_candidate": False,
        "scan_id": "",
        "row_id": "",
        "settings_hash": "",
        "rollout_stage": "",
        "analysis_latency_ms": analysis_latency_ms,
        "short_reason": reason,
        "analysis_error": bool(analysis_error),
        "scanner_group": "data_unavailable",
        "legacy_candidate_status": DATA_UNAVAILABLE,
    }
    for key in V3_ONLY_NEUTRAL_KEYS:
        row.setdefault(key, _V3_ONLY_NEUTRAL[key])
    if isinstance(input_timestamps, dict):
        row["input_timestamps"] = dict(input_timestamps)
    if analysis_error:
        row.pop("_analysis_error", None)
    return row


__all__ = [
    "ADAPTER_VERSION",
    "ANALYSIS_OK",
    "AUTO_TRADE_CANDIDATE_STATUSES",
    "AdapterContractError",
    "V3_ONLY_NEUTRAL_KEYS",
    "blocked_ui_row",
    "build_scanner_output",
    "pair_to_ui_row",
    "scanner_summary",
]