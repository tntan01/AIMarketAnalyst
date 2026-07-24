"""Canonical Phase-8 scoring provenance shared by runtime consumers."""

from __future__ import annotations

from typing import Any

from core.scanner_models import (
    SCANNER_FEATURE_VERSION,
    SCANNER_SCORER_VERSION,
    SETUP_SCORE_METRIC,
)
from core.smc_models import SMC_DOMAIN_VERSION
from core.smc_scoring_contract import resolve_smc_scoring_policy


SCORING_PROVENANCE_VERSION = "phase8-scoring-provenance-v1"


def build_scoring_provenance(smc_scoring_mode: object) -> dict[str, Any]:
    """Return the immutable version identity for one analysis decision."""

    policy = resolve_smc_scoring_policy(smc_scoring_mode)
    return {
        "provenance_version": SCORING_PROVENANCE_VERSION,
        "score_metric": SETUP_SCORE_METRIC,
        "scanner_scorer_version": SCANNER_SCORER_VERSION,
        "scanner_feature_version": SCANNER_FEATURE_VERSION,
        "smc_scorer_version": policy.active_version,
        "smc_domain_version": SMC_DOMAIN_VERSION,
        "smc_scoring_mode": policy.requested_mode,
        "smc_decision_source": policy.decision_source,
    }


def normalize_scoring_provenance(
    value: object,
    *,
    fallback_mode: object = "v2",
) -> dict[str, Any]:
    """Normalize a payload without allowing missing fields to look current."""

    fallback = build_scoring_provenance(fallback_mode)
    if not isinstance(value, dict):
        return fallback
    return {
        key: value.get(key, default)
        for key, default in fallback.items()
    }
