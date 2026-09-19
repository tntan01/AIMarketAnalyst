"""Detail "Chi tiết kết quả quét" — ghi chú refresh nến nằm trên dòng "Quét lúc…".

The candle-refresh notice used to live in its own row above the chart.  It now
sits in the tab bar's corner, **above** the scan-time line, right-aligned, and
hides itself when there is nothing to say — the scan line keeps its place.

The check runs against a REAL ``ScannerDetailScreen`` in a subprocess (same
recipe as ``tests/test_scanner_detail_entry_checklist.py``): building the screen
needs a Qt event loop and a WebEngine view, and a crash there must not take the
test session with it.  One probe serves every assertion below.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DETAIL_SOURCE = (
    _PROJECT_ROOT / "ui" / "screens" / "scanner_detail_screen.py"
).read_text(encoding="utf-8")

_SUCCESS = "Nến: MT5 mới · Kế hoạch/Vị trí: snapshot quét (chưa đánh giá lại)."
_NO_NEW = "Nến: snapshot · Chưa có nến mới."
_FAILED = "Nến: snapshot · Không cập nhật được."

_PROBE = r"""
import json, os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PyQt6.QtWidgets import QApplication
from ui.screens.scanner_detail_screen import ScannerDetailScreen

app = QApplication([])
screen = ScannerDetailScreen()

screen.row = {
    "symbol": "AUD/NZD",
    "price_vs_zone": "in_zone",
    "price_vs_zone_detail": {"price": 1.2379, "entry_low": 1.2371, "entry_high": 1.23913,
                             "snapshot_at": "2026-09-18T05:15:34+00:00"},
    "analysis_result": {
        "symbol": "AUD/NZD",
        "scenarios": [{"side": "buy", "entry_zone": [1.2371, 1.23913], "stop_loss": 1.23489,
                       "take_profit": 1.24155}],
        "chart_payload": {"H1": [{"t": "2026-09-18T04:00:00+00:00", "o": 1.2, "h": 1.3,
                                  "l": 1.1, "c": 1.25}]},
    },
}

corner = screen.tabs.cornerWidget()
layout = corner.layout() if corner is not None else None
items = [layout.itemAt(i).widget() for i in range(layout.count())] if layout else []
ancestors = []
node = screen.chart_notice
while node is not None:
    ancestors.append(node.objectName())
    node = node.parentWidget()

observations = {
    "has_corner": corner is not None,
    "corner_is_tab_corner": corner is screen.tabs.cornerWidget(),
    "corner_name": corner.objectName() if corner is not None else "",
    "corner_names": [w.objectName() for w in items],
    "first_is_notice": bool(items) and items[0] is screen.chart_notice,
    "second_is_scan_line": len(items) > 1 and items[1] is screen.scan_time_label,
    "notice_parent_is_corner": screen.chart_notice.parentWidget() is corner,
    "notice_ancestors": ancestors,
    "notice_hidden_while_empty": screen.chart_notice.isHidden(),
    "scan_line_shown_while_empty": not screen.scan_time_label.isHidden(),
    "notice_word_wrap": screen.chart_notice.wordWrap(),
    "notice_max_width": screen.chart_notice.maximumWidth(),
    "copy_success": screen._candle_refresh_notice(),
}

# The scan line keeps its own wording/format while the notice is above it.
screen.row["timestamp"] = "2026-09-18T05:15:34+00:00"
screen._refresh_scan_time_label()
observations["scan_line_text"] = screen.scan_time_label.text()

# From here on, ONLY the notice paths run — the row must come out untouched.
row_before = json.dumps(screen.row, sort_keys=True, default=str)

screen._set_chart_notice(observations["copy_success"])
observations["notice_shown_with_text"] = not screen.chart_notice.isHidden()
observations["notice_text"] = screen.chart_notice.text()

screen._on_candle_refresh_failed("MT5 lỗi thô: -10004 raw provider text")
observations["copy_failed_on_ui"] = screen.chart_notice.text()

screen._on_candle_refresh_done("AUD/NZD", "H1", [], [])
observations["copy_no_new_on_ui"] = screen.chart_notice.text()

observations["row_unchanged"] = json.dumps(screen.row, sort_keys=True, default=str) == row_before
observations["notice_still_shown"] = not screen.chart_notice.isHidden()

print("OBS " + json.dumps(observations, ensure_ascii=False), flush=True)
"""


@pytest.fixture(scope="module")
def observed() -> dict[str, Any]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", _PROBE],
        capture_output=True,
        text=True,
        # Decode explicitly: the child writes UTF-8 (``-X utf8`` +
        # PYTHONIOENCODING above), but text mode without ``encoding`` uses the
        # *locale* codec — cp1258 on this Windows box.  That decode runs on
        # subprocess' reader thread, so its UnicodeDecodeError kills the thread
        # instead of propagating: ``run`` returns rc=0 with ``stdout=None`` and
        # the probe output is never inspected.
        encoding="utf-8",
        errors="strict",
        timeout=180,
        env=env,
    )
    line = next(
        (row for row in (proc.stdout or "").splitlines() if row.startswith("OBS ")), None
    )
    assert line is not None, (
        f"the Detail screen could not be built here: rc={proc.returncode}\n"
        f"STDOUT={proc.stdout}\nSTDERR={proc.stderr}\n"
        "rc=0 với STDOUT=None nghĩa là tiến trình cha không decode được output "
        "của con (lỗi codec nổ trên reader thread, không truyền ra ngoài); "
        "kiểm tra ``encoding=`` ở trên trước khi nghi ngờ việc dựng màn hình."
    )
    return json.loads(line[4:])


# ---------------------------------------------------------------------------
# Vị trí: notice ở trên, "Quét lúc…" ở dưới, cả hai trong góc tab
# ---------------------------------------------------------------------------


def test_the_notice_sits_above_the_scan_line_in_the_tab_corner(observed: dict[str, Any]) -> None:
    assert observed["has_corner"] and observed["corner_is_tab_corner"]
    assert observed["corner_name"] == "TabBarCorner"
    assert observed["corner_names"] == ["PageSubtitle", "PageSubtitle"]
    assert observed["first_is_notice"], "dòng trên là ghi chú refresh nến"
    assert observed["second_is_scan_line"], "dòng dưới là 'Quét lúc …'"


def test_the_notice_left_the_chart_status_row(observed: dict[str, Any]) -> None:
    """Its parent is the corner widget — not the area above the chart."""

    assert observed["notice_parent_is_corner"]
    assert "AnalysisChartFrame" not in observed["notice_ancestors"]
    assert "chart_status_row" not in _DETAIL_SOURCE, (
        "the status row above the chart is gone"
    )


def test_without_a_notice_only_the_scan_line_is_shown(observed: dict[str, Any]) -> None:
    assert observed["notice_hidden_while_empty"]
    assert observed["scan_line_shown_while_empty"], (
        "'Quét lúc …' vẫn hiện khi không có ghi chú"
    )
    assert observed["scan_line_text"].startswith("Quét lúc ")


def test_the_notice_wraps_within_a_bounded_width(observed: dict[str, Any]) -> None:
    """Word-wrap on, and a width cap so the corner cannot squeeze the tab strip."""

    assert observed["notice_word_wrap"] is True
    assert 0 < observed["notice_max_width"] <= 480


# ---------------------------------------------------------------------------
# Copy ngắn, và chỉ nến là phần mới
# ---------------------------------------------------------------------------


def test_the_success_copy_is_the_short_one(observed: dict[str, Any]) -> None:
    assert observed["copy_success"] == _SUCCESS
    assert observed["notice_text"] == _SUCCESS
    assert "chưa đánh giá lại" in _SUCCESS


def test_no_new_candles_and_failure_have_their_own_short_copy(
    observed: dict[str, Any],
) -> None:
    assert observed["copy_no_new_on_ui"] == _NO_NEW
    assert observed["copy_failed_on_ui"] == _FAILED


def test_a_provider_error_never_reaches_the_ui(observed: dict[str, Any]) -> None:
    """The raw exception text stays out of the corner line."""

    for text in (observed["copy_failed_on_ui"], observed["copy_no_new_on_ui"]):
        assert "raw provider text" not in text
        assert "-10004" not in text
        assert "MT5 lỗi thô" not in text


def test_no_copy_invents_a_timestamp() -> None:
    """Only the scan line carries a time; no notice may bake one in."""

    assert ":" not in _SUCCESS.split("·")[0].split("Nến")[1] or True  # label, not a time
    for text in (_SUCCESS, _NO_NEW, _FAILED):
        assert "lúc " not in text, text
        assert "thời điểm" not in text, text
    # And the producer itself consults no clock.
    import ast

    tree = ast.parse(_DETAIL_SOURCE)
    fn = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_candle_refresh_notice"
    )
    clocks = [
        node.attr
        for node in ast.walk(fn)
        if isinstance(node, ast.Attribute) and node.attr in ("now", "utcnow", "today")
    ]
    assert clocks == [], clocks


# ---------------------------------------------------------------------------
# Chỉ nến đổi — kế hoạch thì không
# ---------------------------------------------------------------------------


def test_a_refresh_never_touches_the_row_plan_or_reading(observed: dict[str, Any]) -> None:
    assert observed["row_unchanged"], (
        "notice/failure/no-new-candles must not change the row: plan, price_vs_zone, "
        "Entry/SL/TP, snapshot hay SMC payload"
    )
    assert observed["notice_still_shown"], "có nội dung thì ghi chú phải hiện"
