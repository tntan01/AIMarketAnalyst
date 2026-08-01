"""Settings and scanner output contracts introduced in Phase 0."""

from __future__ import annotations

from config.settings import FeatureFlagSettings, default_settings
from core.scanner import ScannerRequest, build_scanner_output
from core.scanner_observability import create_scan_context
from services.settings_service import SettingsService


def test_feature_flags_default_off():
    settings = default_settings()
    assert settings.features == FeatureFlagSettings()


def test_feature_flags_load_backward_compatibly(tmp_path):
    service = SettingsService(tmp_path / "settings.json")
    service.storage.save({
        "ai": {},
        "features": {
            "scanner_architecture_v2": True,
            "auto_trade_v2": True,
            "backtest_config_v2": True,
            "backtest_engine_v2": True,
        },
    })
    settings = service.load()
    assert settings.features.scanner_architecture_v2 is True
    assert settings.features.auto_trade_v2 is True
    assert settings.features.scanner_fast_tier1 is False
    assert settings.features.scanner_fast_tier2 is False
    assert settings.features.scanner_mt5_history_cache is False
    assert not hasattr(settings.features, "backtest_config_v2")
    assert not hasattr(settings.features, "backtest_engine_v2")


def test_feature_flags_round_trip(tmp_path):
    # Avoid touching the OS credential store; no provider has an API key.
    service = SettingsService(tmp_path / "settings.json")
    settings = default_settings()
    settings.features.scanner_architecture_v2 = True
    settings.features.auto_trade_v2 = True
    settings.features.scanner_fast_tier1 = True
    settings.features.scanner_fast_tier2 = True
    settings.features.scanner_mt5_history_cache = True
    service.save(settings)

    loaded = service.load()
    assert loaded.features.scanner_architecture_v2 is True
    assert loaded.features.auto_trade_v2 is True
    assert loaded.features.scanner_fast_tier1 is True
    assert loaded.features.scanner_fast_tier2 is True
    assert loaded.features.scanner_mt5_history_cache is True
    stored = service.storage.load()
    assert "backtest_config_v2" not in stored["features"]
    assert "backtest_engine_v2" not in stored["features"]


def test_scanner_output_exposes_contract_and_flags():
    request = ScannerRequest(
        symbols=[],
        account_balance=10_000,
        risk_percent=1.0,
        timezone_name="Asia/Ho_Chi_Minh",
        feature_flags={
            "auto_trade_v2": False,
            "scanner_fast_tier1": False,
            "scanner_fast_tier2": False,
            "scanner_mt5_history_cache": False,
        },
    )
    output = build_scanner_output([], request, 0)
    assert output["scanner_contract_version"] == "phase0-safety-v1"
    assert output["strategy_router_version"] == "phase2-router-v1"
    assert output["portfolio_engine_version"] == "phase4-portfolio-v1"
    assert output["feature_flags"] == {
        "auto_trade_v2": False,
        "scanner_fast_tier1": False,
        "scanner_fast_tier2": False,
        "scanner_mt5_history_cache": False,
    }


def test_fast_flags_are_preserved_in_scan_context_and_request_fingerprint():
    base_kwargs = {
        "symbols": ["EUR/USD"],
        "account_balance": 10_000,
        "risk_percent": 1.0,
        "timezone_name": "Asia/Ho_Chi_Minh",
    }
    disabled = ScannerRequest(
        **base_kwargs,
        feature_flags={"scanner_fast_tier1": False, "scanner_fast_tier2": False},
    )
    enabled = ScannerRequest(
        **base_kwargs,
        feature_flags={"scanner_fast_tier1": True, "scanner_fast_tier2": True},
    )

    disabled_context = create_scan_context(default_settings(), disabled)
    enabled_context = create_scan_context(default_settings(), enabled)

    assert enabled_context.feature_flags == {
        "scanner_fast_tier1": True,
        "scanner_fast_tier2": True,
    }
    assert enabled_context.request_hash != disabled_context.request_hash
