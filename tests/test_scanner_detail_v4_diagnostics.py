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

from datetime import datetime, timezone

import pytest
import ui.screens.scanner_detail_screen as mod
from controllers.scanner_controller import _analyze_one_symbol
from core.scanner_live_producers import build_live_market_safety_context
from core.scanner_order_policy import load_runtime_order_policy
from ui.screens.scanner_detail_screen import ScannerDetailScreen

from tests.test_scanner_release import _zoned_candles


def _blocked_row() -> dict:
    """Produce a real BLOCKED row via the live controller path."""
    d1, h4, h1 = _zoned_candles()
    m15 = h1[-40:]
    live_now = datetime.now(timezone.utc)
    safety = build_live_market_safety_context(
        "XAU/USD", live_now,
        terminal_connected=True, broker_logged_in=True,
        connectivity_checked_at=live_now, last_candle_time_utc=live_now,
        data_checked_at=live_now, last_tick_time_utc=live_now,
        spread_points=500.0, spread_checked_at=live_now,
        news_source_verified=True, news_checked_at=live_now,
        volatility_ratio=1.0, volatility_checked_at=live_now,
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
        "v4_captured_at": live_now,
        "location_cutoff": live_now,
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
        order_policy=load_runtime_order_policy(),
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


def test_scores_html_selected_marker_is_flat_icon() -> None:
    """Marker hướng chọn phải là icon phẳng data-URI, không còn emoji ✅."""
    screen = _stub_screen(_blocked_row())
    html = screen._diag_scores_html(light=True)
    assert "✅" not in html
    assert "đang chọn" in html
    assert "data:image/png;base64" in html


def test_scores_html_marker_follows_theme() -> None:
    """Data-URI icon build theo palette hiện hành — đổi theme phải đổi URI."""
    import sys

    from PyQt6.QtWidgets import QApplication

    from ui.theme_manager import APP_THEME_PROPERTY, current_palette

    app = QApplication.instance() or QApplication(sys.argv)
    start = "light" if current_palette().name == "light" else "dark"
    target = "dark" if start == "light" else "light"
    screen = _stub_screen(_blocked_row())
    before = screen._diag_scores_html(light=True)
    app.setProperty(APP_THEME_PROPERTY, target)
    try:
        after = screen._diag_scores_html(light=True)
    finally:
        app.setProperty(APP_THEME_PROPERTY, start)
    assert before != after, "data-URI icon không đổi theo theme"


@pytest.mark.parametrize("raw", [0, 13, None])
def test_location_html_renders_raw_states_and_h1_reference(raw) -> None:
    from tests.test_location_canonical_detail import _location_detail

    detail = _location_detail("buy", raw).to_dict() if raw is not None else None
    location_component = {
        "raw": raw,
        "raw_max": 25,
        "weight": 40,
        "contribution": None if raw is None else raw * 40 / 25,
    }
    row = {
        "pipeline_route": "scanner",
        "scanner_candidate_decision": {
            "selected_side": "buy",
            "status": "WATCH_ZONE",
        },
        "side_scores": [
            {
                "side": "buy",
                "location_raw": raw,
                "technical_breakdown": {"location": location_component},
                **({"location_detail": detail} if detail is not None else {}),
            }
        ],
    }

    html = _stub_screen(row)._diag_location_html(light=True)
    assert "Location" in html
    assert (f"{raw}/25" in html if raw is not None else "Không đủ dữ liệu" in html)
    if detail is None:
        assert "Bản lưu cũ chưa có chi tiết Location" in html
    else:
        assert "Giá tham chiếu H1" in html
        assert "reference_closed_at" not in html
        assert "Chưa quan sát được trong dữ liệu đã xét" in html


@pytest.mark.parametrize("light", [True, False])
@pytest.mark.parametrize("viewport_width", [320, 1280])
def test_location_html_fixture_is_responsive_for_long_values(light, viewport_width) -> None:
    """G03 fixture: both themes and supported widths keep critical Location text."""
    from tests.test_location_canonical_detail import _location_detail

    detail = _location_detail("buy", 13).to_dict()
    detail["reason_codes"] = [
        "LOCATION_LIMITED_CONTEXT",
        "LONG_REASON_CODE_FOR_RESPONSIVE_LOCATION_CARD_REGRESSION",
    ]
    detail["reference_price"] = 1234567890.123456
    detail["reference_closed_at"] = "2026-09-10T12:34:56.123456+00:00"
    detail["obstacle"] = None
    row = {
        "scanner_candidate_decision": {"selected_side": "buy"},
        "side_scores": [
            {
                "side": "buy",
                "technical_breakdown": {
                    "location": {"raw": 13, "contribution": 20.8},
                },
                "location_detail": detail,
            },
        ],
    }

    html = _stub_screen(row)._diag_location_html(light=light)
    from ui.rich_text import compile_rich_html
    html = compile_rich_html(html, theme="light" if light else "dark")

    # The render path uses a responsive table rather than a fixed-width card.
    assert f"width:100%" in html
    assert "table-layout:fixed" in html
    assert "overflow-wrap:anywhere" in html
    assert "LONG_REASON_CODE_FOR_RESPONSIVE_LOCATION_CARD_REGRESSION" in html
    assert "1234567890.12" in html
    assert "Chưa quan sát được trong dữ liệu đã xét" in html
    assert "Raw" in html and "Giá tham chiếu H1" in html
    assert "min-width" not in html
    assert viewport_width in (320, 1280)  # document the narrow/wide fixture matrix


def test_location_html_fixture_theme_changes_palette_not_content() -> None:
    from tests.test_location_canonical_detail import _location_detail

    detail = _location_detail("buy", 0).to_dict()
    row = {
        "scanner_candidate_decision": {"selected_side": "buy"},
        "side_scores": [
            {
                "side": "buy",
                "technical_breakdown": {
                    "location": {"raw": 0, "contribution": 0.0},
                },
                "location_detail": detail,
            },
        ],
    }
    screen = _stub_screen(row)
    light_html = screen._diag_location_html(light=True)
    dark_html = screen._diag_location_html(light=False)

    assert light_html != dark_html
    for text in ("Location", "0/25", "Giá tham chiếu H1", "Anchor"):
        assert text in light_html and text in dark_html


def test_location_html_preserves_fx_price_precision() -> None:
    from tests.test_location_canonical_detail import _location_detail

    detail = _location_detail("buy", 13).to_dict()
    detail["reference_price"] = 1.142465
    detail["anchor"]["low"] = 1.14211
    detail["anchor"]["high"] = 1.14267
    row = {
        "symbol": "EUR/USD",
        "scanner_candidate_decision": {"selected_side": "buy"},
        "side_scores": [
            {
                "side": "buy",
                "technical_breakdown": {
                    "location": {"raw": 13, "contribution": 20.8},
                },
                "location_detail": detail,
            },
        ],
    }

    html = _stub_screen(row)._diag_location_html(light=True)
    assert "1.14247" in html
    assert "[1.14211, 1.14267]" in html
    assert "[1.14, 1.14]" not in html


def test_location_card_renders_without_horizontal_overflow_at_supported_widths() -> None:
    from PyQt6.QtWidgets import QApplication, QTextEdit
    from ui.rich_text import set_rich_html
    from ui.theme_manager import APP_THEME_PROPERTY
    from tests.test_location_canonical_detail import _location_detail

    app = QApplication.instance() or QApplication([])
    detail = _location_detail("buy", 13).to_dict()
    detail["reference_price"] = 1.142465
    detail["anchor"]["low"] = 1.14211
    detail["anchor"]["high"] = 1.14267
    detail["reason_codes"] = [
        "LOCATION_LIMITED_CONTEXT",
        "LONG_REASON_CODE_FOR_LOCATION_CARD_RENDER_REGRESSION",
    ]
    row = {
        "symbol": "EUR/USD",
        "scanner_candidate_decision": {"selected_side": "buy"},
        "side_scores": [
            {
                "side": "buy",
                "technical_breakdown": {
                    "location": {"raw": 13, "contribution": 20.8},
                },
                "location_detail": detail,
            },
        ],
    }
    screen = _stub_screen(row)
    original_theme = app.property(APP_THEME_PROPERTY)
    try:
        for theme in ("light", "dark"):
            app.setProperty(APP_THEME_PROPERTY, theme)
            for width in (320, 1280):
                edit = QTextEdit()
                edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
                edit.resize(width, 720)
                edit.show()
                set_rich_html(
                    edit,
                    screen._diag_location_html(light=theme == "light"),
                )
                app.processEvents()
                assert edit.horizontalScrollBar().maximum() == 0
                plain = edit.toPlainText()
                assert "1.14247" in plain
                assert "1.14211" in plain and "1.14267" in plain
                assert "LONG_REASON_CODE_FOR_LOCATION_CARD_RENDER_REGRESSION" in plain
                edit.close()
    finally:
        app.setProperty(APP_THEME_PROPERTY, original_theme)


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
    # The configured spread gate must appear (translated, not raw).
    assert "Chênh lệch giá (spread) bất thường" in html
    # Icon trạng thái phải là icon phẳng data-URI, không còn emoji chấm tròn.
    for emoji in ("🟢", "🔴", "🟡", "⚪"):
        assert emoji not in html, f"gate section còn emoji {emoji!r}"
    assert "data:image/png;base64" in html
    assert "Chặn" in html, "row BLOCKED phải giữ label trạng thái 'Chặn'"


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
