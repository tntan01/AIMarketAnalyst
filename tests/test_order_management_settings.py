from __future__ import annotations

import json

from config.settings import default_settings
from services.settings_service import SettingsService


def test_order_management_defaults_are_shadow_and_fail_safe() -> None:
    settings = default_settings()

    assert settings.features.order_management_v2 is False
    assert settings.order_management.stage == "SHADOW"
    assert settings.order_management.require_demo_account is True
    assert settings.order_management.production_approved is False
    assert settings.order_management.manage_scope == "AMA"
    assert settings.order_management.canary_broker_symbol == ""
    assert settings.order_management.canary_position_id == 0


def test_order_management_settings_round_trip(tmp_path) -> None:
    path = tmp_path / "settings.json"
    service = SettingsService(path)
    settings = default_settings()
    settings.features.order_management_v2 = True
    settings.order_management.stage = "DEMO"
    settings.order_management.be_trigger_r = 1.25
    settings.order_management.trail_wide_atr_multiplier = 3.0
    settings.order_management.canary_broker_symbol = "EURUSDm"
    settings.order_management.canary_position_id = 12345

    service.save(settings)
    loaded = service.load()

    assert loaded.features.order_management_v2 is True
    assert loaded.order_management.stage == "DEMO"
    assert loaded.order_management.be_trigger_r == 1.25
    assert loaded.order_management.trail_wide_atr_multiplier == 3.0
    assert loaded.order_management.canary_broker_symbol == "EURUSDm"
    assert loaded.order_management.canary_position_id == 12345


def test_invalid_order_management_settings_fail_closed(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "ai": {},
                "features": {"order_management_v2": True},
                "order_management": {
                    "stage": "UNKNOWN",
                    "manage_scope": "EVERYTHING",
                    "poll_interval_seconds": 0,
                    "max_retry_attempts": 0,
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = SettingsService(path).load()

    assert loaded.order_management.stage == "SHADOW"
    assert loaded.order_management.manage_scope == "AMA"
    assert loaded.order_management.poll_interval_seconds == 0.5
    assert loaded.order_management.max_retry_attempts == 1
