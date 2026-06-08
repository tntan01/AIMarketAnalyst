"""Phase 13.1 — test that FINAL_SCORE_* reason codes import and map to messages."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.reason_codes import (
    FINAL_SCORE_OK,
    FINAL_SCORE_DATA_INCOMPLETE,
    FINAL_SCORE_SIGNAL_DOMINANT,
    FINAL_SCORE_EVIDENCE_NEUTRAL,
    FINAL_SCORE_EVIDENCE_POSITIVE,
    FINAL_SCORE_EVIDENCE_NEGATIVE,
    FINAL_SCORE_EXECUTION_STRONG,
    FINAL_SCORE_EXECUTION_WEAK,
    REASON_CODE_MESSAGES,
    codes_to_messages,
    normalize_codes,
    append_code,
)


EXPECTED_CODES = [
    FINAL_SCORE_OK,
    FINAL_SCORE_DATA_INCOMPLETE,
    FINAL_SCORE_SIGNAL_DOMINANT,
    FINAL_SCORE_EVIDENCE_NEUTRAL,
    FINAL_SCORE_EVIDENCE_POSITIVE,
    FINAL_SCORE_EVIDENCE_NEGATIVE,
    FINAL_SCORE_EXECUTION_STRONG,
    FINAL_SCORE_EXECUTION_WEAK,
]


def test_all_final_score_codes_defined():
    """Every FINAL_SCORE_* constant is a non-empty string."""
    for code in EXPECTED_CODES:
        assert isinstance(code, str) and len(code) > 0


def test_all_final_score_codes_have_messages():
    """Every FINAL_SCORE_* appears in REASON_CODE_MESSAGES."""
    for code in EXPECTED_CODES:
        assert code in REASON_CODE_MESSAGES, f"Missing message for {code}"
        msg = REASON_CODE_MESSAGES[code]
        assert isinstance(msg, str) and len(msg) > 0


def test_codes_to_messages_resolves_all():
    """codes_to_messages returns Vietnamese strings for all FINAL_SCORE_*."""
    messages = codes_to_messages(EXPECTED_CODES)
    assert len(messages) == len(EXPECTED_CODES)
    for msg in messages:
        assert isinstance(msg, str) and len(msg) > 0


def test_normalize_codes_accepts_final_score_codes():
    """normalize_codes returns the same list for valid FINAL_SCORE_* codes."""
    result = normalize_codes(EXPECTED_CODES)
    assert result == EXPECTED_CODES


def test_append_code_adds_new_code():
    """append_code adds a FINAL_SCORE_* code when not already present."""
    target: list[str] = [FINAL_SCORE_OK]
    append_code(target, FINAL_SCORE_DATA_INCOMPLETE)
    assert FINAL_SCORE_DATA_INCOMPLETE in target
    assert len(target) == 2


def test_append_code_no_duplicate():
    """append_code does not add duplicate codes."""
    target: list[str] = [FINAL_SCORE_OK]
    append_code(target, FINAL_SCORE_OK)
    assert target == [FINAL_SCORE_OK]


def test_existing_codes_not_affected():
    """Phase 9-12 codes are still present and unchanged."""
    from core.reason_codes import (
        TREND_D1_H4_ALIGNED,
        M15_STRICT_CONFIRMED,
        MACRO_ALIGNED,
        STAT_EDGE_POSITIVE,
        EXECUTION_QUALITY_OK,
        MISTAKE_DETECTOR_OK,
    )
    assert TREND_D1_H4_ALIGNED in REASON_CODE_MESSAGES
    assert M15_STRICT_CONFIRMED in REASON_CODE_MESSAGES
    assert MACRO_ALIGNED in REASON_CODE_MESSAGES
    assert STAT_EDGE_POSITIVE in REASON_CODE_MESSAGES
    assert EXECUTION_QUALITY_OK in REASON_CODE_MESSAGES
    assert MISTAKE_DETECTOR_OK in REASON_CODE_MESSAGES
