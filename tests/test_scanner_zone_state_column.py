"""Step 1: contract tests for the "Vùng" (price_vs_zone) scanner column.

Tests the binary display mapping, color contract, tooltip semantics, and
backend boundary logic BEFORE the UI is implemented.  These tests must FAIL
because the column doesn't exist yet — not because of bad fixtures.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from core.scanner import price_vs_entry_zone
from ui.screens.scanner_screen import ScannerTableModel
from ui.theme import DARK_PALETTE


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _real_row(zone_origin: str = "smc", price_vs_zone: str = "in_zone") -> dict:
    return {"zone_origin_class": zone_origin, "price_vs_zone": price_vs_zone}


# =========================================================================
# Column contract
# =========================================================================


def test_zone_column_exists_in_columns():
    """price_vs_zone must be a column key in ScannerTableModel.COLUMNS."""
    keys = [k for k, _ in ScannerTableModel.COLUMNS]
    assert "price_vs_zone" in keys, (
        "COLUMNS is missing price_vs_zone — Step 2 hasn't added the column yet"
    )


def test_zone_column_is_after_origin_class():
    """'Vùng' is placed immediately after 'Loại vùng'."""
    keys = [k for k, _ in ScannerTableModel.COLUMNS]
    if "price_vs_zone" not in keys:
        return  # let test_zone_column_exists_in_columns report the real failure
    origin_idx = keys.index("zone_origin_class")
    zone_idx = keys.index("price_vs_zone")
    assert zone_idx == origin_idx + 1, (
        f"price_vs_zone index={zone_idx}, expected={origin_idx + 1}"
    )


def test_zone_column_label_is_vung():
    labels = {k: v for k, v in ScannerTableModel.COLUMNS}
    if "price_vs_zone" not in labels:
        return
    assert labels["price_vs_zone"] == "Vùng"


# =========================================================================
# Display mapping — binary: Trong vùng / Ngoài vùng / --
# =========================================================================


def test_in_zone_displays_trong_vung():
    model = ScannerTableModel()
    row = _real_row(price_vs_zone="in_zone")
    assert model._display_value("price_vs_zone", "in_zone", row) == "Trong vùng"


def test_near_zone_displays_ngoai_vung():
    model = ScannerTableModel()
    row = _real_row(price_vs_zone="near_zone")
    assert model._display_value("price_vs_zone", "near_zone", row) == "Ngoài vùng"


def test_far_displays_ngoai_vung():
    model = ScannerTableModel()
    row = _real_row(price_vs_zone="far")
    assert model._display_value("price_vs_zone", "far", row) == "Ngoài vùng"


def test_unknown_displays_dash():
    model = ScannerTableModel()
    row = _real_row(price_vs_zone="unknown")
    assert model._display_value("price_vs_zone", "unknown", row) == "--"


def test_missing_key_displays_dash():
    model = ScannerTableModel()
    row = {"zone_origin_class": "smc"}
    assert model._display_value("price_vs_zone", None, row) == "--"


def test_malformed_value_displays_dash():
    model = ScannerTableModel()
    row = _real_row(price_vs_zone="invalid")
    assert model._display_value("price_vs_zone", "invalid", row) == "--"


def test_fallback_row_always_dash():
    """Fallback rows show '--' regardless of price_vs_zone value."""
    model = ScannerTableModel()
    row = {"zone_origin_class": "fallback", "price_vs_zone": "in_zone"}
    assert model._display_value("price_vs_zone", "in_zone", row) == "--"


def test_none_row_always_dash():
    """None rows show '--' regardless of price_vs_zone value."""
    model = ScannerTableModel()
    row = {"zone_origin_class": "none", "price_vs_zone": "in_zone"}
    assert model._display_value("price_vs_zone", "in_zone", row) == "--"


# =========================================================================
# Backend boundary logic (price_vs_entry_zone in core/scanner.py)
# =========================================================================


def test_boundary_low_is_in_zone():
    assert price_vs_entry_zone(1.0, [1.0, 2.0], 0.5) == "in_zone"


def test_boundary_high_is_in_zone():
    assert price_vs_entry_zone(2.0, [1.0, 2.0], 0.5) == "in_zone"


def test_middle_price_is_in_zone():
    assert price_vs_entry_zone(1.5, [1.0, 2.0], 0.5) == "in_zone"


def test_below_low_is_not_in_zone():
    result = price_vs_entry_zone(0.8, [1.0, 2.0], 0.5)
    assert result != "in_zone", f"price below zone must not be in_zone, got {result}"


def test_above_high_is_not_in_zone():
    result = price_vs_entry_zone(2.2, [1.0, 2.0], 0.5)
    assert result != "in_zone", f"price above zone must not be in_zone, got {result}"


def test_below_low_within_half_atr_is_near_zone():
    result = price_vs_entry_zone(0.96, [1.0, 2.0], 0.1)
    assert result == "near_zone", f"0.04 distance <= 0.05 ATR, got {result}"


def test_below_low_outside_half_atr_is_far():
    result = price_vs_entry_zone(0.94, [1.0, 2.0], 0.1)
    assert result == "far", f"0.06 distance > 0.05 ATR, got {result}"


# =========================================================================
# Color contract — near_zone and far share the same color
# =========================================================================


def test_near_zone_and_far_share_same_color():
    """Near and far must render the same color — no implied two-level UI."""
    model = ScannerTableModel()
    near_color = model._foreground(
        {"price_vs_zone": "near_zone", "zone_origin_class": "smc"},
        "price_vs_zone",
    )
    far_color = model._foreground(
        {"price_vs_zone": "far", "zone_origin_class": "smc"},
        "price_vs_zone",
    )
    assert near_color is not None
    assert far_color is not None
    assert near_color.name() == far_color.name(), (
        f"near={near_color.name()}, far={far_color.name()} must be identical"
    )


def test_in_zone_color_is_success():
    model = ScannerTableModel()
    color = model._foreground(
        {"price_vs_zone": "in_zone", "zone_origin_class": "smc"},
        "price_vs_zone",
    )
    assert color is not None
    assert color.name() == DARK_PALETTE.success


def test_near_zone_color_is_muted():
    model = ScannerTableModel()
    color = model._foreground(
        {"price_vs_zone": "near_zone", "zone_origin_class": "smc"},
        "price_vs_zone",
    )
    assert color is not None
    assert color.name() == DARK_PALETTE.text_muted


def test_unknown_color_is_muted_or_subtle():
    model = ScannerTableModel()
    color = model._foreground(
        {"price_vs_zone": "unknown", "zone_origin_class": "smc"},
        "price_vs_zone",
    )
    assert color is not None
    assert color.name() in (DARK_PALETTE.text_muted, DARK_PALETTE.text_subtle)


def test_fallback_row_color_is_muted_regardless_of_value():
    """Fallback origin rows must use muted color, not success."""
    model = ScannerTableModel()
    color = model._foreground(
        {"price_vs_zone": "in_zone", "zone_origin_class": "fallback"},
        "price_vs_zone",
    )
    assert color is not None
    assert color.name() in (DARK_PALETTE.text_muted, DARK_PALETTE.text_subtle), (
        f"fallback row must be muted, got {color.name()}"
    )


# =========================================================================
# Tooltip contract — scan-time semantics
# =========================================================================


def test_tooltip_mentions_scan_time():
    """Tooltip must make clear the price snapshot is from scan time."""
    _app()
    model = ScannerTableModel()
    row = {"zone_origin_class": "smc", "price_vs_zone": "in_zone"}
    model.set_rows([row])

    col_idx = next(
        i for i, (k, _) in enumerate(model.COLUMNS) if k == "price_vs_zone"
    )
    tooltip = model.data(model.index(0, col_idx), Qt.ItemDataRole.ToolTipRole)

    assert tooltip is not None
    assert "tại thời điểm quét" in tooltip, (
        f"Tooltip must mention scan-time semantics, got: {tooltip}"
    )


def test_tooltip_mentions_live_revalidation():
    """Tooltip must mention that live bid/ask revalidation happens pre-execution."""
    _app()
    model = ScannerTableModel()
    row = {"zone_origin_class": "smc", "price_vs_zone": "near_zone"}
    model.set_rows([row])

    col_idx = next(
        i for i, (k, _) in enumerate(model.COLUMNS) if k == "price_vs_zone"
    )
    tooltip = model.data(model.index(0, col_idx), Qt.ItemDataRole.ToolTipRole)

    assert tooltip is not None
    has_reval = "kiểm tra lại" in tooltip or "bid/ask" in tooltip or "live" in tooltip
    assert has_reval, (
        f"Tooltip must mention live revalidation, got: {tooltip}"
    )


# =========================================================================
# Help dialog — "Vùng" entry in COLUMN_HELP
# =========================================================================


def test_column_help_has_vung_entry():
    """ScannerColumnsHelpDialog.COLUMN_HELP must include a 'Vùng' entry."""
    from ui.screens.scanner_screen import ScannerColumnsHelpDialog

    labels = [item["column"] for item in ScannerColumnsHelpDialog.COLUMN_HELP]
    assert "Vùng" in labels, "COLUMN_HELP is missing 'Vùng' entry"


def test_column_help_vung_between_loai_vung_and_diem_thiet_lap():
    from ui.screens.scanner_screen import ScannerColumnsHelpDialog

    labels = [item["column"] for item in ScannerColumnsHelpDialog.COLUMN_HELP]
    if "Vùng" not in labels:
        return
    loai_idx = labels.index("Loại vùng")
    vung_idx = labels.index("Vùng")
    diem_idx = labels.index("Điểm thiết lập")
    assert loai_idx < vung_idx < diem_idx, (
        f"Order wrong: Loại vùng={loai_idx}, Vùng={vung_idx}, Điểm thiết lập={diem_idx}"
    )


# =========================================================================
# Regression — near_zone / far must stay distinct in ranking_score_breakdown
# =========================================================================


def test_near_zone_and_far_stay_distinct_in_ranking_breakdown():
    """near_zone and far must differ in proximity_quality even though UI
    shows the same Vietnamese text.  Ranking depends on this distinction."""
    from core.scanner_ranking_engine import rank_scanner_rows

    near_row = {
        "symbol": "EUR/USD", "best_side": "buy", "candidate_status": "READY_NOW",
        "selected_side": "buy", "setup_score": 70, "price_vs_zone": "near_zone",
        "market_regime": "trend_up", "risk_reward": 2.0,
    }
    far_row = {
        "symbol": "EUR/USD", "best_side": "buy", "candidate_status": "READY_NOW",
        "selected_side": "buy", "setup_score": 70, "price_vs_zone": "far",
        "market_regime": "trend_up", "risk_reward": 2.0,
    }

    ranked_near = rank_scanner_rows([near_row])[0]
    ranked_far = rank_scanner_rows([far_row])[0]

    near_prox = ranked_near["ranking_score_breakdown"]["proximity_quality"]
    far_prox = ranked_far["ranking_score_breakdown"]["proximity_quality"]

    assert near_prox != far_prox, (
        f"near_zone and far must stay distinct in ranking_score_breakdown, "
        f"got near={near_prox}, far={far_prox}"
    )
    assert near_prox > far_prox, (
        f"near_zone proximity must be higher than far, "
        f"got near={near_prox}, far={far_prox}"
    )
