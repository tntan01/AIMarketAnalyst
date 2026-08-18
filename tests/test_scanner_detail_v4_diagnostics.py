"""Detail-screen Chẩn đoán tab contract for Scanner rows (17/08/2026).

Scanner rows (``pipeline_route == "scanner"``) carry their scores,
statuses and reason codes directly on the UI row — NOT inside the legacy
``analysis_result`` (which holds ``scenario_scores`` / ``pipeline_diagnostics``
that the rows never emit).  Regression: the Chẩn đoán tab previously rendered
only the legacy builders, so it came out empty for these rows.
``_refresh_diagnostics`` now dispatches to native builders; here we assert they
render the component scores and gate blocks from the real row.

These tests drive the builders on a real ``_analyze_one_symbol`` row through
a minimal (non-QWebEngineView) screen stub, because constructing a full
``ScannerDetailScreen`` instantiates a chart view that segfaults headless.
"""

from __future__ import annotations

import ui.screens.scanner_detail_screen as mod
from controllers.scanner_controller import _analyze_one_symbol
from core.scanner_live_producers import build_live_market_safety_context
from ui.screens.scanner_detail_screen import ScannerDetailScreen

from tests.test_scanner_release import NOW, _zoned_candles


def _blocked_row() -> dict:
    """Produce a real BLOCKED row via the live controller path."""
    d1, h4, h1 = _zoned_candles()
    m15 = h1[-40:]
    safety = build_live_market_safety_context(
        "XAU/USD", NOW,
        terminal_connected=True, broker_logged_in=True,
        connectivity_checked_at=NOW, last_candle_time_utc=NOW,
        data_checked_at=NOW, last_tick_time_utc=NOW,
        spread_points=260.0, spread_checked_at=NOW,
        news_source_verified=True, news_checked_at=NOW,
        volatility_ratio=1.0, volatility_checked_at=NOW,
    )
    pkt = {
        "symbol": "XAU/USD",
        "broker_symbol": "XAUUSDc",
        "candles": {"D1": d1, "H4": h4, "H1": h1, "M15": m15},
        "m15_candles": m15,
        "data_quality": {},
        "macro_context": {},
        "quote_to_usd": None,
        "input_timestamps": {},
        "v4_safety": safety,
        "v4_captured_at": NOW,
        "account": None,
        "portfolio": None,
        "journal": None,
    }
    return _analyze_one_symbol(
        pkt,
        correlation_context={},
        freshness_multiplier=1.0,
        contract_size_overrides={},
        analysis_input_kwargs={},
        closed_trades=[],
        account_guard_settings={},
        order_policy=None,
    )


def _stub_screen(row: dict) -> ScannerDetailScreen:
    screen = ScannerDetailScreen.__new__(ScannerDetailScreen)
    screen.row = row
    screen._is_light_theme = lambda: True
    return screen


def test_row_is_with_side_scores() -> None:
    row = _blocked_row()
    assert row["pipeline_route"] == "scanner"
    assert row["candidate_status"] == "BLOCKED"
    sides = row.get("side_scores") or []
    assert len(sides) == 2, "row must expose per-side component scores"
    for s in sides:
        assert s["side"] in ("buy", "sell")
        assert "technical_signal_score" in s and "setup_score" in s


def test_status_resolves_via_canonical() -> None:
    row = _blocked_row()
    assert _stub_screen(row)._canonical_status() == "BLOCKED"


def test_route_html_annotates_status_and_side() -> None:
    screen = _stub_screen(_blocked_row())
    html = screen._diag_route_html(light=True)
    assert "Scanner — Hướng" in html
    assert "Bị cổng an toàn chặn" in html
    assert "Hướng MUA" in html or "Hướng BÁN" in html


def test_scores_html_lists_component_scores() -> None:
    screen = _stub_screen(_blocked_row())
    html = screen._diag_scores_html(light=True)
    assert html, "Chẩn đoán must render component scores (non-empty)"
    for label in (
        "Tín hiệu kỹ thuật",
        "Điểm thiết lập (Setup)",
        "Bằng chứng (Evidence)",
        "Chất lượng thực thi",
    ):
        assert label in html, f"missing component label {label!r}"
    assert "MUA" in html and "BÁN" in html


def test_gates_html_lists_all_gate_groups() -> None:
    screen = _stub_screen(_blocked_row())
    html = screen._diag_gates_html(light=True)
    assert html, "Chẩn đoán must render gate blocks (non-empty)"
    for label in (
        "An toàn thị trường",
        "Vĩ mô",
        "Kịch bản (R:R)",
        "Tài khoản",
        "Danh mục",
        "Nhật ký",
    ):
        assert label in html, f"missing gate group {label!r}"
    # The fail-closed spread threshold code must appear (translated, not raw).
    assert "ngưỡng spread" in html


def test_plan_html_shows_entry_sl_tp_and_status() -> None:
    screen = _stub_screen(_blocked_row())
    html = screen._diag_plan_html(light=True)
    assert html
    for label in ("Điểm vào lệnh (entry)", "Dừng lỗ (stop-loss)", "Chốt lời (take-profit)"):
        assert label in html, f"missing plan field {label!r}"


def test_refresh_diagnostics_dispatches_to_builders() -> None:
    """For a row, the Chẩn đoán render uses the native builders (non-empty)."""
    captured: list[str] = []

    def _fake_set_rich_html(widget, html, **kwargs):
        captured.append(html)

    original = mod.set_rich_html
    mod.set_rich_html = _fake_set_rich_html
    try:
        screen = _stub_screen(_blocked_row())
        screen.diag_text = object()
        screen._refresh_diagnostics()
    finally:
        mod.set_rich_html = original

    assert captured, "Chẩn đoán must emit HTML for a row"
    html = captured[0]
    assert "Scanner — Hướng" in html
    assert "Phân rã điểm số" in html
    assert "Cổng chặn" in html