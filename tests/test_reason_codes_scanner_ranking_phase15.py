"""Phase 15.1 — test SCANNER_* reason codes import and messages."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.reason_codes import (
    SCANNER_RANKING_READY_NOW,
    SCANNER_RANKING_WAITING_CONFIRMATION,
    SCANNER_RANKING_WATCH_ZONE,
    SCANNER_RANKING_BLOCKED,
    SCANNER_OPPORTUNITY_SCORE_OK,
    SCANNER_OPPORTUNITY_DATA_INCOMPLETE,
    SCANNER_PROXIMITY_IN_ZONE,
    SCANNER_PROXIMITY_NEAR_ZONE,
    SCANNER_PROXIMITY_FAR,
    SCANNER_RR_STRONG,
    SCANNER_RR_WEAK,
    SCANNER_NEWS_PENALTY,
    SCANNER_SPREAD_PENALTY,
    REASON_CODE_MESSAGES,
    codes_to_messages,
    normalize_codes,
    append_code,
)


CODES = [
    SCANNER_RANKING_READY_NOW,
    SCANNER_RANKING_WAITING_CONFIRMATION,
    SCANNER_RANKING_WATCH_ZONE,
    SCANNER_RANKING_BLOCKED,
    SCANNER_OPPORTUNITY_SCORE_OK,
    SCANNER_OPPORTUNITY_DATA_INCOMPLETE,
    SCANNER_PROXIMITY_IN_ZONE,
    SCANNER_PROXIMITY_NEAR_ZONE,
    SCANNER_PROXIMITY_FAR,
    SCANNER_RR_STRONG,
    SCANNER_RR_WEAK,
    SCANNER_NEWS_PENALTY,
    SCANNER_SPREAD_PENALTY,
]


def test_all_codes_defined():
    for code in CODES:
        assert isinstance(code, str) and len(code) > 0


def test_all_codes_have_messages():
    for code in CODES:
        assert code in REASON_CODE_MESSAGES, f"Missing message for {code}"
        assert isinstance(REASON_CODE_MESSAGES[code], str)


def test_codes_to_messages():
    messages = codes_to_messages(CODES)
    assert len(messages) == len(CODES)
    for msg in messages:
        assert isinstance(msg, str) and len(msg) > 0


def test_normalize_accepts_scanner_codes():
    result = normalize_codes(CODES)
    assert result == CODES


def test_append_code_adds():
    target: list[str] = [SCANNER_RANKING_READY_NOW]
    append_code(target, SCANNER_PROXIMITY_IN_ZONE)
    assert len(target) == 2
    assert SCANNER_PROXIMITY_IN_ZONE in target


def test_no_duplicate():
    target: list[str] = [SCANNER_PROXIMITY_NEAR_ZONE]
    append_code(target, SCANNER_PROXIMITY_NEAR_ZONE)
    assert len(target) == 1


def test_phase9_14_codes_unaffected():
    from core.reason_codes import (
        TREND_D1_H4_ALIGNED,
        M15_STRICT_CONFIRMED,
        STAT_EDGE_POSITIVE,
        EXECUTION_QUALITY_OK,
        MISTAKE_DETECTOR_OK,
        FINAL_SCORE_OK,
        DECISION_READY_TO_TRADE,
    )
    for code in [TREND_D1_H4_ALIGNED, M15_STRICT_CONFIRMED, STAT_EDGE_POSITIVE,
                 EXECUTION_QUALITY_OK, MISTAKE_DETECTOR_OK, FINAL_SCORE_OK,
                 DECISION_READY_TO_TRADE]:
        assert code in REASON_CODE_MESSAGES
