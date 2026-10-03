"""WI-6 — hint UI "Cần dán lịch ForexFactory" trên Scanner.

Cờ `MACRO_CALENDAR_STALE` là DISPLAY-ONLY: khi bất kỳ row nào mang cờ trong
`row["macro"]["freshness_reason_codes"]`, nhãn trạng thái quét hiện có
(`status_summary_label`) thêm ĐÚNG MỘT dòng nhắc; không có cờ thì không nhắc, và
mỗi lần cập nhật trạng thái là hint được tính lại theo scan mới (hint cũ bị xóa).
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from core.reason_codes import MACRO_CALENDAR_STALE  # noqa: E402
from tools.capture_ui_style_baseline import _fake_app  # noqa: E402
from ui.screens.scanner_screen import ScannerScreen  # noqa: E402

_QT_APP: QApplication | None = None

HINT_TEXT = "Cần dán lịch ForexFactory"


def _app() -> QApplication:
    """QApplication dùng chung (giữ tham chiếu cấp module — PyQt huỷ app non)."""
    global _QT_APP
    if _QT_APP is None:
        _QT_APP = QApplication.instance() or QApplication(sys.argv)
    return _QT_APP


def _screen() -> ScannerScreen:
    _app()
    return ScannerScreen(app=_fake_app("light"))


def _row(*, codes=None, with_macro: bool = True) -> dict:
    row: dict = {"symbol": "EUR/USD", "candidate_status": "BLOCKED"}
    if with_macro:
        macro: dict = {"macro_confidence": 0.4}
        if codes is not None:
            macro["freshness_reason_codes"] = codes
        row["macro"] = macro
    return row


class TestCalendarStaleHint:
    def test_hint_shown_when_any_row_carries_the_flag(self):
        screen = _screen()
        screen.scan_result = {
            "rows": [
                _row(codes=[]),
                _row(codes=[MACRO_CALENDAR_STALE]),
                _row(codes=[]),
            ]
        }

        screen._update_status_summary()

        text = screen.status_summary_label.text()
        assert text.count(HINT_TEXT) == 1  # ĐÚNG một dòng
        assert "phạm vi lịch kinh tế không tươi" in text

    def test_no_hint_when_no_row_carries_the_flag(self):
        screen = _screen()
        screen.scan_result = {"rows": [_row(codes=[]), _row(codes=["MACRO_LOW_CONFIDENCE"])]}

        screen._update_status_summary()

        assert HINT_TEXT not in screen.status_summary_label.text()

    def test_no_hint_before_the_first_scan(self):
        screen = _screen()

        screen._update_status_summary()

        assert screen.scan_result is None
        assert HINT_TEXT not in screen.status_summary_label.text()

    def test_no_hint_for_rows_without_the_macro_bucket(self):
        screen = _screen()
        screen.scan_result = {"rows": [_row(with_macro=False)]}

        screen._update_status_summary()

        assert HINT_TEXT not in screen.status_summary_label.text()

    def test_no_hint_when_the_key_is_missing(self):
        """Fixture cũ/fake thiếu key → không lỗi, không nhắc."""
        screen = _screen()
        screen.scan_result = {"rows": [_row(codes=None)]}

        screen._update_status_summary()

        assert HINT_TEXT not in screen.status_summary_label.text()

    def test_new_scan_clears_the_previous_hint(self):
        screen = _screen()
        screen.scan_result = {"rows": [_row(codes=[MACRO_CALENDAR_STALE])]}
        screen._update_status_summary()
        assert HINT_TEXT in screen.status_summary_label.text()

        screen.scan_result = {"rows": [_row(codes=[])]}
        screen._update_status_summary()

        assert HINT_TEXT not in screen.status_summary_label.text()

    def test_summary_keeps_the_scan_counts(self):
        screen = _screen()
        screen.status_labels["Đã quét"].setText("5 / 5")
        screen.scan_result = {"rows": [_row(codes=[MACRO_CALENDAR_STALE])]}

        screen._update_status_summary()

        text = screen.status_summary_label.text()
        assert "Đã quét: 5 / 5" in text
        assert HINT_TEXT in text
