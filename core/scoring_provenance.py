"""Canonical Phase-8 scoring provenance shared by runtime consumers."""

from __future__ import annotations

from typing import Any

from core.scanner_models import (
    SCANNER_FEATURE_VERSION,
    SCANNER_SCORER_VERSION,
    SETUP_SCORE_METRIC,
)
from core.smc_models import SMC_DOMAIN_VERSION
from core.smc_versions import SMC_SCORER_VERSION


SCORING_PROVENANCE_VERSION = "phase8-scoring-provenance-v1"

_SCORING_PROVENANCE_FIELDS = (
    "provenance_version",
    "score_metric",
    "scanner_scorer_version",
    "scanner_feature_version",
    "smc_scorer_version",
    "smc_domain_version",
)


def build_scoring_provenance() -> dict[str, Any]:
    """Return the immutable version identity for one analysis decision.

    Provenance is metadata only: it carries the single canonical scorer
    version and can never route a decision to another scorer.
    """

    return {
        "provenance_version": SCORING_PROVENANCE_VERSION,
        "score_metric": SETUP_SCORE_METRIC,
        "scanner_scorer_version": SCANNER_SCORER_VERSION,
        "scanner_feature_version": SCANNER_FEATURE_VERSION,
        "smc_scorer_version": SMC_SCORER_VERSION,
        "smc_domain_version": SMC_DOMAIN_VERSION,
    }


def normalize_scoring_provenance(value: object) -> dict[str, Any]:
    """Accept only the exact executable V3 identity; otherwise fail closed.

    This compatibility normalizer is intentionally *not* a V4 reader.  Missing,
    blank, incorrectly typed, foreign, or target-V4 fields become a fully blank
    identity so the V3 row adapter cannot relabel an untrusted payload. New V3
    artifacts must use :func:`build_scoring_provenance`; Scanner V4 payloads use
    the strict validator in ``core.scanner_v4_models``.
    """

    rejected = {key: "" for key in _SCORING_PROVENANCE_FIELDS}
    if type(value) is not dict:
        return rejected
    if set(value) != set(_SCORING_PROVENANCE_FIELDS):
        return rejected
    expected = build_scoring_provenance()
    if any(
        type(value.get(key)) is not str or value.get(key) != expected[key]
        for key in _SCORING_PROVENANCE_FIELDS
    ):
        return rejected
    return {key: value[key] for key in _SCORING_PROVENANCE_FIELDS}
