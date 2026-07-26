"""Small valid release evidence used by config/router regression fixtures."""

from __future__ import annotations

from core.backtest_contract import VALIDATION_BACKTEST_ENGINE_VERSION
from core.backtest_golden_replay import (
    GOLDEN_REPLAY_VERSION,
    GOLDEN_RESULT_FINGERPRINT,
)
from core.backtest_release import (
    BACKTEST_FORWARD_RECONCILIATION_VERSION,
    BACKTEST_RELEASE_REPORT_VERSION,
    BACKTEST_SHADOW_REPORT_VERSION,
    release_report_fingerprint,
)


def ready_release_report(
    *,
    dataset_hash: str = "a" * 64,
    provenance_fingerprint: str = "e" * 64,
) -> dict:
    report = {
        "version": BACKTEST_RELEASE_REPORT_VERSION,
        "ready": True,
        "approved": True,
        "reviewed_by": "phase7-test-reviewer",
        "reviewed_at": "2026-07-24T00:00:00+00:00",
        "dataset_hash": dataset_hash,
        "provenance_fingerprint": provenance_fingerprint,
        "engine_version": VALIDATION_BACKTEST_ENGINE_VERSION,
        "forward_evidence_fingerprint": "f" * 64,
        "demo_evidence_fingerprint": "d" * 64,
        "golden_replay": {
            "version": GOLDEN_REPLAY_VERSION,
            "passed": True,
            "result_fingerprint": GOLDEN_RESULT_FINGERPRINT,
            "mismatches": [],
        },
        "forward_demo": {
            "version": BACKTEST_FORWARD_RECONCILIATION_VERSION,
            "ready": True,
            "block_codes": [],
            "metrics": {
                "matched_trades": 20,
                "correlated_matches": 20,
                "fill_rate": 1.0,
                "rejection_rate": 0.0,
                "average_adverse_slippage_bps": 0.0,
                "performance_degradation_pct": 0.0,
            },
        },
        "engine_shadow": {
            "version": BACKTEST_SHADOW_REPORT_VERSION,
            "ready": True,
            "block_codes": [],
            "samples": 20,
            "disagreement_rate": 0.0,
            "performance_degradation_pct": 0.0,
        },
        "block_codes": [],
    }
    report["report_fingerprint"] = release_report_fingerprint(report)
    return report
