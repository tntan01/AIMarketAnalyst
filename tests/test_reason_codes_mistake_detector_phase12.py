"""Phase 12.1 tests: verify MISTAKE_* constants exist in reason_codes module."""

from __future__ import annotations

import core.reason_codes as rc

# ---------------------------------------------------------------------------
# Phase 12 mistake detector constants
# ---------------------------------------------------------------------------

_MISTAKE_CONSTANTS = [
    ("MISTAKE_ENTERED_TOO_EARLY", "MISTAKE_ENTERED_TOO_EARLY"),
    ("MISTAKE_CHASED_PRICE", "MISTAKE_CHASED_PRICE"),
    ("MISTAKE_IGNORED_M15", "MISTAKE_IGNORED_M15"),
    ("MISTAKE_IGNORED_NEWS", "MISTAKE_IGNORED_NEWS"),
    ("MISTAKE_MOVED_STOP_LOSS", "MISTAKE_MOVED_STOP_LOSS"),
    ("MISTAKE_CLOSED_TOO_EARLY", "MISTAKE_CLOSED_TOO_EARLY"),
    ("MISTAKE_OVERSIZED_POSITION", "MISTAKE_OVERSIZED_POSITION"),
    ("MISTAKE_REVENGE_TRADE_WARNING", "MISTAKE_REVENGE_TRADE_WARNING"),
    ("MISTAKE_REVENGE_TRADE_CONFIRMED", "MISTAKE_REVENGE_TRADE_CONFIRMED"),
    ("MISTAKE_DATA_INCOMPLETE", "MISTAKE_DATA_INCOMPLETE"),
    ("MISTAKE_DETECTOR_OK", "MISTAKE_DETECTOR_OK"),
]


class TestMistakeConstants:
    def test_all_mistake_constants_exist(self):
        for attr, expected in _MISTAKE_CONSTANTS:
            assert hasattr(rc, attr), f"missing constant: {attr}"
            assert getattr(rc, attr) == expected, f"{attr} != {expected!r}"

    def test_every_mistake_constant_has_message(self):
        for attr, code in _MISTAKE_CONSTANTS:
            assert code in rc.REASON_CODE_MESSAGES, (
                f"{attr} ({code!r}) missing from REASON_CODE_MESSAGES"
            )
            msg = rc.REASON_CODE_MESSAGES[code]
            assert isinstance(msg, str) and len(msg) > 0, (
                f"empty message for {code}"
            )

    def test_mistake_detector_ok_imports(self):
        assert rc.MISTAKE_DETECTOR_OK == "MISTAKE_DETECTOR_OK"

    def test_mistake_chased_price_message_is_vietnamese(self):
        msg = rc.REASON_CODE_MESSAGES[rc.MISTAKE_CHASED_PRICE]
        assert "đuổi giá" in msg

    def test_mistake_oversized_message_is_vietnamese(self):
        msg = rc.REASON_CODE_MESSAGES[rc.MISTAKE_OVERSIZED_POSITION]
        assert "khối lượng" in msg.lower()
