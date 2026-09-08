"""Bước 4 gỡ Backtest (2026-09-08): luồng live không nạp module Backtest.

Chạy trong subprocess riêng để ``sys.modules`` không bị nhiễm bởi các test
engine backtest khác trong cùng phiên pytest. Không MT5/mạng/lệnh thật.
"""

from __future__ import annotations

import os
import subprocess
import sys


_CHECK_PROGRAM = r'''
import os, sys, tempfile
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FORBIDDEN = (
    "core.backtest_",
    "core.system_backtest_engine",
    "core.walk_forward_engine",
    "core.monte_carlo",
    "core.param_sensitivity",
    "core.vix_pair_backtest",
    "controllers.backtest_controller",
    "workers.backtest_worker",
    "workers.param_sweep_worker",
)

def clean(stage):
    bad = sorted(
        n for n in sys.modules if any(n.startswith(p) for p in FORBIDDEN)
    )
    assert not bad, f"{stage}: {bad}"

# 1) Entrypoint sản xuất (app, scanner, journal, settings, analysis, VIX).
import main
import controllers.app_controller
import controllers.scanner_controller
import controllers.journal_controller
import services.settings_service as ss
import services.journal_service
import workers.scanner_worker
import core.analysis_pipeline
import core.correlation_check as cc
import core.scanner_candidate_engine
import core.scanner_strategy_router
import core.symbol_scan_config as ssc
import ui.main_window
import ui.screens.scanner_screen
import ui.screens.scanner_detail_screen
import ui.screens.settings_screen
import ui.screens.journal_screen
import ui.screens.dashboard_screen
clean("import")

# 2) Lazy paths: settings load (revalidation fail-closed), payload builder,
#    VIX eligibility.
with tempfile.TemporaryDirectory() as tmp:
    service = ss.SettingsService(Path(tmp) / "settings.json")
    service.storage.save({
        "ai": {},
        "trading": {
            "enabled_symbols": ["EUR/USD"],
            "symbol_settings": {
                "EUR/USD": {
                    "backtest": True,
                    "backtest_status": "VALIDATED",
                    "backtest_config_id": "cfg-live-check",
                    "min_score": 68,
                },
            },
        },
    })
    loaded = service.load()
    cfg = loaded.trading.symbol_settings["EUR/USD"]
    # Bước 4b/6: không tái kiểm định khi load; model không còn field
    # evidence — quyền suy dẫn từ trạng thái hiệu lực cũ (thiếu expiry ⇒ TẮT).
    assert cfg.auto_trade_permitted is False
    assert cfg.scan_enabled is True         # bảo toàn quét (Bước 2)
    clean("settings-load")
    assert ssc.build_symbol_auto_trade(loaded.trading.symbol_settings, ["EUR/USD"]) == {}
    clean("payload-builder")

cc._load_vix_sensitivity()
clean("vix-eligibility")

# 3) API trung lập hoạt động đúng (Bước 4b: hub live là symbol_scan_config).
from config.settings import SymbolScanSettings
from core.symbol_scan_config import (
    analysis_thresholds_for_symbol,
    serialize_symbol_auto_trade_config,
)
from core.scanner_strategy_router import validate_auto_trade_config

assert analysis_thresholds_for_symbol(None) is None
assert serialize_symbol_auto_trade_config(None, symbol="EUR/USD") is None
status, reasons = validate_auto_trade_config({"side": "buy"}, {"symbol": "EUR/USD"})
assert status == "INVALID" and "BACKTEST_REGIME_MISSING" in reasons
clean("symbol-config")
print("IMPORT_GRAPH_CLEAN")
'''


def test_live_flows_never_load_backtest_modules() -> None:
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, "-c", _CHECK_PROGRAM],
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )
    assert result.returncode == 0, (
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "IMPORT_GRAPH_CLEAN" in result.stdout


def test_backtest_engine_modules_are_deleted() -> None:
    """Bước 5 (2026-09-09): engine + shim Backtest đã xóa khỏi codebase.

    Guard chống tái xuất hiện: mọi import các module này phải fail. Dữ liệu
    người dùng (settings.json evidence, snapshot app_data/backtests) KHÔNG bị
    xóa — chỉ code engine.
    """

    import importlib
    import pytest

    deleted = [
        "core.backtest_engine",
        "core.backtest_feedback",
        "core.backtest_config",
        "core.backtest_config_validation",
        "core.backtest_provenance",
        "core.backtest_contract",
        "core.backtest_evidence_contract",
        "core.backtest_release",
        "core.backtest_statistics",
        "core.backtest_market_data",
        "core.backtest_execution",
        "core.backtest_execution_parity",
        "core.backtest_candidate_ledger",
        "core.backtest_golden_replay",
        "core.backtest_to_scanner_config",
        "core.backtest_advanced",
        "core.backtest_history",
        "core.backtest_migration",
        "core.backtest_portfolio_engine",
        "core.backtest_presentation",
        "core.backtest_validation_replay",
        "core.system_backtest_engine",
        "core.walk_forward_engine",
        "core.monte_carlo",
        "core.param_sensitivity",
        "core.plan_replay",
        "core.pattern_confidence",
        "core.scanner_symbol_config",
        "core.scanner_config_validation",
        "core.scanner_config_contract",
        "controllers.backtest_controller",
        "workers.backtest_worker",
        "workers.param_sweep_worker",
    ]
    for name in deleted:
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(name)


def test_shared_neutral_modules_survive_engine_removal() -> None:
    """Các hàm dùng chung đã tách (còn người dùng live) phải tồn tại."""

    import core.symbol_scan_config as ssc
    import core.vix_pair_sensitivity as vix
    import core.vix_pair_backtest as vix_producer  # producer của data VIX live
    import ui.rich_text as rich_text

    assert callable(ssc.build_symbol_auto_trade)
    assert callable(ssc.analysis_thresholds_for_symbol)
    assert callable(ssc.serialize_symbol_auto_trade_config)
    assert callable(vix.is_sensitivity_map_eligible)
    assert callable(vix.sensitivity_map_ineligibility_reason)
    assert callable(vix_producer.compute_vix_pair_sensitivity)
    assert callable(rich_text.format_ai_markdown_to_html)
