"""SMC canonical runtime tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from config.settings import default_settings
from core.analysis_engine import analyze_symbol
from core.market_models import Candle
from core.risk_engine import AnalysisInput
from core.scanner import ScannerRequest, build_scanner_output
from core.scanner_observability import create_scan_context
from services.settings_service import SettingsService


def test_smc_scoring_mode_setting_is_gone_and_old_keys_ignored(tmp_path):
    """Bước 15: không còn config path nào kích hoạt scorer khác.

    Settings JSON cũ với smc_scoring_mode (legacy/shadow/v2/invalid) đều
    được bỏ qua — mọi runtime dùng SMC canonical; round-trip không ghi lại
    key cũ.
    """
    service = SettingsService(tmp_path / "settings.json")
    for value in ("legacy", "shadow", "v2", "invalid", ""):
        service.storage.save({
            "ai": {},
            "features": {"smc_scoring_mode": value},
        })
        loaded = service.load()
        assert not hasattr(loaded.features, "smc_scoring_mode"), value

    settings = default_settings()
    assert not hasattr(settings.features, "smc_scoring_mode")
    service.save(settings)
    saved = service.storage.load()
    assert "smc_scoring_mode" not in saved.get("features", {})


def test_default_scan_contract_uses_canonical_scorer():
    request = ScannerRequest(
        symbols=["EUR/USD"],
        account_balance=10_000,
        risk_percent=1.0,
        timezone_name="Asia/Ho_Chi_Minh",
    )
    context = create_scan_context(default_settings(), request)
    output = build_scanner_output([], request, 0)

    assert not hasattr(request, "smc_scoring_mode")
    assert "smc_scoring_mode" not in output
    assert context.smc_scorer_version == "smc-v2"
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


def test_analysis_outputs_single_canonical_scorer():
    request, candles = _pipeline_input()
    first = analyze_symbol(request, candles)
    second = analyze_symbol(request, candles)

    # Deterministic single canonical scorer — no mode can route elsewhere.
    for key in (
        "scenario_scores",
        "direction_bias",
        "scenarios",
        "trade_gate",
        "final_score",
        "side_scores",
        "decision_engine",
    ):
        assert second[key] == first[key], key

    # The canonical diagnostics carry a single scorer version, not a mode and
    # not a shadow/legacy router payload.
    for result in (first, second):
        diagnostics = result["smc_scoring"]
        assert diagnostics["contract_version"] == "smc-scoring-canonical-2026-08"
        assert diagnostics["scoring_version"] == "smc-v2"
        assert set(diagnostics["sides"]) == {"buy", "sell"}
        assert "policy" not in diagnostics
        assert "shadow" not in diagnostics
        assert "active" not in diagnostics
        assert "comparison" not in diagnostics

    for side in ("buy", "sell"):
        side_score = first["scenario_scores"][side]
        consumer = first["smc_consumer"]["sides"][side]
        diagnostics_side = first["smc_scoring"]["sides"][side]
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
