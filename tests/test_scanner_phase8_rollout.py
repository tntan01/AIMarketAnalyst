"""Phase-8 shadow, rollout guard and release-gate tests."""

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
    build_shadow_report,
    evaluate_canary_readiness,
    evaluate_legacy_v1,
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


def test_shadow_report_captures_trade_side_and_score_disagreements():
    report = build_shadow_report(
        [{
            "scan_id": "scan-1",
            "row_id": "row-1",
            "symbol": "EUR/USD",
            "legacy_candidate_status": "READY_NOW",
            "candidate_status": "BLOCKED",
            "best_side": "buy",
            "selected_side": "sell",
            "best_score": 75,
            "min_score": 65,
            "legacy_candidate_input": {
                "scanner_action": "ready",
                "scanner_group": "ready_now",
                "trade_permission": "allowed",
                "best_side": "buy",
                "best_score": 75,
                "expected_effective_rr": 2.0,
                "market_regime": "range",
            },
            "analysis_result": {
                "scenarios": [{
                    "type": "buy",
                    "entry_zone": [1.0, 1.1],
                }],
            },
            "scanner_candidate_decision": {
                "auto_trade_candidate": False,
                "reason_codes": ["SETUP_SCORE_BELOW_MINIMUM"],
                "strategy": {
                    "eligible": False,
                    "min_score": 65,
                },
            },
        }],
        enabled=True,
    )

    comparison = report["comparisons"][0]
    assert report["disagreements"] == 1
    assert report["side_mismatches"] == 1
    assert report["false_ready_removed"] == 1
    assert report["new_trade_candidates"] == 0
    assert report["unsafe_disagreements"] == 0
    assert set(comparison["disagreement_codes"]) == {
        "TRADE_WAIT_DISAGREEMENT",
        "SIDE_DISAGREEMENT",
        "STATUS_DISAGREEMENT",
        "SCORE_GATE_DISAGREEMENT",
    }
    assert comparison["v2_order_suppressed"] is True


def test_shadow_v1_reproduction_exposes_forced_side_scenario_bug():
    legacy = evaluate_legacy_v1({
        "legacy_candidate_status": "READY_NOW",
        "legacy_candidate_input": {
            "scanner_action": "ready",
            "scanner_group": "ready_now",
            "trade_permission": "allowed",
            "best_side": "buy",
            "best_score": 75,
            "expected_effective_rr": 2.0,
            "market_regime": "range",
        },
        "auto_trade_config": {
            "regime": "range",
            "side": "sell",
            "min_score": 65,
            "min_rr": 1.5,
        },
        "analysis_result": {
            "scenarios": [{
                "type": "buy",
                "entry_zone": [1.0, 1.1],
            }],
        },
    })

    assert legacy["trade"] is True
    assert legacy["side"] == "sell"
    assert legacy["scenario_side"] == "buy"
    assert legacy["side_scenario_mismatch"] is True


def test_release_gate_fails_closed_when_evidence_is_missing():
    readiness = evaluate_release_readiness({}, _settings())

    assert readiness.ready is False
    assert "SHADOW_SAMPLE_INSUFFICIENT" in readiness.block_codes
    assert "DEMO_ORDER_SAMPLE_INSUFFICIENT" in readiness.block_codes
    assert "CANARY_ORDER_SAMPLE_INSUFFICIENT" in readiness.block_codes
    assert "OOS_EVIDENCE_MISSING" in readiness.block_codes
    assert "DEMO_EVIDENCE_MISSING" in readiness.block_codes
    assert "ROLLBACK_NOT_VERIFIED" in readiness.block_codes


def test_release_gate_passes_only_when_all_thresholds_hold():
    readiness = evaluate_release_readiness({
        "shadow_samples": 200,
        "disagreements": 10,
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
    assert readiness.metrics["disagreement_rate"] == 0.05


def test_release_gate_allows_safe_false_ready_removals():
    readiness = evaluate_release_readiness({
        "shadow_samples": 200,
        "disagreements": 200,
        "unsafe_disagreements": 0,
        "side_mismatches": 0,
        "demo_orders": 30,
        "canary_orders": 5,
        "revalidation_attempts": 100,
        "revalidation_failures": 0,
        "premature_orders": 0,
        "portfolio_violations": 0,
        "oos_degradation_pct": 5,
        "demo_degradation_pct": 7,
        "oos_evidence_recorded": True,
        "demo_evidence_recorded": True,
        "rollback_tested": True,
    }, _settings())

    assert readiness.metrics["disagreement_rate"] == 1.0
    assert readiness.metrics["unsafe_disagreement_rate"] == 0.0
    assert readiness.ready is True


def test_canary_gate_opens_before_production_gate():
    metrics = {
        "shadow_samples": 200,
        "disagreements": 5,
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
            "samples": 2,
            "disagreements": 1,
            "side_mismatches": 0,
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

    assert metrics["shadow_samples"] == 2
    assert metrics["disagreements"] == 1
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
    controller._auto_trade_safety_decision = lambda *_args: SimpleNamespace(
        auto_trade_candidate=True
    )
    controller.execute_order_candidate = lambda *_args, **_kwargs: (
        pytest.fail("SHADOW must not call execution")
    )
    policy = build_rollout_policy(
        _settings(stage=ROLLOUT_SHADOW),
        server="Broker-Demo",
    )

    result = controller._execute_auto_trades(
        [{"symbol": "EUR/USD", "scan_id": "scan-1"}],
        _request(),
        rollout_policy=policy,
    )

    assert result["attempted"] == 1
    assert result["opened"] == 0
    assert result["rollout_blocked"] == 1
    assert "SHADOW_MODE_ORDER_SUPPRESSED" in (
        result["orders"][0]["rollout"]["reason_codes"]
    )


def test_auto_trade_canary_caps_risk_before_shared_execution(monkeypatch):
    controller = ScannerController.__new__(ScannerController)
    controller.observability = _EventSink()
    controller.orders_screen = None
    controller._auto_trade_safety_decision = lambda *_args: SimpleNamespace(
        auto_trade_candidate=True
    )
    captured: dict = {}

    def _execute(proposal, *, risk_percent, comment):
        captured.update({
            "proposal": proposal,
            "risk_percent": risk_percent,
            "comment": comment,
        })
        return {"success": True, "order_id": 1}

    controller.execute_order_candidate = _execute
    monkeypatch.setattr(
        scanner_controller_module,
        "build_candidate_order_payload",
        lambda *_args, **_kwargs: {"symbol": "EUR/USD"},
    )
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
        [{"symbol": "EUR/USD"}],
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
