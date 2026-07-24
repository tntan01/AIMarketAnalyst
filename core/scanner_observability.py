"""Phase-7 scanner provenance, snapshot and deterministic replay helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any
from uuid import uuid4

from core.portfolio_models import PORTFOLIO_ENGINE_VERSION
from core.scanner_models import (
    EXECUTION_REVALIDATION_VERSION,
    SCANNER_FEATURE_VERSION,
    SCANNER_RANKING_VERSION,
    SCANNER_SCORER_VERSION,
    STRATEGY_ROUTER_VERSION,
)
from core.scanner_rollout import SCANNER_ROLLOUT_VERSION
from core.smc_scoring_contract import (
    normalize_smc_scoring_mode,
    resolve_smc_scoring_policy,
)
from core.scoring_provenance import build_scoring_provenance
from core.smc_models import SMC_DOMAIN_VERSION


SCANNER_OBSERVABILITY_VERSION = "phase7-observability-v1"
SCANNER_RUNTIME_VERSION = "scanner-runtime-v2"
SCANNER_CONTRACT_VERSION = "phase0-safety-v1"

_SENSITIVE_PARTS = (
    "api_key",
    "apikey",
    "token",
    "password",
    "secret",
    "credential",
)


@dataclass(frozen=True, slots=True)
class ScannerScanContext:
    scan_id: str
    started_at: str
    scanner_version: str
    scanner_contract_version: str
    scorer_version: str
    feature_version: str
    strategy_router_version: str
    ranking_version: str
    execution_revalidation_version: str
    portfolio_engine_version: str
    rollout_version: str
    smc_scorer_version: str
    smc_domain_version: str
    smc_scoring_mode: str
    settings_hash: str
    request_hash: str
    feature_flags: dict[str, bool]

    def to_dict(self) -> dict[str, Any]:
        return {
            "observability_version": SCANNER_OBSERVABILITY_VERSION,
            **asdict(self),
        }


def create_scan_context(
    settings: object,
    request: object,
    *,
    now: datetime | None = None,
) -> ScannerScanContext:
    timestamp = _utc(now or datetime.now(timezone.utc))
    scan_id = (
        timestamp.strftime("%Y%m%dT%H%M%S.%fZ")
        + "-"
        + uuid4().hex[:12]
    )
    request_payload = _to_plain(request)
    feature_flags = request_payload.get("feature_flags", {})
    smc_policy = resolve_smc_scoring_policy(
        request_payload.get("smc_scoring_mode")
    )
    return ScannerScanContext(
        scan_id=scan_id,
        started_at=timestamp.isoformat(timespec="milliseconds"),
        scanner_version=SCANNER_RUNTIME_VERSION,
        scanner_contract_version=SCANNER_CONTRACT_VERSION,
        scorer_version=SCANNER_SCORER_VERSION,
        feature_version=SCANNER_FEATURE_VERSION,
        strategy_router_version=STRATEGY_ROUTER_VERSION,
        ranking_version=SCANNER_RANKING_VERSION,
        execution_revalidation_version=EXECUTION_REVALIDATION_VERSION,
        portfolio_engine_version=PORTFOLIO_ENGINE_VERSION,
        rollout_version=SCANNER_ROLLOUT_VERSION,
        smc_scorer_version=smc_policy.active_version,
        smc_domain_version=SMC_DOMAIN_VERSION,
        smc_scoring_mode=normalize_smc_scoring_mode(
            request_payload.get("smc_scoring_mode")
        ),
        settings_hash=stable_hash(settings),
        request_hash=stable_hash(request_payload),
        feature_flags=(
            {
                str(key): bool(value)
                for key, value in feature_flags.items()
            }
            if isinstance(feature_flags, dict)
            else {}
        ),
    )


def stable_hash(value: object) -> str:
    """Hash canonical non-secret state for provenance comparisons."""

    canonical = json.dumps(
        redact_sensitive(_to_plain(value)),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def redact_sensitive(value: object) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            lowered = key.lower()
            if any(part in lowered for part in _SENSITIVE_PARTS):
                result[key] = "<redacted>"
            else:
                result[key] = redact_sensitive(raw_value)
        return result
    if isinstance(value, (list, tuple, set)):
        return [redact_sensitive(item) for item in value]
    return value


def row_identity(scan_id: str, symbol: object) -> str:
    normalized = "".join(
        character
        for character in str(symbol or "").upper()
        if character.isalnum()
    ) or "UNKNOWN"
    return f"{scan_id}:{normalized}"


def input_timestamps_from_candles(
    candles_by_timeframe: object,
) -> dict[str, str]:
    if not isinstance(candles_by_timeframe, dict):
        return {}
    result: dict[str, str] = {}
    for timeframe, values in candles_by_timeframe.items():
        if not isinstance(values, list) or not values:
            continue
        last = values[-1]
        raw_time = (
            getattr(last, "time", None)
            if not isinstance(last, dict)
            else last.get("time")
        )
        timestamp = _timestamp_text(raw_time)
        if timestamp:
            result[str(timeframe)] = timestamp
    return result


def attach_row_observability(
    row: dict[str, Any],
    context: ScannerScanContext,
    *,
    portfolio_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    enriched = dict(row)
    analysis = (
        enriched.get("analysis_result")
        if isinstance(enriched.get("analysis_result"), dict)
        else {}
    )
    config = (
        enriched.get("auto_trade_config")
        if isinstance(enriched.get("auto_trade_config"), dict)
        else {}
    )
    data_quality = (
        analysis.get("data_quality")
        if isinstance(analysis.get("data_quality"), dict)
        else {}
    )
    final_score = (
        analysis.get("final_score_detail")
        if isinstance(analysis.get("final_score_detail"), dict)
        else {}
    )
    trade_gate = (
        analysis.get("trade_gate")
        if isinstance(analysis.get("trade_gate"), dict)
        else {}
    )
    smc_scoring = (
        analysis.get("smc_scoring")
        if isinstance(analysis.get("smc_scoring"), dict)
        else {}
    )
    candidate = (
        enriched.get("scanner_candidate_decision")
        if isinstance(enriched.get("scanner_candidate_decision"), dict)
        else {}
    )
    ranking = (
        enriched.get("ranking_contract")
        if isinstance(enriched.get("ranking_contract"), dict)
        else {}
    )
    row_id = str(
        enriched.get("row_id")
        or row_identity(context.scan_id, enriched.get("symbol"))
    )
    observability = {
        "observability_version": SCANNER_OBSERVABILITY_VERSION,
        "scan_id": context.scan_id,
        "row_id": row_id,
        "settings_hash": context.settings_hash,
        "request_hash": context.request_hash,
        "scanner_version": context.scanner_version,
        "scanner_contract_version": context.scanner_contract_version,
        "scorer_version": context.scorer_version,
        "feature_version": context.feature_version,
        "strategy_router_version": context.strategy_router_version,
        "ranking_version": context.ranking_version,
        "execution_revalidation_version": (
            context.execution_revalidation_version
        ),
        "portfolio_engine_version": context.portfolio_engine_version,
        "rollout_version": context.rollout_version,
        "smc_scorer_version": context.smc_scorer_version,
        "smc_domain_version": context.smc_domain_version,
        "smc_scoring_mode": context.smc_scoring_mode,
        "rollout_stage": enriched.get("rollout_stage"),
        "backtest_config_id": str(config.get("config_id", "") or ""),
        "input_timestamps": dict(
            enriched.get("input_timestamps", {})
            if isinstance(enriched.get("input_timestamps"), dict)
            else {}
        ),
        "data_freshness": {
            "macro": data_quality.get("macro_freshness"),
            "warning": data_quality.get("warning"),
            "spread_status": data_quality.get("spread_status"),
            "terminal_connected": data_quality.get("terminal_connected"),
            "broker_logged_in": data_quality.get("broker_logged_in"),
            "analysis_timestamp": analysis.get("timestamp"),
        },
        "selected_branch": enriched.get("auto_trade_branch"),
        "selected_side": enriched.get("selected_side"),
        "score_inputs": {
            "buy_score": enriched.get("buy_score"),
            "sell_score": enriched.get("sell_score"),
            "setup_score": enriched.get("setup_score"),
            "score_gap": enriched.get("score_gap"),
            "min_score": (
                candidate.get("strategy", {}).get("min_score")
                if isinstance(candidate.get("strategy"), dict)
                else None
            ),
            "effective_rr": enriched.get("expected_effective_rr"),
            "min_rr": (
                candidate.get("strategy", {}).get("min_rr")
                if isinstance(candidate.get("strategy"), dict)
                else None
            ),
        },
        "weighted_components": {
            "final_score": final_score,
            "ranking": ranking.get("breakdown", {}),
        },
        "smc_scoring": smc_scoring,
        "gate_results": {
            "analysis_trade_gate": trade_gate,
            "strategy": candidate.get("strategy", {}),
            "execution": candidate.get("execution", {}),
        },
        "portfolio_state": dict(portfolio_state or {}),
        "final_candidate_decision": candidate,
    }
    enriched.update({
        "scan_id": context.scan_id,
        "row_id": row_id,
        "settings_hash": context.settings_hash,
        "scorer_version": context.scorer_version,
        "feature_version": context.feature_version,
        "smc_scorer_version": context.smc_scorer_version,
        "smc_scoring_mode": context.smc_scoring_mode,
        "scoring_provenance": build_scoring_provenance(
            context.smc_scoring_mode
        ),
        "observability": observability,
    })
    order_payload = enriched.get("candidate_order_payload")
    if isinstance(order_payload, dict):
        order_payload = dict(order_payload)
        order_payload.update({
            "scan_id": context.scan_id,
            "row_id": row_id,
            "settings_hash": context.settings_hash,
            "backtest_config_id": observability["backtest_config_id"],
            "scorer_version": context.scorer_version,
            "ranking_version": context.ranking_version,
            "rollout_version": context.rollout_version,
            "rollout_stage": enriched.get("rollout_stage"),
            "smc_scorer_version": context.smc_scorer_version,
            "smc_domain_version": context.smc_domain_version,
            "smc_scoring_mode": context.smc_scoring_mode,
        })
        enriched["candidate_order_payload"] = order_payload
    return enriched


def build_analysis_document(
    row: dict[str, Any],
    context: ScannerScanContext | dict[str, Any],
) -> dict[str, Any]:
    context_payload = (
        context.to_dict()
        if isinstance(context, ScannerScanContext)
        else dict(context)
    )
    summary = {
        key: value
        for key, value in row.items()
        if key != "analysis_result"
    }
    return {
        "observability_version": SCANNER_OBSERVABILITY_VERSION,
        "scan_context": redact_sensitive(context_payload),
        "symbol": row.get("symbol"),
        "row_summary": redact_sensitive(summary),
        "analysis_result": redact_sensitive(row.get("analysis_result")),
        "auto_trade_config": redact_sensitive(row.get("auto_trade_config")),
        "candidate_decision": redact_sensitive(
            row.get("scanner_candidate_decision")
        ),
        "ranking_contract": redact_sensitive(row.get("ranking_contract")),
        "observability": redact_sensitive(row.get("observability")),
    }


def replay_candidate_decision(document: dict[str, Any]) -> dict[str, Any]:
    """Replay Strategy Router/Candidate Engine and compare saved decisions."""

    if not isinstance(document, dict):
        return {
            "replayable": False,
            "reason_codes": ["REPLAY_DOCUMENT_INVALID"],
        }
    row = document.get("row_summary")
    analysis = document.get("analysis_result")
    if not isinstance(row, dict) or not isinstance(analysis, dict):
        return {
            "replayable": False,
            "reason_codes": ["REPLAY_INPUT_MISSING"],
        }
    reconstructed = dict(row)
    reconstructed["analysis_result"] = analysis
    config = document.get("auto_trade_config")
    config = config if isinstance(config, dict) and config else None

    from core.scanner_candidate_engine import evaluate_scanner_candidate
    from core.scanner_ranking_engine import rank_scanner_rows

    scan_context = document.get("scan_context")
    replay_time = None
    if isinstance(scan_context, dict):
        replay_time = _parse_datetime(scan_context.get("started_at"))
    decision = evaluate_scanner_candidate(
        reconstructed,
        config,
        now=replay_time,
    )
    replayed = decision.to_dict()
    reconstructed.update({
        "candidate_status": decision.status,
        "selected_side": decision.selected_side,
        "auto_trade_branch": decision.branch,
        "strategy_config_status": decision.strategy.config_status,
        "setup_score": decision.setup_score,
        "expected_effective_rr": decision.strategy.expected_effective_rr,
        "execution_ready": decision.execution_ready,
        "trade_allowed": decision.trade_allowed,
        "scanner_candidate_decision": replayed,
    })
    replayed_row = rank_scanner_rows([reconstructed])[0]
    saved = document.get("candidate_decision")
    saved = saved if isinstance(saved, dict) else {}
    saved_ranking = document.get("ranking_contract")
    saved_ranking = saved_ranking if isinstance(saved_ranking, dict) else {}
    reason_match = set(replayed.get("reason_codes", [])) == set(
        saved.get("reason_codes", [])
    )
    comparisons = {
        "status_match": replayed.get("status") == saved.get("status"),
        "branch_match": replayed.get("branch") == saved.get("branch"),
        "side_match": replayed.get("selected_side") == saved.get("selected_side"),
        "reason_codes_match": reason_match,
        "opportunity_rank_match": (
            replayed_row.get("opportunity_rank")
            == saved_ranking.get("opportunity_rank")
        ),
    }
    return {
        "replayable": True,
        "match": all(comparisons.values()),
        "comparisons": comparisons,
        "saved_decision": saved,
        "replayed_decision": replayed,
        "saved_opportunity_rank": saved_ranking.get("opportunity_rank"),
        "replayed_opportunity_rank": replayed_row.get("opportunity_rank"),
        "reason_codes": (
            []
            if all(comparisons.values())
            else ["REPLAY_DECISION_MISMATCH"]
        ),
    }


def _to_plain(value: object) -> dict[str, Any]:
    if is_dataclass(value) and not isinstance(value, type):
        raw = asdict(value)
    elif isinstance(value, dict):
        raw = value
    elif hasattr(value, "__dict__"):
        raw = vars(value)
    else:
        return {"value": str(value)}
    return {
        str(key): _plain_value(item)
        for key, item in raw.items()
    }


def _plain_value(value: object) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            str(key): _plain_value(item)
            for key, item in asdict(value).items()
        }
    if isinstance(value, dict):
        return {
            str(key): _plain_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_plain_value(item) for item in value]
    if isinstance(value, datetime):
        return _utc(value).isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _timestamp_text(value: object) -> str:
    if isinstance(value, datetime):
        return _utc(value).isoformat()
    if isinstance(value, str):
        return value
    return ""


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
