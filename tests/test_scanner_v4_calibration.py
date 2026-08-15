"""Scanner V4 calibration reproducibility (Bước 09, target-only).

Mục 9D: khóa dataset manifest + point-in-time boundary, chia train/OOS, chạy
walk-forward.  When the repository has NO historical PIT dataset, the harness
MUST record ``INSUFFICIENT_SAMPLE`` and keep recommended thresholds ``None`` —
fail-closed, never inventing production numbers.  The tests prove the report is
byte-reproducible from (manifest, rows) and that sample-count integrity is
enforced.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.reason_codes import SCANNER_V4_CALIBRATION_INSUFFICIENT
from core.scanner_v4_calibration import (
    SCANNER_V4_CALIBRATION_MANIFEST_VERSION,
    SCANNER_V4_CALIBRATION_REPORT_VERSION,
    CalibrationInput,
    CalibrationManifest,
    CalibrationReport,
    make_empty_calibration_manifest,
    run_calibration,
)

NOW = datetime(2026, 8, 13, 12, 0, 0, tzinfo=timezone.utc)
PIT = NOW - timedelta(days=60)


def _manifest(**overrides) -> CalibrationManifest:
    base = dict(
        manifest_version=SCANNER_V4_CALIBRATION_MANIFEST_VERSION,
        dataset_id="dataset-test",
        pit_boundary=PIT,
        minimum_required_rows=50,
        thresholds_being_calibrated=(
            "technical_floor",
            "setup_floor",
            "min_risk_reward",
        ),
    )
    base.update(overrides)
    return CalibrationManifest(**base)


def _rows(n: int, *, outcome: float = 1.0, observed: datetime = NOW) -> tuple[CalibrationInput, ...]:
    return tuple(
        CalibrationInput(
            observed_at=observed - timedelta(hours=i),
            symbol="XAUUSD" if i % 2 else "EURUSD",
            regime="trending_up",
            side="buy" if i % 2 else "sell",
            candidate_status="READY_NOW",
            outcome_r=(None if i % 3 == 0 else (-0.5 if i % 7 == 1 else outcome)),
            technical_signal_score=50 + i,
            setup_score=60 + i,
        )
        for i in range(n)
    )


class TestInsufficientSample:
    def test_empty_rows_reports_insufficient(self):
        report = run_calibration(_manifest(), ())
        assert report.status == "INSUFFICIENT_SAMPLE"
        assert SCANNER_V4_CALIBRATION_INSUFFICIENT in report.reason_codes
        assert all(value is None for value in report.recommended_thresholds.values())

    def test_below_minimum_reports_insufficient(self):
        report = run_calibration(_manifest(minimum_required_rows=50), _rows(10))
        assert report.status == "INSUFFICIENT_SAMPLE"
        assert SCANNER_V4_CALIBRATION_INSUFFICIENT in report.reason_codes
        assert all(value is None for value in report.recommended_thresholds.values())

    def test_no_realized_outcomes_reports_insufficient(self):
        rows = tuple(
            CalibrationInput(
                observed_at=NOW - timedelta(hours=i),
                symbol="XAUUSD",
                regime="range",
                side="buy",
                candidate_status="WATCH_ZONE",
                outcome_r=None,
                technical_signal_score=60,
                setup_score=55,
            )
            for i in range(60)
        )
        report = run_calibration(_manifest(), rows)
        assert report.status == "INSUFFICIENT_SAMPLE"
        assert all(value is None for value in report.recommended_thresholds.values())

    def test_default_empty_manifest_is_the_repo_state(self):
        report = run_calibration(make_empty_calibration_manifest(), ())
        assert report.status == "INSUFFICIENT_SAMPLE"
        assert SCANNER_V4_CALIBRATION_INSUFFICIENT in report.reason_codes
        # No production threshold is ever emitted.
        assert all(value is None for value in report.recommended_thresholds.values())


class TestReproducibility:
    def test_same_input_bytes_identical_report(self):
        rows = _rows(60)
        a = run_calibration(_manifest(), rows)
        b = run_calibration(_manifest(), rows)
        assert a.to_dict() == b.to_dict()
        assert a.fingerprint(rows) == b.fingerprint(rows)

    def test_order_of_rows_does_not_change_report(self):
        rows = list(_rows(60))
        a = run_calibration(_manifest(), rows)
        b = run_calibration(_manifest(), tuple(reversed(rows)))
        assert a.to_dict() == b.to_dict()

    def test_manifest_change_changes_fingerprint(self):
        rows = _rows(60)
        a = run_calibration(_manifest(), rows)
        b = run_calibration(_manifest(minimum_required_rows=49), rows)
        assert a.manifest_fingerprint != b.manifest_fingerprint

    def test_report_version_locked(self):
        report = run_calibration(_manifest(), ())
        assert report.report_version == SCANNER_V4_CALIBRATION_REPORT_VERSION


class TestSufficientSample:
    def test_enough_rows_with_realized_outcomes_ok(self):
        report = run_calibration(_manifest(minimum_required_rows=50), _rows(120))
        assert report.status == "STANDALONE_OK"
        assert report.reason_codes == ()
        assert report.summary.n == 120
        assert report.summary.expectancy_r is not None
        assert report.summary.profit_factor is not None
        assert report.summary.max_drawdown_r is not None

    def test_threshold_recommendations_are_provisional(self):
        # Even on an OK sample the harness only *recommends* — it never returns
        # a production-certified verdict by itself.  Tests only assert the
        # deterministic numeric output exists and is stable.
        report = run_calibration(_manifest(), _rows(120))
        assert report.recommended_thresholds["technical_floor"] is not None
        assert report.recommended_thresholds["min_risk_reward"] is not None
        again = run_calibration(_manifest(), _rows(120))
        assert report.recommended_thresholds == again.recommended_thresholds

    def test_confidence_interval_shape(self):
        report = run_calibration(_manifest(), _rows(120))
        ci = report.summary.confidence_interval_95
        assert ci is not None
        assert ci[0] <= ci[1]

    def test_stability_by_symbol(self):
        report = run_calibration(_manifest(), _rows(120))
        assert set(report.summary.stability_by_symbol) == {"XAUUSD", "EURUSD"}

    def test_oos_split_counted(self):
        # Rows below pit_boundary are "train" history; rows at/after boundary
        # are OOS.  The harness counts the OOS split explicitly.
        oos_rows = _rows(40, observed=PIT + timedelta(days=2))
        report = run_calibration(_manifest(), oos_rows)
        assert report.summary.oos_n == 40


class TestReportContract:
    def test_report_to_dict_shape(self):
        report = run_calibration(make_empty_calibration_manifest(), ())
        payload = report.to_dict()
        assert set(payload) == {
            "report_version",
            "manifest_fingerprint",
            "manifest",
            "status",
            "reason_codes",
            "summary",
            "recommended_thresholds",
        }

    def test_manifest_is_immutable(self):
        with pytest.raises(AttributeError):
            make_empty_calibration_manifest().minimum_required_rows = 10  # type: ignore[misc]

    def test_input_rows_are_immutable(self):
        row = _rows(1)[0]
        assert isinstance(row, CalibrationInput)
        with pytest.raises(AttributeError):
            row.outcome_r = 5.0  # type: ignore[misc]