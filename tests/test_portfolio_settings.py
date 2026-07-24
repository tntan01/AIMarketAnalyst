"""Phase-4 portfolio limit settings compatibility tests."""

from __future__ import annotations

from config.settings import default_settings
from services.settings_service import SettingsService


def test_legacy_settings_receive_safe_portfolio_defaults(tmp_path):
    service = SettingsService(tmp_path / "settings.json")
    service.storage.save({"ai": {}, "trading": {"account_balance": 5000}})

    trading = service.load().trading

    assert trading.max_open_risk_pct == 3.0
    assert trading.max_symbol_risk_pct == 2.0
    assert trading.max_currency_exposure_pct == 2.0
    assert trading.max_correlated_risk_pct == 2.0
    assert trading.max_concurrent_orders == 5


def test_portfolio_limits_round_trip(tmp_path):
    service = SettingsService(tmp_path / "settings.json")
    settings = default_settings()
    settings.trading.max_symbol_risk_pct = 1.5
    settings.trading.max_currency_exposure_pct = 1.75
    settings.trading.max_correlated_risk_pct = 1.25
    settings.trading.max_concurrent_orders = 4

    service.save(settings)
    loaded = service.load().trading

    assert loaded.max_symbol_risk_pct == 1.5
    assert loaded.max_currency_exposure_pct == 1.75
    assert loaded.max_correlated_risk_pct == 1.25
    assert loaded.max_concurrent_orders == 4


def test_invalid_portfolio_limits_are_clamped(tmp_path):
    service = SettingsService(tmp_path / "settings.json")
    service.storage.save({
        "ai": {},
        "trading": {
            "max_symbol_risk_pct": 0,
            "max_currency_exposure_pct": -1,
            "max_correlated_risk_pct": 0,
            "max_concurrent_orders": 0,
        },
    })

    trading = service.load().trading

    assert trading.max_symbol_risk_pct == 0.1
    assert trading.max_currency_exposure_pct == 0.1
    assert trading.max_correlated_risk_pct == 0.1
    assert trading.max_concurrent_orders == 1
