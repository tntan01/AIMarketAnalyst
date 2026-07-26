from __future__ import annotations

import inspect
from pathlib import Path

from core.backtest_migration import migrate_snapshot_payload
from services.settings_service import SettingsService


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REMOVED_BACKTEST_UI_NAMES = (
    "_on_tab_changed",
    "_build_equity_curve_html",
    "_do_apply_config",
    "_section_box",
    "_field_cell",
    "_symbol_cell",
    "BacktestInputHelpDialog",
    "_show_input_help",
    "set_equity_chart_visible",
    "_refresh_progress_bar_style",
    "_refresh_tab_styles",
)


def test_backtest_screen_has_no_confirmed_dead_ui_contracts() -> None:
    import ui.screens.backtest_screen as screen_module

    for name in REMOVED_BACKTEST_UI_NAMES:
        assert not hasattr(screen_module.BacktestScreen, name)
    assert not hasattr(screen_module, "BacktestInputHelpDialog")


def test_obsolete_backtest_flags_are_read_compatible_but_not_rewritten(
    tmp_path: Path,
) -> None:
    service = SettingsService(tmp_path / "settings.json")
    service.storage.save({
        "features": {
            "scanner_architecture_v2": True,
            "auto_trade_v2": True,
            "backtest_config_v2": True,
            "backtest_engine_v2": True,
            "smc_scoring_mode": "v2",
        },
        "trading": {
            "enabled_symbols": ["EUR/USD"],
            "symbol_settings": {
                "EUR/USD": {
                    "enabled": True,
                    "min_score": 77,
                    "backtest": True,
                    "backtest_status": "VALIDATED",
                    "backtest_validation_fingerprint": "evidence-kept",
                }
            },
        },
    })

    settings = service.load()
    symbol = settings.trading.symbol_settings["EUR/USD"]
    assert settings.features.scanner_architecture_v2 is True
    assert settings.features.auto_trade_v2 is True
    assert settings.features.smc_scoring_mode == "v2"
    assert not hasattr(settings.features, "backtest_config_v2")
    assert not hasattr(settings.features, "backtest_engine_v2")
    assert symbol.min_score == 77
    # Historical evidence is retained, but an incomplete old payload remains
    # fail-closed instead of being trusted as a current VALIDATED config.
    assert symbol.backtest_status == "VERSION_MISMATCH"
    assert symbol.backtest_validation_fingerprint == "evidence-kept"

    service.save(settings)
    stored = service.storage.load()
    assert "backtest_config_v2" not in stored["features"]
    assert "backtest_engine_v2" not in stored["features"]
    stored_symbol = stored["trading"]["symbol_settings"]["EUR/USD"]
    assert stored_symbol["min_score"] == 77
    assert stored_symbol["backtest_validation_fingerprint"] == "evidence-kept"


def test_strategy_router_has_no_dependency_on_obsolete_backtest_flags() -> None:
    import core.scanner_strategy_router as router

    source = inspect.getsource(router)
    assert "backtest_config_v2" not in source
    assert "backtest_engine_v2" not in source


def test_legacy_snapshot_migration_preserves_historical_evidence() -> None:
    source = {
        "mode": "system_backtest",
        "backtest_contract": {"engine_version": "legacy-engine"},
        "summary": {"total_trades": 12},
        "validation_replay": {"status": "COMPLETE", "dataset_hash": "abc"},
        "walk_forward": {"status": "COMPLETE", "windows": [1, 2]},
        "custom_evidence": {"keep": True},
    }

    migrated = migrate_snapshot_payload(source)

    assert migrated["summary"] == source["summary"]
    assert migrated["validation_replay"] == source["validation_replay"]
    assert migrated["walk_forward"] == source["walk_forward"]
    assert migrated["custom_evidence"] == {"keep": True}
    assert migrated["lifecycle"]["status"] == "LEGACY_RESEARCH"


def test_temporary_backtest_patch_script_is_removed() -> None:
    assert not (PROJECT_ROOT / "scratch" / "fix_backtest_screen.py").exists()
