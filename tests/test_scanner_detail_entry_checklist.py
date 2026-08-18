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
        item for item in items if item["label"].startswith("Cho phép đặt lệnh")
    )
    assert permission["state"] == "fail"
    assert "không được phép" in permission["label"]
    # The label must name a real, human-readable reason — never a raw code
    # like SAFETY_* / GATE_* or an empty tail.
    assert "— do " in permission["label"]
    reason = permission["label"].split("do ", 1)[1].strip()
    assert reason
    assert "SAFETY_" not in reason and "GATE_" not in reason
    assert "_" not in reason  # concise status phrase, not a machine code


def test_checklist_panel_builds_without_crash() -> None:
    """Regression: opening the detail view must never crash building the grid.

    The "?" QToolButton previously referenced ``QtCore.QSize`` without importing
    ``QtCore`` — a runtime NameError that py_compile cannot catch (syntax only),
    so the app crashed exactly when the checklist panel rendered.  Runs the real
    panel build in a subprocess to exercise the live QToolButton path.
    """
    import os
    import subprocess
    import sys
    import textwrap

    code = textwrap.dedent(
        """
        import os
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget
        from ui.screens.scanner_detail_screen import ScannerDetailScreen
        from tests.test_scanner_detail_chart_for_blocked import _analyzed

        app = QApplication([])
        screen = ScannerDetailScreen()
        screen.row = _analyzed()
        screen.checklist_panel = QWidget()
        screen.checklist_panel.setLayout(QVBoxLayout(screen.checklist_panel))
        screen._refresh_checklist_panel()  # must not raise
        print("PANEL_OK")
        """
    )
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    assert proc.returncode == 0, (
        f"checklist panel crashed:\nSTDOUT={proc.stdout}\nSTDERR={proc.stderr}"
    )
    assert "PANEL_OK" in proc.stdout


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


def test_dialog_setup_card_resolves_from_lock_policy() -> None:
    """The M15 card was replaced by "ĐIỂM THIẾT LẬP" (setup/floor).

    ``_dialog_card_setup`` reads the canonical setup score and the locked default
    threshold floor, so a real routed candidate yields a real "1/2" style value
    (never "--") with a pass/fail accent — not the legacy M15 verdict.
    """
    screen = _screen()
    val, detail, accent = screen._dialog_card_setup()
    assert "/" in val, f"setup card must show setup/floor, got {val!r}"
    assert accent in ("#10b981", "#e11d48", "#f59e0b", "#94a3b8")


def test_legacy_m15_and_journal_dialog_references_removed() -> None:
    """The removed gates (M15, journal) must no longer be referenced by the
    "Xem đầy đủ" dialog — they were legacy V3 concepts.  Source-level guard so we
    can't regress to the stale cards without a test noticing."""
    import inspect

    from ui.screens import scanner_detail_screen

    src = inspect.getsource(scanner_detail_screen)
    assert "_dialog_card_setup" in src  # replacement card present
    assert "XÁC NHẬN M15" not in src
    assert "HIỆU SUẤT NHẬT KÝ" not in src
    assert "_dialog_card_journal_sample" not in src
    assert "_dialog_card_journal_exp" not in src