"""SMC canonical runtime and legacy replay fixture tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from config.settings import FeatureFlagSettings, default_settings
from core.analysis_engine import analyze_symbol
from core.market_models import Candle
from core.risk_engine import AnalysisInput
from core.signal_engine import smc_quality_score
from core.smc_context import zone_quality_score
from core.smc_versions import SMC_RAW_ZONE_VERSION
from core.scanner import ScannerRequest, build_scanner_output
from core.scanner_observability import create_scan_context
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
    assert fixture["scorer_version"] == SMC_RAW_ZONE_VERSION
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


def test_smc_mode_settings_default_load_and_round_trip(tmp_path):
    assert default_settings().features == FeatureFlagSettings()
    assert default_settings().features.smc_scoring_mode == "v2"
    service = SettingsService(tmp_path / "settings.json")
    assert service.load().features.smc_scoring_mode == "v2"
    service.storage.save({
        "ai": {},
        "features": {"smc_scoring_mode": "invalid"},
    })
    assert service.load().features.smc_scoring_mode == "legacy"

    settings = default_settings()
    settings.features.smc_scoring_mode = "shadow"
    service.save(settings)
    assert service.load().features.smc_scoring_mode == "shadow"


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


def test_smc_modes_all_route_to_single_canonical_scorer():
    request, candles = _pipeline_input()
    legacy = analyze_symbol(
        request,
        candles,
        smc_scoring_mode="legacy",
    )
    shadow = analyze_symbol(
        request,
        candles,
        smc_scoring_mode="shadow",
    )
    requested_v2 = analyze_symbol(
        request,
        candles,
        smc_scoring_mode="v2",
    )

    # No mode can route to a different scorer any more.
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
        assert requested_v2[key] == legacy[key], key

    # The canonical diagnostics carry a single scorer version, not a mode and
    # not a shadow/legacy router payload.
    for result in (legacy, shadow, requested_v2):
        diagnostics = result["smc_scoring"]
        assert diagnostics["contract_version"] == "smc-scoring-canonical-2026-08"
        assert diagnostics["scoring_version"] == "smc-v2"
        assert set(diagnostics["sides"]) == {"buy", "sell"}
        assert "policy" not in diagnostics
        assert "shadow" not in diagnostics
        assert "active" not in diagnostics
        assert "comparison" not in diagnostics

    for side in ("buy", "sell"):
        side_score = requested_v2["scenario_scores"][side]
        consumer = requested_v2["smc_consumer"]["sides"][side]
        diagnostics_side = requested_v2["smc_scoring"]["sides"][side]
        assert side_score["smc_scoring_version"] == "smc-v2"
        assert side_score["smc_quality"] == diagnostics_side["score"]
        assert side_score["smc_scaled"] == int(
            side_score["smc_quality"]
            * side_score["regime_weights"]["smc"]
            / 15
        )
        assert consumer["scoring_version"] == "smc-v2"
        assert consumer["selected_zone_id"] == side_score["smc_flags"][
            "selected_zone_id"
        ]
