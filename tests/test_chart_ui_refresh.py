"""Lô UI Chart — nến nhỏ hơn một nửa + refresh nến mỗi 30 giây.

Two user-facing changes, and the tests that pin them:

* **Chart density** — ``assets/chart/index.html`` shows 200 candles instead of
  100 at half the bar spacing (3 → 1.5).  Only the time axis is configured; the
  price scale, the OHLC data, manual zoom/pan, Entry/SL/TP and the SMC layer
  (including the H1 execution view) are untouched.
* **Candle refresh cadence** — the Detail chart still refreshes as soon as it
  opens, and then once every ``CANDLE_REFRESH_INTERVAL_SECONDS`` (30) instead of
  every 5 seconds.  A refresh merges newer candles into the CHART only: the row,
  its plan, its ``price_vs_zone`` reading and its snapshot are never re-scored,
  re-selected or rewritten.  A fetch that has not finished is never joined by a
  second MT5 worker.

No test here waits the real 30 seconds: the countdown is driven tick by tick, and
no MT5 connection, thread or QApplication is ever created.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from ui.screens.scanner_detail_screen import (
    CANDLE_REFRESH_INTERVAL_SECONDS,
    ScannerDetailScreen,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CHART_HTML = _PROJECT_ROOT / "assets" / "chart" / "index.html"
_DETAIL_MODULE = Path(ScannerDetailScreen.__module__.replace(".", "/") + ".py")
_DETAIL_SOURCE = (_PROJECT_ROOT / _DETAIL_MODULE).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Helpers — the screen is never constructed (a full Detail screen needs a Qt
# event loop and a WebEngine view; the checklist tests use the same "__new__"
# pattern for exactly this reason).
# ---------------------------------------------------------------------------


def _analysis_result() -> dict[str, Any]:
    """A minimal stored analysis document with H1 candles to refresh."""

    return {
        "symbol": "AUD/NZD",
        "chart_payload": {
            "H1": [
                {"t": "2026-09-18T04:00:00+00:00", "o": 1.2, "h": 1.3, "l": 1.1, "c": 1.25},
                {"t": "2026-09-18T05:00:00+00:00", "o": 1.25, "h": 1.35, "l": 1.2, "c": 1.3},
            ]
        },
    }


def _screen(*, fetch_active: bool = False) -> ScannerDetailScreen:
    """A Detail screen standing at the timer's decision points, nothing else."""

    screen = ScannerDetailScreen.__new__(ScannerDetailScreen)
    screen.row = {"symbol": "AUD/NZD", "analysis_result": _analysis_result()}
    screen._candle_fetch_active = fetch_active
    screen._countdown_seconds = CANDLE_REFRESH_INTERVAL_SECONDS
    screen._hero_base_text = ""
    # The hero bar belongs to the (never built) Qt subtree; a plain ``None``
    # attribute makes ``_refresh_hero_countdown`` return before it touches any
    # C++ object, so the tick can be driven without a QApplication.
    screen.hero_bar = None
    return screen


class _RecordingMT5:
    """An MT5 stand-in that records every call instead of talking to a broker."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def connection_status(self) -> Any:
        self.calls.append("connection_status")
        return SimpleNamespace(connected=True, logged_in=True)

    def available_symbols(self, market_watch_only: bool = True) -> list[str]:
        self.calls.append("available_symbols")
        return []

    def resolve_symbol(self, symbol: str, available: Any) -> None:
        self.calls.append("resolve_symbol")
        return None

    def load_ohlcv(self, broker: str, timeframe: str, bars: int, skip_select: bool = False):
        self.calls.append("load_ohlcv")
        return []


# ---------------------------------------------------------------------------
# 1 — the refresh cadence
# ---------------------------------------------------------------------------


def test_the_interval_is_a_named_thirty_second_constant() -> None:
    assert CANDLE_REFRESH_INTERVAL_SECONDS == 30

    # The tick is still one second, and the scan-time label keeps its own 60s
    # timer — the two cadences are independent.
    assert "self._auto_refresh_timer.setInterval(1000)" in _DETAIL_SOURCE
    assert "self._scan_timer.setInterval(60000)" in _DETAIL_SOURCE
    # No 5-second literal may survive as a countdown value.
    assert "self._countdown_seconds = 5" not in _DETAIL_SOURCE
    assert _DETAIL_SOURCE.count("self._countdown_seconds = CANDLE_REFRESH_INTERVAL_SECONDS") == 3


def test_twenty_nine_ticks_do_not_refresh_and_tick_thirty_refreshes_once() -> None:
    screen = _screen()
    screen._provider_ready = lambda: True
    started: list[str] = []
    screen._start_candle_refresh_symbol = lambda symbol, result: started.append(symbol)

    for _ in range(CANDLE_REFRESH_INTERVAL_SECONDS - 1):
        screen._auto_refresh_tick()

    assert started == [], "29 giây đầu chưa được fetch lượt nào"
    assert screen._countdown_seconds == 1

    screen._auto_refresh_tick()

    assert started == ["AUD/NZD"], "giây thứ 30 fetch đúng một lần"
    assert screen._countdown_seconds == CANDLE_REFRESH_INTERVAL_SECONDS, "đếm lại từ 30"

    # And the cadence repeats: the next refresh is another 30 ticks away.
    for _ in range(CANDLE_REFRESH_INTERVAL_SECONDS):
        screen._auto_refresh_tick()
    assert started == ["AUD/NZD", "AUD/NZD"]


def test_a_disconnected_provider_never_advances_the_countdown() -> None:
    """No connection ⇒ no candle fetch and no countdown burn-through."""

    screen = _screen()
    screen._provider_ready = lambda: False
    started: list[str] = []
    screen._start_candle_refresh_symbol = lambda symbol, result: started.append(symbol)

    for _ in range(CANDLE_REFRESH_INTERVAL_SECONDS * 2):
        screen._auto_refresh_tick()

    assert started == []
    assert screen._countdown_seconds == CANDLE_REFRESH_INTERVAL_SECONDS


def test_a_fetch_in_flight_never_starts_a_second_worker() -> None:
    screen = _screen(fetch_active=True)
    screen._provider_ready = lambda: True
    started: list[str] = []
    screen._start_candle_refresh_symbol = lambda symbol, result: started.append(symbol)

    for _ in range(CANDLE_REFRESH_INTERVAL_SECONDS * 3):
        screen._auto_refresh_tick()

    assert started == [], "lượt fetch đang chạy thì không tạo lượt song song"

    # The guard holds at the ONE place a worker is created, not only in the tick:
    # calling the fetch directly while one is active must create nothing and must
    # not touch MT5 at all.
    mt5 = _RecordingMT5()
    screen.app = SimpleNamespace(mt5=mt5)
    screen._start_candle_refresh_symbol("AUD/NZD", _analysis_result())

    assert "_candle_worker" not in screen.__dict__, "không tạo worker MT5 thứ hai"
    assert mt5.calls == [], "MT5 không được gọi khi lượt trước chưa xong"


def test_the_worker_guard_is_the_first_thing_the_fetch_does() -> None:
    """Structural pin: the ``_candle_fetch_active`` guard precedes everything."""

    tree = ast.parse(_DETAIL_SOURCE)
    fn = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_start_candle_refresh_symbol"
    )
    body = [
        node
        for node in fn.body
        if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant))
    ]
    first = body[0]
    assert isinstance(first, ast.If), ast.dump(first)[:120]
    assert isinstance(first.test, ast.Attribute) and first.test.attr == "_candle_fetch_active"
    assert isinstance(first.body[0], ast.Return)


# ---------------------------------------------------------------------------
# 2 — opening the Detail still refreshes, and a refresh never rewrites the plan
# ---------------------------------------------------------------------------


def test_opening_the_detail_still_refreshes_the_candles_once() -> None:
    screen = _screen()
    screen._set_chart_notice = lambda text: None
    screen._is_light_theme = lambda: True
    painted: list[dict[str, Any]] = []
    screen.chart = SimpleNamespace(
        _active_tf="H1",
        set_payload=lambda payload: painted.append(payload),
        show_empty=lambda: None,
        show_error=lambda text: None,
    )
    started: list[tuple[str, dict[str, Any]]] = []
    screen._start_candle_refresh_symbol = lambda symbol, result: started.append((symbol, result))

    before = json.loads(json.dumps(screen.row, default=str))
    screen._refresh_chart()

    assert len(painted) == 1, "mở Detail là vẽ chart ngay"
    assert started and started[0][0] == "AUD/NZD", "và fetch nến ngay lần đầu"
    assert json.loads(json.dumps(screen.row, default=str)) == before, (
        "refresh không đổi row: không re-score, không đổi price_vs_zone/Entry/SL/TP/snapshot"
    )


# ---------------------------------------------------------------------------
# 3 — the chart density lock
# ---------------------------------------------------------------------------


def _default_time_scale_body() -> str:
    source = _CHART_HTML.read_text(encoding="utf-8")
    start = source.index("function _applyDefaultTimeScale")
    end = source.index("\n    }", start)
    return source[start:end]


def test_the_chart_shows_two_hundred_bars_at_half_the_bar_spacing() -> None:
    body = _default_time_scale_body()

    assert "var visibleBars = 200;" in body
    assert "barSpacing: 1.5," in body
    assert "minBarSpacing: 1.5," in body
    assert "barSpacing: 3" not in body, "mật độ cũ (3) không còn"
    assert "var visibleBars = 100;" not in body


def test_the_density_change_leaves_the_price_scale_alone() -> None:
    """Only the time axis is configured — the vertical scale must not be squashed."""

    body = _default_time_scale_body()

    assert "priceScale" not in body
    assert "scaleMargins" not in body
    assert "autoScale" not in body


def test_the_chart_page_still_has_its_ohlc_and_overlay_surfaces() -> None:
    """The density edit is local: the page keeps every surface it had."""

    source = _CHART_HTML.read_text(encoding="utf-8")

    for marker in (
        "function _isExecutionView",
        "function _renderSmcOverlay",
        "function _renderEntryZone",
        "setChartData",
        "switchTimeframe",
    ):
        assert marker in source, marker


def test_a_theme_switch_never_resets_the_density() -> None:
    """Light/dark re-paint the chrome — they must not undo the smaller candles."""

    source = _CHART_HTML.read_text(encoding="utf-8")
    start = source.index("function applyChartTheme")
    end = source.index("\n    }", start)
    body = source[start:end]

    assert "barSpacing" not in body
    assert "minBarSpacing" not in body
    assert source.count("barSpacing: 1.5") == 1, "one density setting only"
    assert source.count("minBarSpacing: 1.5") == 1
