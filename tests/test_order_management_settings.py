from __future__ import annotations

import json

from config.settings import default_settings
from services.settings_service import SettingsService


def test_order_management_defaults_are_live_and_fail_safe() -> None:
    # Fully live since 2026-08-16: the OM feature flag is removed and the
    # stage ladder / kill switch / canary fields no longer exist. Execution
    # is gated only by the broker account's own trading permission.
    settings = default_settings()

    for removed_field in (
        "stage",
        "kill_switch",
        "require_demo_account",
        "production_approved",
        "canary_broker_symbol",
        "canary_position_id",
        "manage_scope",
    ):
        assert not hasattr(settings.order_management, removed_field)


def test_order_management_settings_round_trip(tmp_path) -> None:
    path = tmp_path / "settings.json"
    service = SettingsService(path)
    settings = default_settings()
    settings.order_management.be_trigger_r = 1.25
    settings.order_management.trail_wide_atr_multiplier = 3.0

    service.save(settings)
    loaded = service.load()

    assert loaded.order_management.be_trigger_r == 1.25
    assert loaded.order_management.trail_wide_atr_multiplier == 3.0


def test_invalid_order_management_settings_fail_closed(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "ai": {},
                "order_management": {
                    # Leftover rollout-era keys must be ignored, not honored.
                    "stage": "SHADOW",
                    "kill_switch": True,
                    "manage_scope": "EVERYTHING",
                    "poll_interval_seconds": 0,
                    "max_retry_attempts": 0,
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = SettingsService(path).load()

    assert not hasattr(loaded.order_management, "stage")
    assert not hasattr(loaded.order_management, "kill_switch")
    assert not hasattr(loaded.order_management, "manage_scope")
    assert loaded.order_management.poll_interval_seconds == 0.5
    assert loaded.order_management.max_retry_attempts == 1
