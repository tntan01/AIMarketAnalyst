"""Versioned routing contract for legacy, shadow and active SMC v2 scoring."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from core.smc_models import SmcScoreBreakdown
from core.smc_scorer_v2 import score_smc_v2
from core.smc_versions import SMC_SCORER_VERSION, SMC_SCORER_V2_VERSION


SMC_SHADOW_BASELINE_VERSION = SMC_SCORER_V2_VERSION

SMC_MODE_LEGACY = "legacy"
SMC_MODE_SHADOW = "shadow"
SMC_MODE_V2 = "v2"
VALID_SMC_SCORING_MODES = frozenset({
    SMC_MODE_LEGACY,
    SMC_MODE_SHADOW,
    SMC_MODE_V2,
})

SMC_V2_SHADOW_ONLY = "SMC_V2_SHADOW_ONLY"
# Backward-compatible import name retained for callers/tests from Phase 0.
SMC_V2_NOT_IMPLEMENTED = SMC_V2_SHADOW_ONLY


def normalize_smc_scoring_mode(value: object) -> str:
    """Return a supported SMC scoring mode, defaulting safely to legacy."""

    normalized = str(value or "").strip().lower()
    return (
        normalized
        if normalized in VALID_SMC_SCORING_MODES
        else SMC_MODE_LEGACY
    )


@dataclass(frozen=True, slots=True)
class SmcScoringPolicy:
    requested_mode: str
    effective_mode: str
    decision_source: str
    active_version: str
    shadow_enabled: bool
    shadow_version: str | None
    decision_impact_allowed: bool
    fallback_reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "fallback_reason_codes": list(self.fallback_reason_codes),
        }


def resolve_smc_scoring_policy(value: object) -> SmcScoringPolicy:
    """Resolve the requested scorer while preserving explicit rollback modes."""

    requested = normalize_smc_scoring_mode(value)
    v2_active = requested == SMC_MODE_V2
    return SmcScoringPolicy(
        requested_mode=requested,
        effective_mode=SMC_MODE_V2 if v2_active else SMC_MODE_LEGACY,
        decision_source=(
            SMC_SCORER_V2_VERSION if v2_active else SMC_SCORER_VERSION
        ),
        active_version=(
            SMC_SCORER_V2_VERSION if v2_active else SMC_SCORER_VERSION
        ),
        shadow_enabled=requested in {SMC_MODE_SHADOW, SMC_MODE_V2},
        shadow_version=(
            SMC_SHADOW_BASELINE_VERSION
            if requested in {SMC_MODE_SHADOW, SMC_MODE_V2}
            else None
        ),
        decision_impact_allowed=v2_active,
        fallback_reason_codes=(),
    )


def build_smc_phase0_diagnostics(
    *,
    requested_mode: object,
    smc: dict[str, Any] | None,
    technical: dict[str, Any] | None,
    active_scores: dict[str, dict[str, Any]] | None,
    market_regime: dict[str, Any] | None = None,
    precomputed_v2_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build deterministic legacy/v2-shadow diagnostics.

    ``precomputed_v2_result`` is supplied only by Scanner Tier 1 after it has
    already evaluated the canonical selector.  Reusing it keeps full-route
    survivors observationally identical while avoiding a duplicate v2 pass.
    """

    policy = resolve_smc_scoring_policy(requested_mode)
    active = _active_side_snapshots(active_scores)
    shadow: dict[str, dict[str, Any]] = {}
    if policy.shadow_enabled:
        if isinstance(precomputed_v2_result, dict):
            shadow = precomputed_v2_result
        else:
            shadow = score_smc_v2(
                smc or {},
                technical or {},
                market_regime or {},
            )

    comparison = _compare_side_snapshots(active, shadow)
    decision_input_changed = bool(
        comparison.get("direction_changed")
        or any(comparison.get("selected_zone_changed", {}).values())
        or any(comparison.get("score_delta", {}).values())
    )
    comparison["decision_input_changed"] = decision_input_changed
    comparison["decision_changed"] = bool(
        policy.decision_impact_allowed and decision_input_changed
    )
    shadow_status = (
        "v2_shadow"
        if policy.shadow_enabled
        else "disabled"
    )
    if policy.requested_mode == SMC_MODE_V2:
        shadow_status = "v2_active_with_legacy_comparison"

    decision = shadow if policy.decision_impact_allowed else active

    return {
        "contract_version": "smc-phase8-active-v2",
        "policy": policy.to_dict(),
        "legacy": active,
        "active": active,
        "shadow": shadow,
        "decision": decision,
        "comparison": comparison,
        "shadow_status": shadow_status,
    }


def _active_side_snapshots(
    active_scores: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    source = active_scores if isinstance(active_scores, dict) else {}
    result: dict[str, dict[str, Any]] = {}
    for side in ("buy", "sell"):
        score = (
            source.get(side)
            if isinstance(source.get(side), dict)
            else {}
        )
        flags = (
            score.get("smc_flags")
            if isinstance(score.get("smc_flags"), dict)
            else {}
        )
        selected_zone_id = flags.get("selected_zone_id")
        reason = str(score.get("smc_reason", "") or "")
        result[side] = {
            "smc_quality": _safe_score(score.get("smc_quality")),
            "smc_reason": reason,
            "signal_score": _safe_score(score.get("signal_score")),
            "scoring_version": SMC_SCORER_VERSION,
            "selected_zone_id": selected_zone_id,
            "selected_zone_type": flags.get("selected_zone_type"),
            "selected_zone_score": flags.get("selected_zone_score"),
            "selected_zone_quality_score": flags.get(
                "selected_zone_quality_score"
            ),
            "selected_zone_relevance_score": flags.get(
                "selected_zone_relevance_score"
            ),
            "selected_zone_setup_score": flags.get(
                "selected_zone_setup_score"
            ),
            "breakdown": SmcScoreBreakdown.from_legacy_score(
                side,
                score.get("smc_quality"),
                selected_zone_id=selected_zone_id,
                reason=reason,
            ).to_dict(),
        }
    return result


def _compare_side_snapshots(
    active: dict[str, dict[str, Any]],
    shadow: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if not shadow:
        return {
            "available": False,
            "score_delta": {},
            "legacy_smc_quality": {},
            "v2_smc_quality": {},
            "selected_zone_changed": {},
            "direction_changed": False,
            "decision_changed": False,
            "best_side_changed": False,
        }
    legacy_quality = {
        side: _safe_score(active.get(side, {}).get("smc_quality"))
        for side in ("buy", "sell")
    }
    v2_quality = {
        side: _safe_score(shadow.get(side, {}).get("smc_quality"))
        for side in ("buy", "sell")
    }
    deltas = {
        side: v2_quality[side] - legacy_quality[side]
        for side in ("buy", "sell")
    }
    active_best = _best_side_from_smc(active)
    shadow_best = _best_side_from_smc(shadow)
    return {
        "available": True,
        "legacy_smc_quality": legacy_quality,
        "v2_smc_quality": v2_quality,
        "score_delta": deltas,
        "selected_zone_changed": {
            side: (
                active.get(side, {}).get("selected_zone_id")
                != shadow.get(side, {}).get("selected_zone_id")
            )
            for side in ("buy", "sell")
        },
        "active_best_side": active_best,
        "shadow_best_side": shadow_best,
        "direction_changed": active_best != shadow_best,
        # The caller promotes this to true only when policy allows v2 to enter
        # the decision path.
        "decision_changed": False,
        "best_side_changed": active_best != shadow_best,
    }


def _best_side_from_smc(values: dict[str, dict[str, Any]]) -> str:
    buy = _safe_score(values.get("buy", {}).get("smc_quality"))
    sell = _safe_score(values.get("sell", {}).get("smc_quality"))
    if buy == sell:
        return "neutral"
    return "buy" if buy > sell else "sell"


def _safe_score(value: object) -> int:
    try:
        return max(0, min(100, int(value or 0)))
    except (TypeError, ValueError, OverflowError):
        return 0
