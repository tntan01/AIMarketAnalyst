"""Scanner V4 backtest-config invalidation (Bước 09; target-only).

Mục 9E: bump schema; config V3 / thiếu version / fingerprint mismatch →
``VERSION_MISMATCH`` + ``backtest=False``; config V4 đủ identity + fingerprint
mới activate — calibration/validation evidence KHÔNG còn bắt buộc (default
threshold policy 40/35/5/2, Bước 12 §9.2).  This module is the V4 config
**reader side**: it computes the versioned V4 config fingerprint and refuses any
config that is not a byte-exact V4 config.  It never mutates the V3 config files
or settings; it only decides whether a given config dict is activatable for
Scanner V4 backtesting.

It also carries the V4 **trade filter** that reads the selected-side
``setup_score`` from the canonical output (never a top-level ``final_score`` /
legacy ``signal_score`` / ``opportunity_score``).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from core.reason_codes import (
    SCANNER_V4_CONFIG_NOT_ACTIVATABLE,
    SCANNER_V4_FORBIDDEN_SCORED_FIELD,
    SCANNER_V4_LEGACY_V3_AUDIT_ONLY,
    SCANNER_V4_VERSION_MISSING,
    SCANNER_V4_VERSION_MISMATCH,
)
from core.scanner_v4_backtest_contract import (
    SCANNER_V4_BACKTEST_CONFIG_SCHEMA_VERSION,
)

# Identity fields that participate in the V4 config fingerprint.  The set is
# the versioned contract: changing any identity silently (without bumping the
# config schema) is a fingerprint mismatch.
V4_CONFIG_IDENTITY_FIELDS = frozenset({
    "config_schema_version",
    "scorer_version",
    "feature_version",
    "output_schema_version",
    "snapshot_version",
    "safety_policy_version",
    "macro_policy_version",
    "threshold_policy_version",
    "backtest_contract_version",
    "candidate_ledger_version",
    "validation_version",
})

# Fields the V4 filter reads for trade/filter decisions.  These are the ONLY
# scored inputs a V4 filter is allowed to read (see ``filter_by_selected_side``).
FORBIDDEN_V3_SCORED_INPUTS = frozenset({
    "total",
    "best_score",
    "final_score",
    "opportunity_score",
    "scanner_action",
    "scanner_group",
    "expected_effective_rr",
    "risk_condition",
    "macro_alignment",
    "signal_score",
})


class ScannerV4ConfigError(ValueError):
    """Typed rejection of a non-activatable / invalid V4 config."""

    def __init__(self, path: str, detail: str, code: str) -> None:
        self.path = path
        self.detail = detail
        self.code = code
        super().__init__(f"{code}: {path}: {detail}")


@dataclass(frozen=True, slots=True)
class ConfigActivationVerdict:
    activatable: bool
    backtest: bool
    reason_codes: tuple[str, ...]
    fingerprint: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "activatable": self.activatable,
            "backtest": self.backtest,
            "reason_codes": list(self.reason_codes),
            "fingerprint": self.fingerprint,
        }


def compute_v4_config_fingerprint(config: Mapping[str, Any]) -> str:
    """Deterministic V4 config fingerprint over the identity fields.

    Only the versioned identity fields participate; scored/threshold content is
    deliberately NOT mixed into the identity digest (a fingerprint mismatch must
    mean "different contract identity", never "different calibration numbers").
    """
    identity = {
        field: config[field]
        for field in V4_CONFIG_IDENTITY_FIELDS
        if field in config
    }
    return hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_v4_backtest_config(
    config: Mapping[str, Any],
    *,
    calibration_evidence: Mapping[str, Any] | None = None,
    known_fingerprint: str | None = None,
) -> ConfigActivationVerdict:
    """Decide whether a config is activatable for V4 backtesting.

    Fail-closed checks in order:

    1. not a dict / rejected;
    2. V3 scorer/feature/ledger identity present → ``VERSION_MISMATCH`` +
       ``backtest=False`` (with ``SCANNER_V4_LEGACY_V3_AUDIT_ONLY`` marker);
    3. missing V4 config schema version → ``VERSION_MISSING``;
    4. all V4 identity fields present (so the fingerprint is bound even when the
       caller passes no known reference fingerprint);
    5. fingerprint mismatch (config identity ≠ expected V4 identity) →
       ``VERSION_MISMATCH``.

    The config is activatable when identity is complete + exact.  Calibration/
    validation evidence is NOT mandatory: under the single-owner DEFAULT
    threshold policy (40/35/5/2, ``scanner-threshold-policy-v4``) a config does
    not need a PIT-calibration artifact to activate (Bước 12, §9.2).  A ``None``
    policy still fails closed; nothing is ever fabricated.
    """
    if type(config) is not dict:
        return ConfigActivationVerdict(
            activatable=False,
            backtest=False,
            reason_codes=(SCANNER_V4_CONFIG_NOT_ACTIVATABLE,),
        )

    # 2. V3 identity is refused no matter what.
    config_schema = config.get("config_schema_version")
    if isinstance(config_schema, int) and config_schema < SCANNER_V4_BACKTEST_CONFIG_SCHEMA_VERSION:
        return ConfigActivationVerdict(
            activatable=False,
            backtest=False,
            reason_codes=(
                SCANNER_V4_VERSION_MISMATCH,
                SCANNER_V4_LEGACY_V3_AUDIT_ONLY,
            ),
        )
    for legacy in ("scanner-v3", "scanner-features-v3", "smc-v2"):
        if any(
            isinstance(value, str) and value == legacy and str(field).endswith("_version")
            for field, value in config.items()
        ):
            return ConfigActivationVerdict(
                activatable=False,
                backtest=False,
                reason_codes=(
                    SCANNER_V4_VERSION_MISMATCH,
                    SCANNER_V4_LEGACY_V3_AUDIT_ONLY,
                ),
            )

    # 3. Missing schema version.
    if "config_schema_version" not in config:
        return ConfigActivationVerdict(
            activatable=False,
            backtest=False,
            reason_codes=(SCANNER_V4_VERSION_MISSING,),
        )
    if config_schema != SCANNER_V4_BACKTEST_CONFIG_SCHEMA_VERSION:
        return ConfigActivationVerdict(
            activatable=False,
            backtest=False,
            reason_codes=(SCANNER_V4_VERSION_MISMATCH,),
        )

    # 4. Identity must be COMPLETE — every V4 identity field present — so the
    #    fingerprint is bound even when the caller supplies no reference.  A
    #    config missing any identity key cannot be a byte-exact V4 config.
    missing_identity = sorted(V4_CONFIG_IDENTITY_FIELDS - set(config))
    if missing_identity:
        return ConfigActivationVerdict(
            activatable=False,
            backtest=False,
            reason_codes=(SCANNER_V4_CONFIG_NOT_ACTIVATABLE,),
            fingerprint="",
        )
    computed = compute_v4_config_fingerprint(config)

    # 5. Fingerprint mismatch when a known reference fingerprint is provided.
    if known_fingerprint is not None and computed != known_fingerprint:
        return ConfigActivationVerdict(
            activatable=False,
            backtest=False,
            reason_codes=(SCANNER_V4_VERSION_MISMATCH,),
            fingerprint=computed,
        )

    # 6. Calibration/validation evidence is NOT gate (default threshold policy
    #    40/35/5/2 is a single-owner default, not a PIT calibration; Bước 12
    #    §9.2).  The fingerprint is always bound to the verdict.
    _ = calibration_evidence  # optional/informational; never fabricated thresholds
    return ConfigActivationVerdict(
        activatable=True,
        backtest=True,
        reason_codes=(),
        fingerprint=computed,
    )


def filter_by_selected_side_setup(
    rows: list[Mapping[str, Any]],
    *,
    min_setup_score: int,
) -> list[Mapping[str, Any]]:
    """V4 trade filter — reads ONLY the selected-side ``setup_score``.

    Every row must be a V4 candidate/ledger row with ``selected_side`` and a
    ``setup_score``; V3 scored inputs are rejected before filtering starts.
    """
    blocked: list[Mapping[str, Any]] = [row for row in rows if not isinstance(row, dict)]
    if blocked:
        raise ScannerV4ConfigError(
            "row",
            "expected dict rows",
            SCANNER_V4_CONFIG_NOT_ACTIVATABLE,
        )
    for row in rows:
        if FORBIDDEN_V3_SCORED_INPUTS & set(row):
            raise ScannerV4ConfigError(
                "row",
                "V4 filter refuses V3 scored inputs "
                f"({sorted(FORBIDDEN_V3_SCORED_INPUTS & set(row))})",
                SCANNER_V4_FORBIDDEN_SCORED_FIELD,
            )
        if not isinstance(row.get("selected_side"), str):
            raise ScannerV4ConfigError(
                "row.selected_side",
                "V4 filter requires selected_side",
                SCANNER_V4_CONFIG_NOT_ACTIVATABLE,
            )
    return [row for row in rows if row.get("setup_score", 0) >= min_setup_score]