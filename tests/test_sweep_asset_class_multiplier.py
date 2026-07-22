"""Tests for scripts/sweep_asset_class_multiplier.py — pure-function unit tests.

These tests run WITHOUT MT5. They verify override/restore, argument parsing,
markdown formatting, and recommendation logic.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

import pytest

import core.risk_engine as _re
from scripts.sweep_asset_class_multiplier import (
    _override_multiplier,
    _restore_multipliers,
    _get_multiplier_for,
    build_parser,
    build_sweep_report,
    build_sweep_json,
    find_best_multiplier,
    SweepRow,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_row(
    multiplier: float = 1.0,
    symbol: str = "XAU/USD",
    total_trades: int = 50,
    win_rate: float = 0.52,
    expectancy_r: float = 0.15,
    profit_factor: float = 1.3,
    max_drawdown_r: float = 5.0,
    average_r: float = 0.30,
    wf_verdict: str = "ROBUST",
    robustness_score: float | None = 72.0,
    error: str | None = None,
) -> SweepRow:
    return {
        "multiplier": multiplier,
        "symbol": symbol,
        "error": error,
        "total_trades": total_trades,
        "win_rate": win_rate,
        "expectancy_r": expectancy_r,
        "profit_factor": profit_factor,
        "max_drawdown_r": max_drawdown_r,
        "average_r": average_r,
        "wf_verdict": wf_verdict,
        "robustness_score": robustness_score,
        "elapsed_seconds": 5.0,
    }


# ── Override / Restore ───────────────────────────────────────────────────────


class TestMultiplierOverride:
    """Tests for _override_multiplier / _restore_multipliers safety."""

    def test_override_and_restore_metals(self):
        """Override metals, verify value changes, restore, verify original."""
        original = _get_multiplier_for("metals")
        assert original == 1.0, f"Expected metals=1.0, got {original}"

        _override_multiplier("metals", 1.3)
        try:
            assert _get_multiplier_for("metals") == 1.3
            assert _get_multiplier_for("forex") == 1.0  # unchanged
        finally:
            _restore_multipliers()

        assert _get_multiplier_for("metals") == 1.0, (
            f"Restore failed: metals={_get_multiplier_for('metals')}"
        )

    def test_override_and_restore_crypto(self):
        """Override crypto, verify value changes, restore, verify original."""
        original = _get_multiplier_for("crypto")
        assert original == 1.0

        _override_multiplier("crypto", 1.6)
        try:
            assert _get_multiplier_for("crypto") == 1.6
        finally:
            _restore_multipliers()

        assert _get_multiplier_for("crypto") == 1.0

    def test_restore_after_exception(self):
        """Restore must run even when an exception occurs mid-sweep."""
        original = _get_multiplier_for("metals")

        try:
            _override_multiplier("metals", 1.5)
            assert _get_multiplier_for("metals") == 1.5
            raise RuntimeError("simulated backtest failure")
        except RuntimeError:
            pass
        finally:
            _restore_multipliers()

        assert _get_multiplier_for("metals") == original, (
            "Multiplier NOT restored after exception — state leak!"
        )

    def test_double_override_uses_first_snapshot(self):
        """Calling _override_multiplier twice uses the ORIGINAL as snapshot."""
        _override_multiplier("metals", 1.2)
        try:
            _override_multiplier("metals", 1.8)  # second override
            try:
                assert _get_multiplier_for("metals") == 1.8
            finally:
                _restore_multipliers()
            # After restore, should be back to 1.0 (original), not 1.2
            assert _get_multiplier_for("metals") == 1.0
        finally:
            _restore_multipliers()

    def test_restore_idempotent(self):
        """Calling _restore_multipliers twice without override is safe."""
        # First call: nothing to restore (no override was done)
        _restore_multipliers()  # should not raise
        # After a normal cycle
        _override_multiplier("metals", 1.3)
        _restore_multipliers()
        # Second restore should be a no-op
        _restore_multipliers()  # should not raise
        assert _get_multiplier_for("metals") == 1.0


# ── Argparse ─────────────────────────────────────────────────────────────────


class TestArgparse:
    """Tests for CLI argument parsing."""

    def test_metals_defaults(self):
        parser = build_parser()
        args = parser.parse_args(["--asset-class", "metals"])
        assert args.asset_class == "metals"
        # Symbols not specified → None (defaults resolved in main)
        assert args.symbols is None
        assert args.values is None
        assert args.is_months == 6
        assert args.oos_months == 3

    def test_crypto_defaults(self):
        parser = build_parser()
        args = parser.parse_args(["--asset-class", "crypto"])
        assert args.asset_class == "crypto"

    def test_invalid_asset_class_rejected(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--asset-class", "forex"])

    def test_custom_values_and_symbols(self):
        parser = build_parser()
        args = parser.parse_args([
            "--asset-class", "crypto",
            "--symbols", "BTC/USD", "ETH/USD",
            "--values", "1.0", "1.5", "2.0",
        ])
        assert args.symbols == ["BTC/USD", "ETH/USD"]
        assert args.values == [1.0, 1.5, 2.0]

    def test_custom_dates(self):
        parser = build_parser()
        args = parser.parse_args([
            "--asset-class", "metals",
            "--start", "2025-01-01",
            "--end", "2025-06-30",
        ])
        assert args.start == "2025-01-01"
        assert args.end == "2025-06-30"


# ── Markdown Report ──────────────────────────────────────────────────────────


class TestSweepReport:
    """Tests for build_sweep_report() formatting."""

    def test_basic_table_structure(self):
        rows = [
            _make_row(multiplier=1.0, symbol="XAU/USD", expectancy_r=0.10),
            _make_row(multiplier=1.2, symbol="XAU/USD", expectancy_r=0.15),
        ]
        config = {
            "start": "2024-01-01", "end": "2025-01-01",
            "is_months": 6, "oos_months": 3,
            "values": [1.0, 1.2],
        }
        report = build_sweep_report("metals", rows, config)

        assert "## XAU/USD" in report
        assert "| Multiplier | Trades |" in report
        assert "| 1.0 |" in report
        assert "| 1.2 |" in report
        assert "+0.10" in report
        assert "+0.15" in report

    def test_sorted_by_expectancy_descending(self):
        """Higher expectancy row must appear FIRST in the table."""
        rows = [
            _make_row(multiplier=1.0, symbol="XAU/USD", expectancy_r=0.05),
            _make_row(multiplier=1.3, symbol="XAU/USD", expectancy_r=0.25),
            _make_row(multiplier=1.1, symbol="XAU/USD", expectancy_r=0.10),
        ]
        config = {
            "start": "2024-01-01", "end": "2025-01-01",
            "is_months": 6, "oos_months": 3,
            "values": [1.0, 1.1, 1.3],
        }
        report = build_sweep_report("metals", rows, config)

        # Find the data rows for XAU/USD
        table_start = report.index("## XAU/USD")
        table_section = report[table_start:]

        # 1.3 should appear before 1.1, which appears before 1.0
        idx_1_3 = table_section.index("| 1.3 |")
        idx_1_1 = table_section.index("| 1.1 |")
        idx_1_0 = table_section.index("| 1.0 |")
        assert idx_1_3 < idx_1_1 < idx_1_0, (
            f"Expected 1.3 < 1.1 < 1.0 but got {idx_1_3} < {idx_1_1} < {idx_1_0}"
        )

    def test_low_trade_warning(self):
        """Rows with < 30 trades must show ⚠ LOW SAMPLE."""
        rows = [
            _make_row(multiplier=1.0, symbol="XAU/USD", total_trades=15),
        ]
        config = {
            "start": "2024-01-01", "end": "2025-01-01",
            "is_months": 6, "oos_months": 3,
            "values": [1.0],
        }
        report = build_sweep_report("metals", rows, config)
        assert "⚠ LOW SAMPLE" in report

    def test_no_low_trade_warning_when_sufficient(self):
        """Rows with >= 30 trades must NOT show ⚠ LOW SAMPLE."""
        rows = [
            _make_row(multiplier=1.0, symbol="XAU/USD", total_trades=30),
        ]
        config = {
            "start": "2024-01-01", "end": "2025-01-01",
            "is_months": 6, "oos_months": 3,
            "values": [1.0],
        }
        report = build_sweep_report("metals", rows, config)
        assert "⚠ LOW SAMPLE" not in report

    def test_overfitting_warning(self):
        """WF verdict OVERFITTING must show in warning."""
        rows = [
            _make_row(multiplier=1.0, symbol="XAU/USD", total_trades=50,
                      wf_verdict="OVERFITTING"),
        ]
        config = {
            "start": "2024-01-01", "end": "2025-01-01",
            "is_months": 6, "oos_months": 3,
            "values": [1.0],
        }
        report = build_sweep_report("metals", rows, config)
        assert "WF: OVERFITTING" in report

    def test_error_in_row(self):
        rows = [
            _make_row(multiplier=1.0, symbol="XAU/USD", total_trades=0,
                      error="MT5 timeout"),
        ]
        config = {
            "start": "2024-01-01", "end": "2025-01-01",
            "is_months": 6, "oos_months": 3,
            "values": [1.0],
        }
        report = build_sweep_report("metals", rows, config)
        assert "ERROR: MT5 timeout" in report

    def test_multiple_symbols_in_report(self):
        """Each symbol gets its own section."""
        rows = [
            _make_row(multiplier=1.0, symbol="XAU/USD", expectancy_r=0.10),
            _make_row(multiplier=1.0, symbol="XAG/USD", expectancy_r=0.08),
        ]
        config = {
            "start": "2024-01-01", "end": "2025-01-01",
            "is_months": 6, "oos_months": 3,
            "values": [1.0],
        }
        report = build_sweep_report("metals", rows, config)
        assert "## XAG/USD" in report
        assert "## XAU/USD" in report


# ── Recommendation Logic ─────────────────────────────────────────────────────


class TestFindBestMultiplier:
    """Tests for find_best_multiplier()."""

    def test_returns_highest_expectancy(self):
        rows = [
            _make_row(multiplier=1.0, expectancy_r=0.10),
            _make_row(multiplier=1.2, expectancy_r=0.18),
            _make_row(multiplier=1.3, expectancy_r=0.12),
        ]
        best = find_best_multiplier(rows)
        assert best is not None
        assert best["multiplier"] == 1.2
        assert best["expectancy_r"] == 0.18

    def test_filters_low_trades(self):
        rows = [
            _make_row(multiplier=1.0, total_trades=25, expectancy_r=0.99),
            _make_row(multiplier=1.2, total_trades=50, expectancy_r=0.10),
        ]
        best = find_best_multiplier(rows)
        assert best is not None
        assert best["multiplier"] == 1.2  # 1.0 excluded due to < 30 trades

    def test_filters_overfitting(self):
        rows = [
            _make_row(multiplier=1.0, total_trades=50, expectancy_r=0.50,
                      wf_verdict="OVERFITTING"),
            _make_row(multiplier=1.2, total_trades=50, expectancy_r=0.10,
                      wf_verdict="ROBUST"),
        ]
        best = find_best_multiplier(rows)
        assert best is not None
        assert best["multiplier"] == 1.2

    def test_filters_inconclusive(self):
        rows = [
            _make_row(multiplier=1.0, total_trades=50, expectancy_r=0.99,
                      wf_verdict="INCONCLUSIVE"),
        ]
        best = find_best_multiplier(rows)
        assert best is None, "INCONCLUSIVE must be filtered out"

    def test_returns_none_when_all_filtered(self):
        """All rows have OVERFITTING or INCONCLUSIVE → None."""
        rows = [
            _make_row(multiplier=1.0, wf_verdict="OVERFITTING"),
            _make_row(multiplier=1.2, wf_verdict="INCONCLUSIVE"),
            _make_row(multiplier=1.4, total_trades=10, wf_verdict="ROBUST"),
        ]
        best = find_best_multiplier(rows)
        assert best is None

    def test_filters_errors(self):
        rows = [
            _make_row(multiplier=1.0, error="MT5 failure"),
            _make_row(multiplier=1.2, total_trades=30, expectancy_r=0.10),
        ]
        best = find_best_multiplier(rows)
        assert best is not None
        assert best["multiplier"] == 1.2

    def test_report_says_no_reliable_when_all_filtered(self):
        """build_sweep_report must print 'không có giá trị nào đủ tin cậy'
        when find_best_multiplier returns None."""
        rows = [
            _make_row(multiplier=1.0, total_trades=50, expectancy_r=0.50,
                      wf_verdict="OVERFITTING"),
            _make_row(multiplier=1.2, total_trades=50, expectancy_r=0.10,
                      wf_verdict="INCONCLUSIVE"),
        ]
        config = {
            "start": "2024-01-01", "end": "2025-01-01",
            "is_months": 6, "oos_months": 3,
            "values": [1.0, 1.2],
        }
        report = build_sweep_report("crypto", rows, config)
        assert "Không có giá trị nào đủ tin cậy" in report

    def test_report_has_recommendation_when_valid(self):
        rows = [
            _make_row(multiplier=1.0, total_trades=50, expectancy_r=0.10,
                      wf_verdict="ROBUST"),
            _make_row(multiplier=1.3, total_trades=50, expectancy_r=0.18,
                      wf_verdict="ROBUST"),
        ]
        config = {
            "start": "2024-01-01", "end": "2025-01-01",
            "is_months": 6, "oos_months": 3,
            "values": [1.0, 1.3],
        }
        report = build_sweep_report("metals", rows, config)
        assert "Đề xuất" in report
        assert "1.3" in report  # best multiplier


# ── JSON Export ──────────────────────────────────────────────────────────────


class TestSweepJson:
    """Tests for build_sweep_json()."""

    def test_json_structure(self):
        rows = [
            _make_row(multiplier=1.0, symbol="BTC/USD"),
            _make_row(multiplier=1.4, symbol="BTC/USD"),
        ]
        config = {
            "asset_class": "crypto",
            "symbols": ["BTC/USD"],
            "values": [1.0, 1.4],
            "start": "2025-01-01",
            "end": "2025-06-30",
            "is_months": 6,
            "oos_months": 3,
        }
        data = build_sweep_json("crypto", rows, config)
        assert data["asset_class"] == "crypto"
        assert len(data["results"]) == 2
        assert data["config"]["values"] == [1.0, 1.4]
        assert data["recommendation"] is not None
        # Verify it's JSON-serializable
        json.dumps(data, indent=2, ensure_ascii=False, default=str)
