"""Phase 10: import-purity and API contract for ui.scanner_rr_formatters.

Verifies:
- Module imports without requiring QApplication / PyQt.
- All 4 public helper functions are present and callable.
- Smoke output matches expected format.
"""

from __future__ import annotations

import sys


class TestImportPurity:
    """ui.scanner_rr_formatters must be importable without Qt."""

    def test_import_without_qapplication(self):
        """Module must not require QApplication construction."""
        # If this import succeeds without Qt initialized, the module is pure.
        from ui.scanner_rr_formatters import (
            format_order_rr_text,
            format_order_rr_tooltip,
            format_order_entry_tooltip,
            enrich_order_note_with_current_rr,
        )
        assert callable(format_order_rr_text)
        assert callable(format_order_rr_tooltip)
        assert callable(format_order_entry_tooltip)
        assert callable(enrich_order_note_with_current_rr)

    def test_module_has_no_pyqt_imports(self):
        """Verify the module source doesn't import PyQt."""
        from pathlib import Path
        src = (Path(__file__).parents[1] / "ui" / "scanner_rr_formatters.py").read_text()
        for qt_mod in ("PyQt", "QtCore", "QtGui", "QtWidgets", "QApplication"):
            assert qt_mod not in src, \
                f"ui.scanner_rr_formatters must not import {qt_mod}"


class TestPublicAPI:
    """All 4 helpers must be present in the module namespace."""

    def test_all_helpers_present(self):
        import ui.scanner_rr_formatters as fm
        for name in (
            "format_order_rr_text",
            "format_order_rr_tooltip",
            "format_order_entry_tooltip",
            "enrich_order_note_with_current_rr",
        ):
            assert hasattr(fm, name), f"Missing {name}"
            assert callable(getattr(fm, name))


class TestSmokeOutput:
    """Quick smoke test — detailed formatting is covered by Phase 8 tests."""

    def test_format_order_rr_text_base_primary_with_range(self):
        from ui.scanner_rr_formatters import format_order_rr_text
        result = format_order_rr_text({
            "risk_reward_range": {"best": 2.5, "base": 1.8, "worst": 1.2},
        })
        assert result == "1.8 (1.2–2.5)"

    def test_format_order_rr_text_range_without_base_falls_back_to_best(self):
        from ui.scanner_rr_formatters import format_order_rr_text
        result = format_order_rr_text({
            "risk_reward_range": {"best": 2.5, "worst": 1.2},
        })
        assert result == "2.5 (1.2–2.5)"

    def test_format_order_rr_tooltip_contains_best(self):
        from ui.scanner_rr_formatters import format_order_rr_tooltip
        result = format_order_rr_tooltip({
            "risk_reward_range": {"best": 2.0, "base": 1.5, "worst": 1.0},
        })
        assert "Best" in result
        assert "Base" in result

    def test_format_order_entry_tooltip_contains_live(self):
        from ui.scanner_rr_formatters import format_order_entry_tooltip
        result = format_order_entry_tooltip({
            "entry_zone": [1.0970, 1.0990],
            "current_entry_price": 1.0985,
            "current_price_in_entry_zone": True,
        })
        assert "Live" in result

    def test_enrich_order_note_appends_current_rr(self):
        from ui.scanner_rr_formatters import enrich_order_note_with_current_rr
        result = enrich_order_note_with_current_rr({
            "note": "Sẵn sàng",
            "current_effective_rr": 1.75,
            "current_entry_price": 1.0980,
            "current_price_in_entry_zone": True,
        })
        assert "Live" in result
        assert "RR=1.75" in result
