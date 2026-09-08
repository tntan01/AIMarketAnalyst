"""Bước 4b gỡ Backtest (2026-09-08): Scanner/auto-trade độc lập kiểm định.

Guard tests: Analyze live không còn nội dung mô phỏng, Nhật ký không đụng
Backtest, và các luồng live không import module evidence engine-side.
Thuần source-level + hàm thuần — không Qt, không MT5, không lệnh thật.
"""

from __future__ import annotations

import ast
from pathlib import Path

import core.analysis_pipeline as pipeline
from core.scanner_strategy_router import (
    validate_auto_trade_config,
)
from core.symbol_scan_config import (
    analysis_thresholds_for_symbol,
    serialize_symbol_auto_trade_config,
)
from config.settings import SymbolScanSettings

ROOT = Path(__file__).resolve().parents[1]


def _imported_modules(path: Path) -> set[str]:
    """Mọi module được import (top-level + function-level) trong file."""

    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_analyze_live_has_no_simulation_content():
    """Req 4: plan replay + pattern confidence đã rời luồng Analyze."""

    path = ROOT / "core" / "analysis_pipeline.py"
    imported = _imported_modules(path)
    assert not any(
        name.startswith(("core.plan_replay", "core.pattern_confidence",
                         "core.backtest_engine", "core.backtest_feedback"))
        for name in imported
    ), sorted(imported)
    assert not hasattr(pipeline, "_conditional_backtest")
    # Kết quả analyze không còn key mô phỏng (hành vi trước: có "backtest"
    # và "pattern_backtest"; sau: không — không có công thức bù).
    source = path.read_text(encoding="utf-8")
    assert '"pattern_backtest"' not in source


def test_journal_stack_has_zero_backtest_dependency():
    """Req 5: Nhật ký giữ nguyên, không import Backtest (trực tiếp/gián tiếp)."""

    journal_files = [
        ROOT / "controllers" / "journal_controller.py",
        ROOT / "services" / "journal_service.py",
        ROOT / "services" / "journal_models.py",
        ROOT / "services" / "journal_converters.py",
        ROOT / "core" / "journal_feedback_engine.py",
        ROOT / "core" / "trade_mistake_detector.py",
        ROOT / "core" / "execution_quality_engine.py",
    ]
    for path in journal_files:
        text = path.read_text(encoding="utf-8")
        assert "backtest" not in text.lower(), path.name


def test_live_scanner_modules_do_not_import_evidence_modules():
    """Req 2/3: các module live không import evidence/engine backtest."""

    live_files = [
        ROOT / "core" / "scanner_strategy_router.py",
        ROOT / "core" / "symbol_scan_config.py",
        ROOT / "core" / "scanner_candidate_engine.py",
        ROOT / "core" / "analysis_pipeline.py",
        ROOT / "services" / "settings_service.py",
        ROOT / "ui" / "screens" / "settings_screen.py",
        ROOT / "ui" / "screens" / "scanner_screen.py",
    ]
    forbidden = (
        "core.backtest_",
        "core.system_backtest_engine",
        "core.walk_forward_engine",
        "core.monte_carlo",
        "core.param_sensitivity",
        "core.vix_pair_backtest",
    )
    for path in live_files:
        imported = _imported_modules(path)
        bad = sorted(
            name
            for name in imported
            if any(name.startswith(prefix) for prefix in forbidden)
        )
        assert not bad, (path.name, bad)


def test_lean_validator_keeps_only_live_checks():
    # Payload gọn hợp lệ ⇒ VALIDATED.
    cfg = SymbolScanSettings(
        auto_trade_regime="range",
        auto_trade_side="best",
        min_score=66,
        min_expected_rr=1.4,
    )
    payload = serialize_symbol_auto_trade_config(cfg, symbol="EUR/USD")
    status, reasons = validate_auto_trade_config(payload, {"symbol": "EUR/USD"})
    assert status == "VALIDATED"
    assert reasons == ()

    # Evidence lifecycle KHÔNG được đọc: payload không status/fingerprint
    # vẫn hợp lệ; hết hạn không phải khái niệm của validator lean.
    assert "status" not in payload
    status, _ = validate_auto_trade_config(
        {**payload, "expires_at": "2020-01-01T00:00:00+00:00"},
        {"symbol": "EUR/USD"},
    )
    assert status == "VALIDATED"

    # Các kiểm tra an toàn live vẫn fail-closed.
    status, reasons = validate_auto_trade_config(payload, {"symbol": "GBP/USD"})
    assert status == "INVALID" and "BACKTEST_SYMBOL_MISMATCH" in reasons
    status, reasons = validate_auto_trade_config(
        {**payload, "min_rr": -1}, {"symbol": "EUR/USD"}
    )
    assert status == "INVALID" and "BACKTEST_MIN_RR_MISSING" in reasons
    status, reasons = validate_auto_trade_config(
        "garbage", {"symbol": "EUR/USD"}
    )
    assert status == "INVALID" and "BACKTEST_CONFIG_MALFORMED" in reasons


def test_decision_thresholds_read_explicit_analysis_min_rr():
    """Req 1: ngưỡng RR Decision Engine là cấu hình tường minh."""

    cfg = SymbolScanSettings(analysis_min_rr=1.6)
    assert analysis_thresholds_for_symbol(cfg)["min_rr"] == 1.6
    # Ngưỡng luôn đến từ analysis_min_rr tường minh (Bước 6: model không
    # còn cờ legacy).
    explicit = SymbolScanSettings(analysis_min_rr=2.2)
    assert analysis_thresholds_for_symbol(explicit)["min_rr"] == 2.2
