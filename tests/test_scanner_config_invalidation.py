"""Scanner config invalidation + migration (Bước 09, target-only).

Mục 9E: bump schema/fingerprint; config legacy / thiếu version / fingerprint
mismatch → ``VERSION_MISMATCH`` + ``backtest=False``; chỉ config mới + evidence
calibration/validation mới được activate.  Trade filter đọc selected-side
``setup_score`` duy nhất, từ chối mọi legacy scored field.
"""

from __future__ import annotations

import pytest

from core.reason_codes import (
    SCANNER_CONFIG_NOT_ACTIVATABLE,
    SCANNER_FORBIDDEN_SCORED_FIELD,
    SCANNER_LEGACY_V3_AUDIT_ONLY,
    SCANNER_VERSION_MISSING,
    SCANNER_VERSION_MISMATCH,
)
from core.scanner_backtest_contract import SCANNER_BACKTEST_CONFIG_SCHEMA_VERSION
from core.scanner_config_invalidation import (
    FORBIDDEN_V3_SCORED_INPUTS,
    ScannerConfigError,
    compute_config_fingerprint,
    filter_by_selected_side_setup,
    validate_v4_backtest_config,
)

EVIDENCE = {"calibration_report_version": "scanner-v4-calibration-report-v1", "status": "STANDALONE_OK"}


def _config(**overrides) -> dict[str, object]:
    base = {
        "config_schema_version": SCANNER_BACKTEST_CONFIG_SCHEMA_VERSION,
        "scorer_version": "scanner-v4",
        "feature_version": "scanner-features-v4",
        "output_schema_version": "scanner-output-v4",
        "snapshot_version": "scanner-pair-snapshot-v4",
        "safety_policy_version": "scanner-safety-policy-v4",
        "macro_policy_version": "scanner-macro-policy-v4",
        "threshold_policy_version": "scanner-threshold-policy-v4",
        "backtest_contract_version": "scanner-backtest-contract-v4",
        "candidate_ledger_version": "scanner-v4-candidate-ledger-v4",
        "validation_version": "scanner-v4-calibration-report-v1",
    }
    base.update(overrides)
    return base


class TestEmptyConfig:
    def test_non_dict_is_not_activatable(self):
        verdict = validate_v4_backtest_config(None)  # type: ignore[arg-type]
        assert verdict.activatable is False
        assert verdict.backtest is False

    def test_empty_config_missing_version(self):
        verdict = validate_v4_backtest_config({})
        assert verdict.activatable is False
        assert verdict.backtest is False
        assert SCANNER_VERSION_MISSING in verdict.reason_codes


class TestV3Rejected:
    def test_v3_schema_bump_is_version_mismatch(self):
        config = _config(config_schema_version=SCANNER_BACKTEST_CONFIG_SCHEMA_VERSION - 1)
        verdict = validate_v4_backtest_config(config, calibration_evidence=EVIDENCE)
        assert verdict.activatable is False
        assert verdict.backtest is False
        assert SCANNER_VERSION_MISMATCH in verdict.reason_codes
        assert SCANNER_LEGACY_V3_AUDIT_ONLY in verdict.reason_codes

    def test_legacy_v3_scorer_version_is_version_mismatch(self):
        config = _config(scorer_version="scanner-v3")
        verdict = validate_v4_backtest_config(config, calibration_evidence=EVIDENCE)
        assert verdict.activatable is False
        assert verdict.backtest is False
        assert SCANNER_VERSION_MISMATCH in verdict.reason_codes
        assert SCANNER_LEGACY_V3_AUDIT_ONLY in verdict.reason_codes

    def test_legacy_smc_v2_is_version_mismatch(self):
        config = _config(scorer_version="smc-v2")
        verdict = validate_v4_backtest_config(config, calibration_evidence=EVIDENCE)
        assert verdict.activatable is False
        assert verdict.backtest is False
        assert SCANNER_VERSION_MISMATCH in verdict.reason_codes


class TestSchemaVersion:
    def test_wrong_schema_version_is_version_mismatch(self):
        config = _config(config_schema_version=SCANNER_BACKTEST_CONFIG_SCHEMA_VERSION + 1)
        verdict = validate_v4_backtest_config(config, calibration_evidence=EVIDENCE)
        assert verdict.activatable is False
        assert verdict.backtest is False
        assert SCANNER_VERSION_MISMATCH in verdict.reason_codes

    def test_non_int_schema_version_is_version_mismatch(self):
        config = _config(config_schema_version="v10")  # type: ignore[dict-item]
        verdict = validate_v4_backtest_config(config, calibration_evidence=EVIDENCE)
        assert verdict.activatable is False
        assert SCANNER_VERSION_MISMATCH in verdict.reason_codes


class TestFingerprint:
    def test_compute_is_deterministic(self):
        config = _config()
        assert compute_config_fingerprint(config) == compute_config_fingerprint(config)

    def test_fingerprint_ignores_scored_content(self):
        a = _config(min_setup_score=10)
        b = _config(min_setup_score=99)
        assert compute_config_fingerprint(a) == compute_config_fingerprint(b)

    def test_fingerprint_changes_with_identity(self):
        a = _config()
        b = _config(scorer_version="scanner-v4-hotfix")
        assert compute_config_fingerprint(a) != compute_config_fingerprint(b)

    def test_fingerprint_mismatch_blocks_activation(self):
        config = _config()
        verdict = validate_v4_backtest_config(
            config,
            calibration_evidence=EVIDENCE,
            known_fingerprint=compute_config_fingerprint(_config(scorer_version="other")),
        )
        assert verdict.activatable is False
        assert verdict.backtest is False
        assert SCANNER_VERSION_MISMATCH in verdict.reason_codes

    def test_matching_fingerprint_with_evidence_activates(self):
        config = _config()
        fingerprint = compute_config_fingerprint(config)
        verdict = validate_v4_backtest_config(config, calibration_evidence=EVIDENCE, known_fingerprint=fingerprint)
        assert verdict.activatable is True
        assert verdict.backtest is True
        assert verdict.fingerprint == fingerprint


class TestIdentityBindings:
    def test_no_evidence_activates_under_default_policy(self):
        # Bước 12 §9.2: calibration evidence is NOT mandatory; the fingerprint
        # is bound even without a caller-supplied reference fingerprint.
        config = _config()
        verdict = validate_v4_backtest_config(config)
        assert verdict.activatable is True
        assert verdict.backtest is True
        assert verdict.fingerprint == compute_config_fingerprint(config)

    def test_non_dict_evidence_does_not_block_default_policy(self):
        config = _config()
        verdict = validate_v4_backtest_config(config, calibration_evidence="not-a-dict")  # type: ignore[arg-type]
        assert verdict.activatable is True
        assert verdict.backtest is True

    def test_missing_identity_field_never_activates(self):
        # §9.2: identity/fingerprint is bound even without caller fingerprint:
        # missing any identity key → not a byte-exact config, fail closed.
        config = _config()
        del config["threshold_policy_version"]
        verdict = validate_v4_backtest_config(config, calibration_evidence=EVIDENCE)
        assert verdict.activatable is False
        assert verdict.backtest is False
        assert SCANNER_CONFIG_NOT_ACTIVATABLE in verdict.reason_codes

    def test_slight_identity_drift_is_still_a_mismatch(self):
        # Changing an identity field WITHOUT bumping the schema must be refused —
        # this is what forces a schema/fingerprint bump on any real change.  The
        # mismatch is caught via the known (registered) fingerprint.
        known = compute_config_fingerprint(_config())
        drifted = _config(safety_policy_version="scanner-safety-policy-v4-b")
        verdict = validate_v4_backtest_config(
            drifted,
            calibration_evidence=EVIDENCE,
            known_fingerprint=known,
        )
        assert verdict.activatable is False
        assert verdict.backtest is False
        assert SCANNER_VERSION_MISMATCH in verdict.reason_codes

    def test_full_with_evidence_activates(self):
        config = _config()
        verdict = validate_v4_backtest_config(config, calibration_evidence=EVIDENCE)
        assert verdict.activatable is True
        assert verdict.backtest is True
        assert verdict.reason_codes == ()

    def test_verdict_to_dict_shape(self):
        payload = validate_v4_backtest_config(_config()).to_dict()
        assert set(payload) == {"activatable", "backtest", "reason_codes", "fingerprint"}


class TestSelectedSideFilter:
    def _row(self, side: str = "buy", setup: int = 40, **extra) -> dict[str, object]:
        row: dict[str, object] = {"selected_side": side, "setup_score": setup}
        row.update(extra)
        return row

    def test_filters_by_selected_side_setup_only(self):
        rows = [self._row("buy", 45), self._row("buy", 35), self._row("sell", 50), self._row("buy", 60)]
        kept = filter_by_selected_side_setup(rows, min_setup_score=40)
        assert [r["setup_score"] for r in kept] == [45, 50, 60]

    def test_rejects_top_level_final_score(self):
        rows = [self._row(setup=45, final_score=80)]
        assert "final_score" in FORBIDDEN_V3_SCORED_INPUTS
        with pytest.raises(ScannerConfigError) as exc:
            filter_by_selected_side_setup(rows, min_setup_score=40)
        assert exc.value.code == SCANNER_FORBIDDEN_SCORED_FIELD

    def test_rejects_legacy_fields(self):
        for legacy in ("total", "best_score", "signal_score", "opportunity_score",
                       "scanner_action", "scanner_group", "expected_effective_rr",
                       "risk_condition", "macro_alignment"):
            rows = [self._row(setup=45, **{legacy: 0.5})]
            with pytest.raises(ScannerConfigError) as exc:
                filter_by_selected_side_setup(rows, min_setup_score=40)
            assert exc.value.code == SCANNER_FORBIDDEN_SCORED_FIELD, legacy

    def test_requires_selected_side(self):
        rows = [{"setup_score": 45}]
        with pytest.raises(ScannerConfigError) as exc:
            filter_by_selected_side_setup(rows, min_setup_score=40)
        assert exc.value.code == SCANNER_CONFIG_NOT_ACTIVATABLE

    def test_non_dict_row_refused(self):
        rows = ["v3-row"]  # type: ignore[list-item]
        with pytest.raises(ScannerConfigError):
            filter_by_selected_side_setup(rows, min_setup_score=40)

    def test_does_not_read_side_specific_scores_from_other_side(self):
        # A row keyed only by selected_side reads exactly that side's setup_score.
        rows = [self._row("buy", 40, sell_setup_score=80)]
        kept = filter_by_selected_side_setup(rows, min_setup_score=40)
        assert len(kept) == 1