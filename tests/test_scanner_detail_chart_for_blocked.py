"""Detail-screen data contract for BLOCKED candidates (17/08/2026).

The detail screen must render the chart + trade parameters for EVERY scanned
candidate, blocked or not — only the status annotation (hero / score panels)
differs.  Regression: ``_analyze_one_symbol`` previously returned an
``analysis_result`` with no ``chart_payload``, so the detail chart was empty and
the background candle-refresh aborted even though the real candles were already
prefetched.  Here we assert the controller injects the real candles into
``analysis_result`` regardless of ``candidate_status`` and that the trade
parameters (entry / stop_loss / take_profit) survive a safety BLOCK.
"""

from __future__ import annotations

from controllers.scanner_controller import _analyze_one_symbol
from core.chart_payload import build_full_chart_payload
from core.scanner_v4_live_producers import build_live_market_safety_context

from tests.test_scanner_v4_release import NOW, _zoned_candles


def _blocked_pkt() -> dict:
    """A fully-fresh safety context whose ONLY safety failure is spread ABNORMAL.

    spread_points (260) > XAU threshold (40) makes the safety gate BLOCK while
    connectivity / data freshness / volatility all PASS — so the row is a
    genuine BLOCKED candidate carrying real structure + plan.
    """
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
    return {
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


def _analyzed() -> dict:
    pkt = _blocked_pkt()
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


def test_blocked_candidate_is_actually_blocked() -> None:
    row = _analyzed()
    assert row["candidate_status"] == "BLOCKED"


def test_blocked_row_keeps_real_trade_parameters() -> None:
    row = _analyzed()
    # Entry/SL/TP come from the real scenario plan and survive the safety BLOCK.
    assert row["stop_loss"] > 0
    assert row["take_profit"] > row["entry_price"]
    assert row["selected_side"] in ("buy", "sell")


def test_analysis_result_carries_candles_for_the_chart() -> None:
    row = _analyzed()
    ar = row["analysis_result"]
    assert "chart_payload" in ar
    cp = ar["chart_payload"]
    # Real prefetched candles are present and JSON-safe dicts (chart-ready).
    for tf in ("D1", "H4", "H1", "M15"):
        assert tf in cp and cp[tf], f"expected candles for {tf}"
        assert isinstance(cp[tf][0], dict), f"{tf} rows must be dicts"


def test_chart_payload_builds_a_nonempty_chart_for_blocked() -> None:
    row = _analyzed()
    payload = build_full_chart_payload(
        row["symbol"], row["analysis_result"], active_timeframe="H1"
    )
    timeframes = payload.get("timeframes") or {}
    assert any(
        isinstance(v, dict) and v.get("candles")
        for v in timeframes.values()
    ), "detail chart must have at least one timeframe with candles"


def test_status_annotation_is_separate_from_chart_data() -> None:
    # The blocked annotation must not gate chart/params: candidate_status stays
    # BLOCKED while the same row still carries candles + plan parameters.
    row = _analyzed()
    assert row["candidate_status"] == "BLOCKED"
    assert (row.get("block_codes") or []), "blocked annotation present"
    assert row["analysis_result"]["chart_payload"]
    assert row["entry_price"] > 0