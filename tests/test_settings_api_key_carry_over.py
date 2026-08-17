"""SettingsService: brave/fred API keys phải carry-over qua save/load.

Regression guard (tách từ bộ test review-fixes cũ): API keys từng bị
reset về mặc định khi save rebuild settings — phải giữ nguyên giá trị
đã nạp từ file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from services.settings_service import SettingsService


def _write_settings_file(path: Path, advanced: dict[str, Any]) -> None:
    path.write_text(json.dumps({"advanced": advanced}), encoding="utf-8")


def test_settings_service_save_khong_reset_api_keys_va_co_carry_over(tmp_path):
    """brave/fred API keys cũng từng bị reset khi save — phải carry-over."""
    path = tmp_path / "settings.json"
    _write_settings_file(
        path,
        {
            "brave_api_key": "brave-x",
            "fred_api_key": "fred-y",
        },
    )
    loaded = SettingsService(path).load()
    assert loaded.advanced.brave_api_key == "brave-x"
    assert loaded.advanced.fred_api_key == "fred-y"

    SettingsService(path).save(loaded)
    reloaded = SettingsService(path).load()
    assert reloaded.advanced.brave_api_key == "brave-x"
    assert reloaded.advanced.fred_api_key == "fred-y"
