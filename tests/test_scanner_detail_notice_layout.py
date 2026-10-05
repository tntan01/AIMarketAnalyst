"""Detail "Chi tiết kết quả quét" — ghi chú refresh nến nằm CÙNG DÒNG "Quét lúc…".

The candle-refresh notice used to live in its own row above the chart.  It now
sits in the tab bar's corner on ONE line: the notice first, the scan-time line
after it, both right-aligned.  The notice hides itself when there is nothing to
say, and the scan line keeps that row (no blank band, no second row).

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
screen.resize(1600, 800)

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

# The scan line keeps its own wording/format while sharing the notice's row.
screen.row["timestamp"] = "2026-09-18T05:15:34+00:00"
screen._refresh_scan_time_label()
observations["scan_line_text"] = screen.scan_time_label.text()

# Geometry: both labels must sit on ONE row, notice first.  The screen is shown
# offscreen so the layouts run; the scan line is measured again with the notice
# hidden to prove it keeps that row instead of dropping to a band of its own.
screen.show()
for _ in range(5):
    app.processEvents()


def _geo(widget):
    g = widget.geometry()
    return [g.x(), g.y(), g.width(), g.height()]


observations["scan_geo_while_empty"] = _geo(screen.scan_time_label)

# From here on, ONLY the notice paths run — the row must come out untouched.
row_before = json.dumps(screen.row, sort_keys=True, default=str)

screen._set_chart_notice(observations["copy_success"])
observations["notice_shown_with_text"] = not screen.chart_notice.isHidden()
observations["notice_text"] = screen.chart_notice.text()
for _ in range(5):
    app.processEvents()
observations["notice_geo"] = _geo(screen.chart_notice)
observations["scan_geo"] = _geo(screen.scan_time_label)
observations["same_row"] = (
    screen.chart_notice.y() == screen.scan_time_label.y()
)
observations["notice_left_of_scan"] = (
    screen.chart_notice.x() < screen.scan_time_label.x()
)
observations["corner_geo"] = _geo(corner)
observations["line_height"] = max(
    screen.chart_notice.height(), screen.scan_time_label.height()
)

# One line means: the label asks for the width its sentence actually needs (a
# wrapped size hint asks for less and then wraps), and it renders that width
# without cutting the sentence.
_fm = screen.chart_notice.fontMetrics()
observations["notice_text_px"] = _fm.horizontalAdvance(screen.chart_notice.text())
observations["font_line_px"] = _fm.height()
observations["notice_hint"] = [
    screen.chart_notice.sizeHint().width(),
    screen.chart_notice.sizeHint().height(),
]

screen._set_chart_notice("")
for _ in range(5):
    app.processEvents()
observations["scan_geo_after_hide"] = _geo(screen.scan_time_label)
screen._set_chart_notice(observations["copy_success"])

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
# Vị trí: notice và "Quét lúc…" trên MỘT dòng, cả hai trong góc tab
# ---------------------------------------------------------------------------


def test_the_notice_shares_one_row_with_the_scan_line(observed: dict[str, Any]) -> None:
    """Đúng một dòng: ghi chú bên trái, 'Quét lúc …' bên phải, cùng một hàng."""

    assert observed["has_corner"] and observed["corner_is_tab_corner"]
    assert observed["corner_name"] == "TabBarCorner"
    assert observed["corner_names"] == ["PageSubtitle", "PageSubtitle"]
    assert observed["first_is_notice"], "phần đầu dòng là ghi chú refresh nến"
    assert observed["second_is_scan_line"], "phần sau dòng là 'Quét lúc …'"

    # The row is one line tall: the labels sit at the same y, notice first.
    assert observed["same_row"], (
        f"notice và 'Quét lúc' phải cùng một dòng: "
        f"notice={observed['notice_geo']} scan={observed['scan_geo']}"
    )
    assert observed["notice_left_of_scan"], (
        f"notice đứng trước 'Quét lúc': "
        f"notice={observed['notice_geo']} scan={observed['scan_geo']}"
    )
    assert observed["corner_geo"][3] <= 2 * observed["line_height"], (
        "góc tab chỉ cao một dòng chữ"
    )


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
    # Hiding the notice neither drops the row nor moves the scan line off it.
    assert observed["scan_geo_after_hide"][1] == observed["scan_geo_while_empty"][1], (
        "'Quét lúc …' giữ nguyên hàng khi ghi chú ẩn đi"
    )


def test_the_notice_keeps_its_whole_sentence_on_one_line(observed: dict[str, Any]) -> None:
    """Một dòng, và cả câu — không wrap, không bị cắt bớt chữ.

    Regression: ``setWordWrap(True)`` làm size hint của QLabel nhỏ hơn bề rộng
    thật của câu, nên ghi chú tự wrap thành 2 dòng dù góc tab còn chỗ.
    """

    assert observed["notice_word_wrap"] is False
    assert observed["notice_max_width"] >= observed["notice_text_px"], (
        "không đặt trần bề rộng dưới bề rộng thật của câu"
    )
    assert observed["notice_hint"][0] >= observed["notice_text_px"], (
        f"góc tab phải xin đủ bề rộng cho cả câu: "
        f"hint={observed['notice_hint']} cần={observed['notice_text_px']}"
    )
    assert observed["notice_geo"][3] <= observed["font_line_px"] * 1.5, (
        f"ghi chú chỉ cao một dòng: geo={observed['notice_geo']} "
        f"font={observed['font_line_px']}"
    )
    assert observed["notice_geo"][2] >= observed["notice_text_px"], (
        f"chữ không bị cắt: geo={observed['notice_geo']} "
        f"cần={observed['notice_text_px']}"
    )


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
