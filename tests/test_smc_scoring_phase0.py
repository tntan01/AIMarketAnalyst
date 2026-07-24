"""SMC legacy, shadow-isolation and active-v2 routing tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from config.settings import FeatureFlagSettings, default_settings
from core.analysis_engine import analyze_symbol
from core.market_models import Candle
from core.risk_engine import AnalysisInput
from core.signal_engine import smc_quality_score
from core.smc_scoring_contract import (
    SMC_MODE_LEGACY,
    SMC_MODE_SHADOW,
    SMC_SCORER_VERSION,
    build_smc_phase0_diagnostics,
    normalize_smc_scoring_mode,
    resolve_smc_scoring_policy,
)
from core.smc_context import zone_quality_score
from core.smc_models import SMC_DOMAIN_VERSION
from core.scanner import ScannerRequest, build_scanner_output
from core.scanner_observability import create_scan_context, stable_hash
from services.settings_service import SettingsService


_FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "smc_phase0_replay.json"
)


def _replay_fixture() -> dict:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


def _active_scores(smc: dict, technical: dict) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for side in ("buy", "sell"):
        quality, reason = smc_quality_score(side, smc, technical)
        result[side] = {
            "smc_quality": quality,
            "smc_reason": reason,
            "signal_score": 0,
        }
    return result


def test_replay_fixture_locks_legacy_scores():
    fixture = _replay_fixture()
    assert fixture["scorer_version"] == SMC_SCORER_VERSION
    assert len(fixture["cases"]) >= 9

    for case in fixture["cases"]:
        actual = _active_scores(case["smc"], case["technical"])
        assert actual["buy"]["smc_quality"] == case["expected"]["buy"], case["name"]
        assert actual["sell"]["smc_quality"] == case["expected"]["sell"], case["name"]


def test_replay_fixture_locks_legacy_zone_quality_formula():
    fixture = _replay_fixture()
    for case in fixture["zone_quality_cases"]:
        assert (
            zone_quality_score(case["zone"], case["side"])
            == case["expected"]
        ), case["name"]


def test_shadow_replay_is_deterministic_and_read_only():
    for case in _replay_fixture()["cases"]:
        active = _active_scores(case["smc"], case["technical"])
        before = stable_hash(active)
        first = build_smc_phase0_diagnostics(
            requested_mode=SMC_MODE_SHADOW,
            smc=case["smc"],
            technical=case["technical"],
            active_scores=active,
        )
        second = build_smc_phase0_diagnostics(
            requested_mode=SMC_MODE_SHADOW,
            smc=case["smc"],
            technical=case["technical"],
            active_scores=active,
        )

        assert stable_hash(first) == stable_hash(second), case["name"]
        assert stable_hash(active) == before, case["name"]
        assert first["policy"]["effective_mode"] == SMC_MODE_LEGACY
        assert first["policy"]["decision_impact_allowed"] is False
        comparison = first["comparison"]
        assert comparison["available"] is True
        assert comparison["decision_changed"] is False
        for side in ("buy", "sell"):
            assert comparison["score_delta"][side] == (
                comparison["v2_smc_quality"][side]
                - comparison["legacy_smc_quality"][side]
            )


def test_v2_request_activates_v2_decision_source():
    policy = resolve_smc_scoring_policy("v2")
    assert policy.requested_mode == "v2"
    assert policy.effective_mode == "v2"
    assert policy.decision_source == "smc-v2"
    assert policy.active_version == "smc-v2"
    assert policy.decision_impact_allowed is True
    assert policy.fallback_reason_codes == ()


def test_invalid_mode_normalizes_to_legacy():
    assert normalize_smc_scoring_mode("unexpected") == SMC_MODE_LEGACY
    assert normalize_smc_scoring_mode(None) == SMC_MODE_LEGACY


def test_smc_mode_settings_default_load_and_round_trip(tmp_path):
    assert default_settings().features == FeatureFlagSettings()
    assert default_settings().features.smc_scoring_mode == "v2"
    service = SettingsService(tmp_path / "settings.json")
    assert service.load().features.smc_scoring_mode == "v2"
    service.storage.save({
        "ai": {},
        "features": {"smc_scoring_mode": "invalid"},
    })
    assert service.load().features.smc_scoring_mode == SMC_MODE_LEGACY

    settings = default_settings()
    settings.features.smc_scoring_mode = SMC_MODE_SHADOW
    service.save(settings)
    assert service.load().features.smc_scoring_mode == SMC_MODE_SHADOW


def test_scan_contract_exposes_smc_mode_and_version():
    request = ScannerRequest(
        symbols=["EUR/USD"],
        account_balance=10_000,
        risk_percent=1.0,
        timezone_name="Asia/Ho_Chi_Minh",
        smc_scoring_mode=SMC_MODE_SHADOW,
    )
    context = create_scan_context(default_settings(), request)
    output = build_scanner_output([], request, 0)

    assert context.smc_scoring_mode == SMC_MODE_SHADOW
    assert context.smc_scorer_version == SMC_SCORER_VERSION
    assert context.smc_domain_version == SMC_DOMAIN_VERSION
    assert output["smc_scoring_mode"] == SMC_MODE_SHADOW
    assert output["smc_scorer_version"] == SMC_SCORER_VERSION
    assert output["smc_domain_version"] == SMC_DOMAIN_VERSION


def test_default_scan_contract_uses_active_v2_version():
    request = ScannerRequest(
        symbols=["EUR/USD"],
        account_balance=10_000,
        risk_percent=1.0,
        timezone_name="Asia/Ho_Chi_Minh",
    )
    context = create_scan_context(default_settings(), request)
    output = build_scanner_output([], request, 0)

    assert request.smc_scoring_mode == "v2"
    assert context.smc_scoring_mode == "v2"
    assert context.smc_scorer_version == "smc-v2"
    assert output["smc_scoring_mode"] == "v2"
    assert output["smc_scorer_version"] == "smc-v2"


def _candles(
    count: int,
    *,
    start: float,
    step: float,
    bar_minutes: int,
) -> list[Candle]:
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    price = start
    result: list[Candle] = []
    for index in range(count):
        direction = 1 if index % 7 != 6 else -1
        body = step * direction
        open_price = price
        close_price = price + body
        result.append(Candle(
            time=timestamp,
            open=round(open_price, 5),
            high=round(max(open_price, close_price) + abs(step) * 0.7, 5),
            low=round(min(open_price, close_price) - abs(step) * 0.7, 5),
            close=round(close_price, 5),
            volume=float(1000 + index),
        ))
        price = close_price
        timestamp += timedelta(minutes=bar_minutes)
    return result


def _pipeline_input() -> tuple[AnalysisInput, dict[str, list[Candle]]]:
    request = AnalysisInput(
        symbol="EUR/USD",
        broker_symbol="EURUSDm",
        account_balance=10_000,
        risk_percent=1.0,
        account_currency="USD",
        lot_step=0.01,
        minimum_lot=0.01,
        contract_size_override=100_000,
        timezone_name="Asia/Ho_Chi_Minh",
    )
    candles = {
        "D1": _candles(120, start=1.05, step=0.00020, bar_minutes=1440),
        "H4": _candles(240, start=1.06, step=0.00010, bar_minutes=240),
        "H1": _candles(300, start=1.07, step=0.00005, bar_minutes=60),
    }
    return request, candles


def test_shadow_is_isolated_while_v2_enters_the_decision_path():
    request, candles = _pipeline_input()
    legacy = analyze_symbol(
        request,
        candles,
        smc_scoring_mode=SMC_MODE_LEGACY,
    )
    shadow = analyze_symbol(
        request,
        candles,
        smc_scoring_mode=SMC_MODE_SHADOW,
    )
    requested_v2 = analyze_symbol(
        request,
        candles,
        smc_scoring_mode="v2",
    )

    for key in (
        "scenario_scores",
        "direction_bias",
        "scenarios",
        "trade_gate",
        "final_score",
        "side_scores",
        "decision_engine",
    ):
        assert shadow[key] == legacy[key], key

    diagnostics = shadow["smc_scoring"]
    assert diagnostics["policy"]["shadow_enabled"] is True
    assert diagnostics["policy"]["decision_impact_allowed"] is False
    assert diagnostics["comparison"]["available"] is True
    assert diagnostics["comparison"]["decision_changed"] is False
    assert diagnostics["shadow"]["buy"]["scoring_version"] == "smc-v2"
    assert diagnostics["shadow"]["sell"]["scoring_version"] == "smc-v2"
    v2_policy = requested_v2["smc_scoring"]["policy"]
    assert v2_policy["effective_mode"] == "v2"
    assert v2_policy["decision_source"] == "smc-v2"
    assert v2_policy["decision_impact_allowed"] is True
    assert v2_policy["fallback_reason_codes"] == []
    v2_comparison = requested_v2["smc_scoring"]["comparison"]
    assert v2_comparison["decision_changed"] == v2_comparison[
        "decision_input_changed"
    ]
    for side in ("buy", "sell"):
        side_score = requested_v2["scenario_scores"][side]
        consumer = requested_v2["smc_consumer"]["sides"][side]
        decision_score = requested_v2["smc_scoring"]["decision_scores"][side]
        v2_snapshot = requested_v2["smc_scoring"]["shadow"][side]
        assert side_score["smc_scoring_version"] == "smc-v2"
        assert side_score["smc_quality"] == v2_snapshot["smc_quality"]
        assert side_score["smc_scaled"] == int(
            side_score["smc_quality"]
            * side_score["regime_weights"]["smc"]
            / 15
        )
        assert consumer["selection_source"] == "v2"
        assert consumer["scoring_version"] == "smc-v2"
        assert decision_score["smc_quality"] == side_score["smc_quality"]
        assert decision_score["signal_score"] == side_score["signal_score"]
        assert (
            decision_score["selected_zone_id"]
            == consumer["selected_zone_id"]
        )
