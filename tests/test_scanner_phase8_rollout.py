"""Phase-8 rollout guard and release-gate tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from config.settings import ScannerRolloutSettings, default_settings
import controllers.scanner_controller as scanner_controller_module
from controllers.scanner_controller import ScannerController
from core.scanner import ScannerRequest
from core.scanner_rollout import (
    ROLLOUT_CANARY,
    ROLLOUT_DEMO_FULL,
    ROLLOUT_DEMO_LIMITED,
    ROLLOUT_PRODUCTION,
    ROLLOUT_SHADOW,
    build_rollout_policy,
    evaluate_canary_readiness,
    evaluate_release_readiness,
)
from services.scanner_rollout_service import ScannerRolloutMetricsService
from services.settings_service import SettingsService


def _settings(**overrides) -> ScannerRolloutSettings:
    settings = ScannerRolloutSettings()
    for key, value in overrides.items():
        setattr(settings, key, value)
    return settings


def test_rollout_defaults_to_shadow_and_suppresses_every_order():
    policy = build_rollout_policy(_settings(), server="Broker-Demo")
    decision = policy.order_decision("EUR/USD")

    assert policy.stage == ROLLOUT_SHADOW
    assert decision.allowed is False
    assert decision.reason_codes == ("SHADOW_MODE_ORDER_SUPPRESSED",)


def test_kill_switch_overrides_production_approval():
    policy = build_rollout_policy(
        _settings(
            stage=ROLLOUT_PRODUCTION,
            production_approved=True,
            kill_switch=True,
        ),
        server="Broker-Live",
    )

    decision = policy.order_decision("EUR/USD")

    assert decision.allowed is False
    assert "ROLLOUT_KILL_SWITCH_ACTIVE" in decision.reason_codes


def test_demo_limited_requires_demo_server_and_allowed_symbol():
    settings = _settings(
        stage=ROLLOUT_DEMO_LIMITED,
        allowed_symbols=["EUR/USD"],
    )

    live = build_rollout_policy(settings, server="Broker-Live")
    demo = build_rollout_policy(settings, server="Broker-Demo")

    assert demo.order_decision("EURUSD").allowed is True
    assert demo.order_decision("GBPUSD").allowed is False
    assert "SYMBOL_NOT_IN_LIMITED_ROLLOUT" in (
        demo.order_decision("GBPUSD").reason_codes
    )
    assert live.order_decision("EURUSD").allowed is False
    assert "DEMO_ACCOUNT_REQUIRED" in (
        live.order_decision("EURUSD").reason_codes
    )


def test_demo_full_allows_all_symbols_only_on_demo_account():
    settings = _settings(stage=ROLLOUT_DEMO_FULL)

    assert build_rollout_policy(
        settings,
        server="MetaQuotes-Demo",
    ).order_decision("XAUUSD").allowed is True
    assert build_rollout_policy(
        settings,
        server="MetaQuotes-Live",
    ).order_decision("XAUUSD").allowed is False


def test_canary_applies_hard_risk_cap():
    policy = build_rollout_policy(
        _settings(
            stage=ROLLOUT_CANARY,
            canary_risk_percent=0.1,
            require_demo_account=False,
        ),
        server="Broker-Live",
        canary_ready=True,
    )

    decision = policy.order_decision("EURUSD")

    assert decision.allowed is True
    assert decision.risk_cap_percent == 0.1


def test_canary_is_blocked_until_shadow_and_demo_gate_is_ready():
    policy = build_rollout_policy(
        _settings(
            stage=ROLLOUT_CANARY,
            require_demo_account=False,
        ),
        server="Broker-Live",
        canary_ready=False,
    )

    decision = policy.order_decision("EURUSD")

    assert decision.allowed is False
    assert "CANARY_GATE_NOT_READY" in decision.reason_codes


def test_production_requires_explicit_approval():
    blocked = build_rollout_policy(
        _settings(stage=ROLLOUT_PRODUCTION),
        server="Broker-Live",
    )
    allowed = build_rollout_policy(
        _settings(
            stage=ROLLOUT_PRODUCTION,
            production_approved=True,
        ),
        server="Broker-Live",
        release_ready=True,
    )

    assert blocked.order_decision("EURUSD").allowed is False
    assert "PRODUCTION_APPROVAL_REQUIRED" in (
        blocked.order_decision("EURUSD").reason_codes
    )
    assert allowed.order_decision("EURUSD").allowed is True


def test_production_is_blocked_when_release_evidence_is_not_ready():
    policy = build_rollout_policy(
        _settings(
            stage=ROLLOUT_PRODUCTION,
            production_approved=True,
        ),
        server="Broker-Live",
        release_ready=False,
    )

    decision = policy.order_decision("EURUSD")

    assert decision.allowed is False
    assert "RELEASE_GATE_NOT_READY" in decision.reason_codes


def test_release_gate_fails_closed_when_evidence_is_missing():
    readiness = evaluate_release_readiness({}, _settings())

    assert readiness.ready is False
    assert "DEMO_ORDER_SAMPLE_INSUFFICIENT" in readiness.block_codes
    assert "CANARY_ORDER_SAMPLE_INSUFFICIENT" in readiness.block_codes
    assert "OOS_EVIDENCE_MISSING" in readiness.block_codes
    assert "DEMO_EVIDENCE_MISSING" in readiness.block_codes
    assert "ROLLBACK_NOT_VERIFIED" in readiness.block_codes


def test_release_gate_passes_only_when_all_thresholds_hold():
    readiness = evaluate_release_readiness({
        "side_mismatches": 0,
        "demo_orders": 30,
        "canary_orders": 5,
        "revalidation_attempts": 100,
        "revalidation_failures": 2,
        "premature_orders": 0,
        "portfolio_violations": 0,
        "oos_degradation_pct": 5,
        "demo_degradation_pct": 7,
        "oos_evidence_recorded": True,
        "demo_evidence_recorded": True,
        "rollback_tested": True,
    }, _settings())

    assert readiness.ready is True
    assert readiness.block_codes == ()


def test_canary_gate_opens_before_production_gate():
    metrics = {
        "side_mismatches": 0,
        "demo_orders": 30,
        "canary_orders": 0,
        "revalidation_attempts": 100,
        "revalidation_failures": 2,
        "premature_orders": 0,
        "portfolio_violations": 0,
        "oos_degradation_pct": 5,
        "demo_degradation_pct": 7,
        "oos_evidence_recorded": True,
        "demo_evidence_recorded": True,
        "rollback_tested": True,
    }

    canary = evaluate_canary_readiness(metrics, _settings())
    production = evaluate_release_readiness(metrics, _settings())

    assert canary.ready is True
    assert production.ready is False
    assert "CANARY_ORDER_SAMPLE_INSUFFICIENT" in production.block_codes


def test_rollout_metrics_persist_and_mark_verified_kill_switch(tmp_path):
    service = ScannerRolloutMetricsService(tmp_path / "metrics.json")
    metrics = service.record_scan(
        scan_id="scan-1",
        shadow_report={
            "smc_no_zone_sides": 1,
            "smc_side_samples": 2,
            "data_unavailable": 0,
            "analysis_errors": 0,
            "analysis_latency_ms_total": 25.0,
            "analysis_latency_samples": 2,
            "analysis_latency_ms_max": 13.0,
        },
        auto_trade_results={
            "opened": 0,
            "rollout_blocked": 1,
            "orders": [],
        },
        rollout_policy={
            "stage": "SHADOW",
            "kill_switch": True,
            "account_is_demo": True,
        },
    )

    assert metrics["smc_no_zone_sides"] == 1
    assert metrics["smc_side_samples"] == 2
    assert metrics["smc_no_zone_rate"] == 0.5
    assert metrics["rollback_tested"] is True
    assert service.load()["last_scan_id"] == "scan-1"
    evidence = service.update_release_evidence(
        oos_degradation_pct=4.0,
        demo_degradation_pct=6.0,
    )
    assert evidence["oos_evidence_recorded"] is True
    assert evidence["demo_evidence_recorded"] is True


def test_settings_migrate_to_shadow_and_round_trip_rollout(tmp_path):
    service = SettingsService(tmp_path / "settings.json")
    service.storage.save({"ai": {}})
    migrated = service.load()

    assert migrated.scanner_rollout.stage == ROLLOUT_SHADOW

    migrated.scanner_rollout = _settings(
        stage=ROLLOUT_CANARY,
        canary_risk_percent=0.15,
        require_demo_account=False,
        allowed_symbols=["EURUSD"],
    )
    service.save(migrated)
    loaded = service.load()

    assert loaded.scanner_rollout.stage == ROLLOUT_CANARY
    assert loaded.scanner_rollout.canary_risk_percent == 0.15
    assert loaded.scanner_rollout.require_demo_account is False
    assert loaded.scanner_rollout.allowed_symbols == ["EURUSD"]


class _SettingsService:
    def __init__(self) -> None:
        self.settings = default_settings()

    def load(self):
        return self.settings


class _ShadowMT5:
    def __init__(self) -> None:
        self.execution_snapshot_calls = 0

    def connection_status(self):
        return SimpleNamespace(server="Broker-Demo")

    def execution_snapshot(self, _symbol):
        self.execution_snapshot_calls += 1
        raise AssertionError("SHADOW must block before execution snapshot")


def test_controller_shadow_guard_blocks_before_market_revalidation():
    mt5 = _ShadowMT5()
    controller = ScannerController(
        settings_service=_SettingsService(),
        mt5=mt5,
    )

    result = controller.execute_order_candidate({
        "symbol": "EUR/USD",
        "broker_symbol": "EURUSD",
        "side": "buy",
    }, manual_release_gate_override=True)

    assert result["success"] is False
    assert "SHADOW_MODE_ORDER_SUPPRESSED" in (
        result["rollout"]["reason_codes"]
    )
    assert mt5.execution_snapshot_calls == 0


class _EventSink:
    def emit(self, *_args, **_kwargs):
        return None


def _request() -> ScannerRequest:
    return ScannerRequest(
        symbols=["EUR/USD"],
        account_balance=10_000,
        risk_percent=1.0,
        timezone_name="UTC",
        auto_trade_enabled=True,
    )


def test_auto_trade_loop_never_calls_execution_in_shadow():
    controller = ScannerController.__new__(ScannerController)
    controller.observability = _EventSink()
    controller.execute_order_candidate = lambda *_args, **_kwargs: (
        pytest.fail("SHADOW must not call execution")
    )
    policy = build_rollout_policy(
        _settings(stage=ROLLOUT_SHADOW),
        server="Broker-Demo",
    )

    result = controller._execute_auto_trades(
        [{
            "symbol": "EUR/USD",
            "scan_id": "scan-1",
            # Genuine V4 READY_NOW candidate so the auto-trade gate lets it
            # through to the rollout guard; the shadow stage must still block it.
            "candidate_status": "READY_NOW",
            "auto_trade_candidate": True,
        }],
        _request(),
        rollout_policy=policy,
    )

    assert result["attempted"] == 1
    assert result["opened"] == 0
    assert result["rollout_blocked"] == 1
    assert "SHADOW_MODE_ORDER_SUPPRESSED" in (
        result["orders"][0]["rollout"]["reason_codes"]
    )


def test_auto_trade_canary_caps_risk_before_shared_execution():
    controller = ScannerController.__new__(ScannerController)
    controller.observability = _EventSink()
    controller.orders_screen = None
    captured: dict = {}

    def _execute(proposal, *, risk_percent, comment):
        captured.update({
            "proposal": proposal,
            "risk_percent": risk_percent,
            "comment": comment,
        })
        return {"success": True, "order_id": 1}

    controller.execute_order_candidate = _execute
    policy = build_rollout_policy(
        _settings(
            stage=ROLLOUT_CANARY,
            canary_risk_percent=0.1,
            require_demo_account=False,
        ),
        server="Broker-Live",
        canary_ready=True,
    )

    result = controller._execute_auto_trades(
        [{
            "symbol": "EUR/USD",
            "candidate_status": "READY_NOW",
            "auto_trade_candidate": True,
            "candidate_order_payload": {
                "symbol": "EUR/USD",
                "side": "buy",
                "entry": 1.1000,
                "stop_loss": 1.0980,
                "take_profit": 1.1080,
                "scoring_version": "scanner-v4",
            },
        }],
        _request(),
        rollout_policy=policy,
    )

    assert result["opened"] == 1
    assert captured["risk_percent"] == 0.1
    assert captured["proposal"]["rollout_stage"] == ROLLOUT_CANARY


@pytest.mark.parametrize(
    ("server", "expected"),
    [
        ("Broker-Demo", True),
        ("Broker-Practice-01", True),
        ("Broker-Live", False),
        ("Demolition-Live", False),
        ("", False),
    ],
)
def test_demo_account_detection_is_fail_closed(server, expected):
    policy = build_rollout_policy(
        _settings(stage=ROLLOUT_DEMO_FULL),
        server=server,
    )

    assert policy.account_is_demo is expected


def test_legacy_settings_file_with_removed_fields_still_loads(tmp_path):
    """An old settings.json that still carries the removed V1/V2 shadow
    comparison fields must load cleanly (unknown keys ignored) and re-save
    without error."""
    service = SettingsService(tmp_path / "settings.json")
    service.storage.save({
        "ai": {},
        "scanner_rollout": {
            "stage": "SHADOW",
            "kill_switch": False,
            "shadow_compare_enabled": True,
            "min_shadow_samples": 100,
            "max_disagreement_rate": 0.1,
            "min_demo_orders": 20,
        },
    })

    loaded = service.load()
    assert loaded.scanner_rollout.stage == "SHADOW"
    assert loaded.scanner_rollout.min_demo_orders == 20
    assert not hasattr(loaded.scanner_rollout, "shadow_compare_enabled")
    assert not hasattr(loaded.scanner_rollout, "min_shadow_samples")
    assert not hasattr(loaded.scanner_rollout, "max_disagreement_rate")

    # Re-saving must not raise and must drop the removed fields.
    service.save(loaded)
    reloaded = service.load()
    assert reloaded.scanner_rollout.stage == "SHADOW"
    assert reloaded.scanner_rollout.min_demo_orders == 20


def test_rollout_tab_builds_and_saves_without_shadow_compare_controls(tmp_path):
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication, QCheckBox
    from ui.screens.settings_screen import SettingsScreen

    _ = QApplication.instance() or QApplication([])

    screen = SettingsScreen.__new__(SettingsScreen)
    screen.app_settings = default_settings()
    screen.settings_service = SettingsService(tmp_path / "settings.json")

    frame = screen._rollout_tab()

    # The three removed controls must be gone (check the instance dict:
    # hasattr() raises on an uninitialized PyQt wrapper).
    widget_attrs = screen.__dict__
    assert "rollout_shadow_compare_input" not in widget_attrs
    assert "rollout_min_shadow_input" not in widget_attrs
    assert "rollout_max_disagreement_input" not in widget_attrs
    checkbox_texts = [cb.text() for cb in frame.findChildren(QCheckBox)]
    assert not any("V1/V2" in text for text in checkbox_texts)
    # Helper text must no longer describe the removed V2 comparison.
    assert "V2" not in screen.rollout_status_label.text()

    # Saving the rollout tab must not raise.
    screen._save_rollout_settings()
    reloaded = screen.settings_service.load()
    assert reloaded.scanner_rollout.stage == "SHADOW"
