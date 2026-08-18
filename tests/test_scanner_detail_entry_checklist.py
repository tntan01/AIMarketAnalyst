"""Detail entry-checklist resolves every condition from real Scanner data.

Regression: the "Điều kiện vào lệnh" card showed 6 of 7 conditions as "chưa có
kết quả" for live Scanner rows because ``pair_to_ui_row`` emitted a minimal
``scanner_candidate_decision`` that lacked ``min_score`` / ``min_rr`` /
``eligible`` / ``entry_confirmation`` / ``execution.trade_allowed``.  Now the
adapter emits those from real source data (locked default threshold policy +
candidate), so a candidate routed through the real controller resolves all 6
conditions (M15 was a legacy-only gate and is removed here).

Here we drive a real BLOCKED candidate (only safety spread is abnormal) through
``_analyze_one_symbol`` -> ``pair_to_ui_row`` and assert the checklist reports a
real verdict for every condition (no "unknown"), includes the locked /2 RR floor
and /35 setup floor, and marks the trade not-allowed (blocked).
"""

from __future__ import annotations

from core.scanner_ui_adapter import _classify_price_vs_zone
from ui.screens.scanner_detail_screen import ScannerDetailScreen

from tests.test_scanner_detail_chart_for_blocked import _analyzed


def _screen() -> ScannerDetailScreen:
    screen = ScannerDetailScreen.__new__(ScannerDetailScreen)
    screen.row = _analyzed()
    return screen


def test_blocked_row_checklist_has_six_items() -> None:
    items = _screen()._build_entry_checklist()
    assert len(items) == 6
    labels = [item["label"] for item in items]
    assert any(l.startswith("Chiến lược") for l in labels)
    assert any(l.startswith("Điểm thiết lập") for l in labels)
    assert any(l.startswith("Vùng vào lệnh") for l in labels)
    # M15 is gone — the new Scanner has no M15 gate.
    assert not any(l.startswith("M15") for l in labels)


def test_every_condition_resolves_from_real_data() -> None:
    """No condition may stay "unknown" for a real routed candidate."""
    items = _screen()._build_entry_checklist()
    unknown = [item for item in items if item.get("state") == "unknown"]
    assert not unknown, (
        f"real Scanner row must resolve every condition, got unknowns: {unknown}"
    )


def test_floors_come_from_locked_default_threshold_policy() -> None:
    items = _screen()._build_entry_checklist()
    setup = next(item for item in items if item["label"].startswith("Điểm thiết lập"))
    assert "/35" in setup["label"]  # setup_floor
    rr = next(item for item in items if item["label"].startswith("R:R"))
    assert "/2" in rr["label"]  # min_risk_reward 2/1


def test_blocked_row_reports_trade_not_allowed() -> None:
    items = _screen()._build_entry_checklist()
    permission = next(
        item for item in items if item["label"].startswith("Quyền giao dịch")
    )
    assert permission["state"] == "fail"
    assert "không được phép" in permission["label"]


def test_entry_confirmation_resolves_not_unknown() -> None:
    items = _screen()._build_entry_checklist()
    entry = next(item for item in items if item["label"].startswith("Xác nhận điểm vào lệnh"))
    assert entry["state"] in ("pass", "fail")
    assert "chưa có dữ liệu" not in entry["label"]


# --- price_vs_zone column (Bảng kết quả quét "Vị trí") ---------------------

def test_classify_price_vs_zone_states() -> None:
    assert _classify_price_vs_zone(1.0900, 1.0920, 1.0910, 0.0010) == "in_zone"
    assert _classify_price_vs_zone(1.0900, 1.0920, 1.0900, 0.0010) == "in_zone"  # đúng biên
    # 1.0925 cách biên 0.0005 <= 0.5 ATR -> gần vùng.
    assert _classify_price_vs_zone(1.0900, 1.0920, 1.0925, 0.0010) == "near_zone"
    # 1.0930 cách biên 0.0010 > 0.5 ATR -> xa vùng.
    assert _classify_price_vs_zone(1.0900, 1.0920, 1.0930, 0.0010) == "far"
    # thiếu dữ liệu -> unknown (fail closed, không bao giờ lạc quan).
    assert _classify_price_vs_zone(None, 1.0920, 1.0910, 0.0010) == "unknown"
    assert _classify_price_vs_zone(1.0900, 1.0920, None, 0.0010) == "unknown"


def test_real_scanner_row_carries_price_vs_zone() -> None:
    """A real routed candidate (with a real plan) must emit a real classification,
    not a neutralized None/"unknown"."""
    row = _analyzed()
    zone = str(row.get("price_vs_zone") or "").strip().lower()
    assert zone in ("in_zone", "near_zone", "far"), (
        f"real Scanner row must classify price vs its plan zone, got {zone!r}"
    )