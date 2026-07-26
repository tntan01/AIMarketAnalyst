"""Phase-7 migration, reconciliation, shadow and release-gate tests."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys

from config.settings import SymbolScanSettings
from core.backtest_config import apply_validated_backtest_config
from core.backtest_config_validation import (
    build_backtest_config,
    validation_fingerprint,
)
from core.backtest_contract import (
    BACKTEST_CONTRACT_VERSION,
    VALIDATION_BACKTEST_ENGINE_VERSION,
)
from core.backtest_golden_replay import run_golden_replay
from core.backtest_migration import LEGACY_RESEARCH, migrate_snapshot_payload
from core.backtest_release import (
    build_release_report,
    compare_engine_shadow,
    reconcile_forward_demo,
    validate_release_report,
)
from core.scanner_models import (
    CONFIG_DRAFT,
    CONFIG_VERSION_MISMATCH,
)
from core.scanner_strategy_router import validate_backtest_config
from services.settings_service import SettingsService
from tests.test_backtest_config_validation import _result


FIXTURE = Path(__file__).parent / "fixtures" / "backtest_phase7_golden.json"


def _trades(count: int = 20) -> list[dict]:
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    return [
        {
            "candidate_id": f"candidate-{index}",
            "symbol": "EUR/USD",
            "side": "buy",
            "entry_time": (start + timedelta(hours=index)).isoformat(),
            "raw_entry_price": 1.1000,
            "entry_price": 1.1001,
            "planned_risk_account": 100.0,
            "result": "win",
            "result_r": 1.0,
        }
        for index in range(count)
    ]


def _demo(trades: list[dict], *, slippage_bps: float = 1.0) -> list[dict]:
    return [
        {
            "candidate_id": row["candidate_id"],
            "symbol": row["symbol"],
            "side": row["side"],
            "opened_at": row["entry_time"],
            "actual_entry": row["raw_entry_price"] * (
                1.0 + slippage_bps / 10_000.0
            ),
            "result_amount": row["planned_risk_account"],
            "mt5_deal_id": 1000 + index,
        }
        for index, row in enumerate(trades)
    ]


def _release_snapshot(trades: list[dict]) -> dict:
    return {
        "validation_replay": {
            "status": "COMPLETE",
            "backtest_contract": {
                "contract_version": BACKTEST_CONTRACT_VERSION,
                "engine_version": VALIDATION_BACKTEST_ENGINE_VERSION,
            },
            "data_manifest": {"dataset_hash": "a" * 64},
            "backtest_provenance": {
                "dataset_hash": "a" * 64,
                "provenance_fingerprint": "b" * 64,
            },
            "oos_trades": trades,
        }
    }


def test_legacy_snapshot_is_preserved_but_cannot_publish():
    original = {
        "backtest_contract": {
            "contract_version": "old-contract",
            "engine_version": "legacy-engine",
            "validation_eligible": True,
        },
        "trades": [{"candidate_id": "kept-for-audit"}],
    }

    migrated = migrate_snapshot_payload(original, source_path="old.json")

    assert migrated["lifecycle"]["status"] == LEGACY_RESEARCH
    assert migrated["lifecycle"]["can_publish_config"] is False
    assert migrated["migration"]["legacy_engine"] is True
    assert migrated["trades"] == original["trades"]
    assert original["backtest_contract"]["validation_eligible"] is True


def test_current_validation_snapshot_is_not_marked_legacy():
    migrated = migrate_snapshot_payload(_release_snapshot(_trades()))

    assert migrated["migration"]["legacy_engine"] is False
    assert migrated["lifecycle"]["status"] == "RESEARCH_ONLY"


def test_golden_replay_is_stable_and_passes():
    first = run_golden_replay(FIXTURE)
    second = run_golden_replay(FIXTURE)

    assert first["passed"] is True
    assert first["result_fingerprint"] == second["result_fingerprint"]
    assert first["fixture_hash"] == second["fixture_hash"]


def test_forward_demo_measures_fill_slippage_and_performance():
    expected = _trades()
    report = reconcile_forward_demo(expected, _demo(expected))

    assert report["ready"] is True
    assert report["metrics"]["matched_trades"] == 20
    assert report["metrics"]["fill_rate"] == 1.0
    assert report["metrics"]["rejection_rate"] == 0.0
    assert report["metrics"]["average_adverse_slippage_bps"] == 1.0
    assert report["metrics"]["performance_degradation_pct"] == 0.0


def test_forward_demo_blocks_small_sample_and_excessive_slippage():
    expected = _trades()
    report = reconcile_forward_demo(
        expected,
        _demo(expected[:10], slippage_bps=8.0),
    )

    assert report["ready"] is False
    assert "FORWARD_SAMPLE_TOO_SMALL" in report["block_codes"]
    assert "FORWARD_FILL_RATE_TOO_LOW" in report["block_codes"]
    assert "FORWARD_SLIPPAGE_TOO_HIGH" in report["block_codes"]


def test_forward_demo_requires_scanner_order_correlation():
    expected = _trades()
    demo = _demo(expected)
    for row in demo:
        row.pop("candidate_id")

    report = reconcile_forward_demo(expected, demo)

    assert report["ready"] is False
    assert "FORWARD_CORRELATION_MISSING" in report["block_codes"]


def test_release_thresholds_cannot_be_weakened_by_caller():
    expected = _trades(1)
    report = reconcile_forward_demo(
        expected,
        _demo(expected),
        thresholds={
            "min_forward_samples": 1,
            "min_fill_rate": 0.0,
            "max_rejection_rate": 1.0,
            "max_average_adverse_slippage_bps": 999.0,
            "max_performance_degradation_pct": 999.0,
        },
    )

    assert report["ready"] is False
    assert report["thresholds"]["min_forward_samples"] == 20
    assert "FORWARD_SAMPLE_TOO_SMALL" in report["block_codes"]


def test_engine_shadow_blocks_material_disagreement():
    legacy = _trades()
    identical = compare_engine_shadow(legacy, deepcopy(legacy))
    changed = deepcopy(legacy)
    for row in changed[:3]:
        row["result"] = "loss"
        row["result_r"] = -1.0
    different = compare_engine_shadow(legacy, changed)

    assert identical["ready"] is True
    assert identical["disagreement_rate"] == 0.0
    assert different["ready"] is False
    assert "ENGINE_SHADOW_DISAGREEMENT_TOO_HIGH" in different["block_codes"]


def test_release_report_requires_all_evidence_and_detects_tampering():
    trades = _trades()
    snapshot = _release_snapshot(trades)
    golden = run_golden_replay(FIXTURE)
    shadow = compare_engine_shadow(trades, deepcopy(trades))
    report = build_release_report(
        snapshot,
        demo_trades=_demo(trades),
        golden_report=golden,
        shadow_report=shadow,
        reviewed_by="risk-reviewer",
        approved=True,
    )

    assert report["ready"] is True
    assert validate_release_report(
        report,
        dataset_hash="a" * 64,
        provenance_fingerprint="b" * 64,
    ) == []

    tampered = deepcopy(report)
    tampered["dataset_hash"] = "c" * 64
    reasons = validate_release_report(
        tampered,
        dataset_hash="a" * 64,
        provenance_fingerprint="b" * 64,
    )
    assert "BACKTEST_RELEASE_DATASET_MISMATCH" in reasons
    assert "BACKTEST_RELEASE_REPORT_FINGERPRINT_INVALID" in reasons


def test_config_builder_and_router_fail_closed_without_release_report():
    result = _result()
    result.pop("release_report")
    draft = build_backtest_config(result, symbol="EUR/USD")

    assert draft is not None
    assert draft["status"] == CONFIG_DRAFT
    assert "BACKTEST_RELEASE_REPORT_MISSING" in draft["validation_reasons"]

    legacy_config = build_backtest_config(_result(), symbol="EUR/USD")
    assert legacy_config is not None
    legacy_config.pop("release_report")
    legacy_config["validation_fingerprint"] = validation_fingerprint(
        legacy_config
    )
    status, reasons = validate_backtest_config(
        legacy_config,
        {"symbol": "EUR/USD"},
    )
    assert status == CONFIG_VERSION_MISMATCH
    assert "BACKTEST_RELEASE_REPORT_MISSING" in reasons


def test_settings_migrates_pre_phase7_validated_config_fail_closed(tmp_path):
    service = SettingsService(tmp_path / "settings.json")
    app_settings = service.load()
    config = build_backtest_config(_result(), symbol="EUR/USD")
    assert config is not None
    symbol_settings = SymbolScanSettings()
    apply_validated_backtest_config(
        symbol_settings,
        symbol="EUR/USD",
        recommendation=config,
    )
    app_settings.trading.symbol_settings["EUR/USD"] = symbol_settings
    service.save(app_settings)

    persisted = service.storage.load()
    del persisted["trading"]["symbol_settings"]["EUR/USD"][
        "backtest_release_report"
    ]
    service.storage.save(persisted)
    migrated = service.load().trading.symbol_settings["EUR/USD"]

    assert migrated.backtest is False
    assert migrated.backtest_status == CONFIG_VERSION_MISMATCH
    assert "BACKTEST_RELEASE_REPORT_MISSING" in (
        migrated.backtest_validation_reasons
    )


def test_release_report_cli_is_deterministic_on_windows(tmp_path):
    trades = _trades()
    current_path = tmp_path / "current.json"
    forward_path = tmp_path / "forward.json"
    legacy_path = tmp_path / "legacy.json"
    demo_path = tmp_path / "demo.json"
    output_path = tmp_path / "reviewed.json"
    current_path.write_text(
        json.dumps(_release_snapshot(trades)), encoding="utf-8"
    )
    forward_path.write_text(
        json.dumps(_release_snapshot(trades)), encoding="utf-8"
    )
    legacy_path.write_text(json.dumps({
        "backtest_contract": {
            "contract_version": "old-contract",
            "engine_version": "legacy-engine",
        },
        "trades": trades,
    }), encoding="utf-8")
    demo_path.write_text(json.dumps(_demo(trades)), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/backtest_release_report.py",
            "--snapshot", str(current_path),
            "--forward-snapshot", str(forward_path),
            "--legacy-snapshot", str(legacy_path),
            "--demo-trades", str(demo_path),
            "--reviewer", "phase7-test-reviewer",
            "--approve",
            "--output", str(output_path),
        ],
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    reviewed = json.loads(output_path.read_text(encoding="utf-8"))
    assert reviewed["release_report"]["ready"] is True
    assert reviewed["lifecycle"]["can_publish_config"] is True
