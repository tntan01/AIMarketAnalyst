"""Detail-screen Chẩn đoán tab contract for Scanner rows (17/08/2026).

Scanner rows (``pipeline_route == "scanner"``) carry their scores,
statuses and reason codes directly on the UI row — NOT inside the legacy
``analysis_result`` (which holds ``scenario_scores`` / ``pipeline_diagnostics``
that the rows never emit).  Regression: the Chẩn đoán tab previously rendered
only the legacy builders, so it came out empty for these rows.
``_refresh_diagnostics`` now dispatches to native builders; here we assert they
render the route, plan, gate groups, SMC verdict and Location detail from the
real row — and that the trimmed blocks (score breakdown, B/Q/L/C table, Location
raw/contribution, aggregate block codes) are gone.

These tests drive the builders on a real ``_analyze_one_symbol`` row through
a minimal (non-QWebEngineView) screen stub, because constructing a full
``ScannerDetailScreen`` instantiates a chart view that segfaults headless.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
import ui.screens.scanner_detail_screen as mod
from controllers.scanner_controller import _analyze_one_symbol
from core.scanner_live_producers import build_live_market_safety_context
from core.scanner_order_policy import load_runtime_order_policy
from ui.screens.scanner_detail_screen import ScannerDetailScreen

from tests.test_scanner_release import _zoned_candles

# Task 101: the snapshot seam reads the symbol metadata from the packet, and
# the cutoff must come from the DATA, never from the wall clock.  The fixture
# quotes ~1000 with 0.2 wicks, so one broker tick is 0.01.
_TICK_SIZE = 0.01

# Task 137: this fixture is observed at a FIXED instant, and the row is composed
# against that same instant.  ``_zoned_candles`` places its candles on the
# timeframe grid (the anchor is a whole hour and every timeframe is a whole
# number of hours) while ``datetime.now()`` carries a sub-hour remainder, so a
# wall-clock placement moved every candle off its boundary.  The canonical
# verdict is grid-sensitive: the same input returned ``evaluated``,
# ``watch_zone`` and ``data_unavailable`` within seconds of each other and a side
# could lose its zone id between two runs of one test.  Pinning the instant — and
# the clock the composition compares it to — keeps the row a real
# ``_analyze_one_symbol`` row AND repayable; it is the same fixed-observation
# pattern ``tests/test_scanner_execution_controller.py`` already uses for the
# dispatch path.  ``datetime.now()`` is deliberately not read here: a fixture
# whose verdict depends on when it runs cannot be a regression test.
_OBSERVED_AT = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)


def _place_at_observation(candles, shift):
    """Shift a fixed-date fixture onto the observation instant.

    The scanner compares the snapshot boundary against the real clock, so the
    candle data has to sit where the observation happens.  The shift is applied
    to the DATA; every timestamp below is then derived from the candles.
    """

    return [
        replace(candle, time=candle.time + shift) for candle in candles
    ]


def _blocked_row() -> dict:
    """Produce a real BLOCKED row via the live controller path.

    The row is placed at — and composed against — the fixed ``_OBSERVED_AT``
    instant, so the same call always produces the same row.
    """
    from tests.test_scanner_release import NOW as _FIXTURE_ANCHOR

    d1, h4, h1 = _zoned_candles()
    m15 = h1[-40:]
    # Place the fixture at the observation instant, then DERIVE the boundary
    # from the data (never from a second clock read).
    shift = _OBSERVED_AT - _FIXTURE_ANCHOR
    d1 = _place_at_observation(d1, shift)
    h4 = _place_at_observation(h4, shift)
    h1 = _place_at_observation(h1, shift)
    m15 = _place_at_observation(m15, shift)
    # The boundary is the close of the newest candle in the fixture: with the
    # placement shift above it lands on the observation instant, and it is
    # still read from the DATA rather than from a second clock call.
    live_now = max(candle.time for candle in h1) + timedelta(hours=1)
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
        "data_quality": {
            "tick_size": _TICK_SIZE,
            "tick_size_source": "trade_tick_size",
        },
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
        now=_OBSERVED_AT,
    )


@pytest.fixture(autouse=True)
def _qt_application():
    """The renderers embed Qt icons (``ui.icons.flat_data_uri``).

    Building a QPixmap/QBuffer without a live QApplication is undefined
    behaviour and kills the process headless, so the suite provides the same
    offscreen application the real UI has.
    """

    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


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


def test_location_html_renders_h1_reference_anchor_and_obstacle() -> None:
    from tests.test_location_canonical_detail import _location_detail

    detail = _location_detail("buy", 13).to_dict()
    row = {
        "pipeline_route": "scanner",
        "scanner_candidate_decision": {
            "selected_side": "buy",
            "status": "WATCH_ZONE",
        },
        "side_scores": [
            {
                "side": "buy",
                "location_raw": 13,
                "technical_breakdown": {
                    "location": {"raw": 13, "raw_max": 25, "contribution": 20.8},
                },
                "location_detail": detail,
            }
        ],
    }

    html = _stub_screen(row)._diag_location_html(light=True)
    assert "Location" in html
    for label in (
        "Giá tham chiếu H1",
        "Anchor",
        "Khoảng cách anchor",
        "Obstacle phía trước",
        "Khoảng trống obstacle",
    ):
        assert label in html, f"missing Location field {label!r}"
    assert "reference_closed_at" not in html
    # The raw/contribution summary and the version row were cut from the tab.
    for dropped in ("Raw", "Đóng góp kỹ thuật", "/25", "Model/config"):
        assert dropped not in html, f"cut Location content {dropped!r} still rendered"


def test_location_html_without_detail_says_so() -> None:
    row = {
        "pipeline_route": "scanner",
        "scanner_candidate_decision": {"selected_side": "buy"},
        "side_scores": [{"side": "buy", "location_raw": 0}],
    }

    html = _stub_screen(row)._diag_location_html(light=True)
    assert "Location" in html
    assert "Bản lưu cũ chưa có chi tiết Location" in html
    assert "Raw" not in html and "Đóng góp kỹ thuật" not in html


@pytest.mark.parametrize("light", [True, False])
@pytest.mark.parametrize("viewport_width", [320, 1280])
def test_location_html_fixture_is_responsive_for_long_values(light, viewport_width) -> None:
    """G03 fixture: both themes and supported widths keep critical Location text."""
    from tests.test_location_canonical_detail import _location_detail

    detail = _location_detail("buy", 13).to_dict()
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
    assert "1234567890.12" in html
    assert "Chưa quan sát được trong dữ liệu đã xét" in html
    assert "Giá tham chiếu H1" in html
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
    for text in ("Location", "Giá tham chiếu H1", "Anchor"):
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
    # The aggregate block-code line was cut: every code is already listed above.
    assert "Mã chặn tổng hợp" not in html


def test_plan_html_shows_entry_sl_tp_and_status() -> None:
    screen = _stub_screen(_blocked_row())
    html = screen._diag_plan_html(light=True)
    assert html
    for label in ("Điểm vào lệnh (entry)", "Dừng lỗ (stop-loss)", "Chốt lời (take-profit)"):
        assert label in html, f"missing plan field {label!r}"


def test_refresh_diagnostics_renders_the_trimmed_blocks_in_order() -> None:
    """Route → plan → gates → SMC → Location, with the cut content absent."""
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
    markers = [
        "Scanner — Hướng",
        "Kế hoạch &amp; quyết định",
        "Cổng chặn",
        'rt-location-title">SMC<',
        'rt-location-title">Location<',
    ]
    positions = []
    for marker in markers:
        assert marker in html, f"missing block {marker!r}"
        positions.append(html.index(marker))
    assert positions == sorted(positions), f"blocks out of order: {positions}"

    for dropped in (
        "Phân rã điểm số",
        "Thành phần SMC",
        "Mã chặn tổng hợp",
        "Đóng góp kỹ thuật",
        "Model/config",
    ):
        assert dropped not in html, f"cut content {dropped!r} still rendered"
