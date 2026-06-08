"""Phase 9.1 tests: verify reason_codes module constants and helpers."""

from __future__ import annotations

import core.reason_codes as rc


# ---------------------------------------------------------------------------
# Constants exist and are string identities
# ---------------------------------------------------------------------------

_EXPECTED_CONSTANTS = [
    # Trend / Location / SMC
    ("TREND_D1_H4_ALIGNED", "TREND_D1_H4_ALIGNED"),
    ("PRICE_NEAR_SUPPORT", "PRICE_NEAR_SUPPORT"),
    ("PRICE_NEAR_RESISTANCE", "PRICE_NEAR_RESISTANCE"),
    ("CHOCH_AGAINST_DIRECTION", "CHOCH_AGAINST_DIRECTION"),
    ("ZONE_BROKEN", "ZONE_BROKEN"),
    ("SWEEP_DISPLACEMENT_M15_ALIGNED", "SWEEP_DISPLACEMENT_M15_ALIGNED"),
    # M15
    ("M15_STRICT_CONFIRMED", "M15_STRICT_CONFIRMED"),
    ("M15_LOOSE_CONFIRMATION", "M15_LOOSE_CONFIRMATION"),
    ("M15_NOT_CONFIRMED", "M15_NOT_CONFIRMED"),
    ("M15_DATA_UNAVAILABLE", "M15_DATA_UNAVAILABLE"),
    # Spread / News / Data / MT5
    ("SPREAD_NORMAL", "SPREAD_NORMAL"),
    ("SPREAD_CAUTION", "SPREAD_CAUTION"),
    ("SPREAD_ABNORMAL", "SPREAD_ABNORMAL"),
    ("HIGH_IMPACT_NEWS_NEARBY", "HIGH_IMPACT_NEWS_NEARBY"),
    ("DATA_QUALITY_WARNING", "DATA_QUALITY_WARNING"),
    ("MT5_NOT_READY", "MT5_NOT_READY"),
    # R:R
    ("EXPECTED_RR_OK", "EXPECTED_RR_OK"),
    ("EXPECTED_RR_TOO_LOW", "EXPECTED_RR_TOO_LOW"),
    # Account guard
    ("DAILY_LOSS_LIMIT_REACHED", "DAILY_LOSS_LIMIT_REACHED"),
    ("WEEKLY_LOSS_LIMIT_REACHED", "WEEKLY_LOSS_LIMIT_REACHED"),
    ("MAX_CONSECUTIVE_LOSSES_REACHED", "MAX_CONSECUTIVE_LOSSES_REACHED"),
    ("MAX_OPEN_RISK_REACHED", "MAX_OPEN_RISK_REACHED"),
    # Macro
    ("MACRO_ALIGNED", "MACRO_ALIGNED"),
    ("MACRO_UNCLEAR", "MACRO_UNCLEAR"),
    ("MACRO_CONFLICT", "MACRO_CONFLICT"),
    # Score gap
    ("BUY_SELL_SCORE_GAP_LOW", "BUY_SELL_SCORE_GAP_LOW"),
    # Statistical edge
    ("STAT_EDGE_NOT_ENOUGH_DATA", "STAT_EDGE_NOT_ENOUGH_DATA"),
    ("STAT_EDGE_POSITIVE", "STAT_EDGE_POSITIVE"),
    ("STAT_EDGE_NEGATIVE", "STAT_EDGE_NEGATIVE"),
]


class TestReasonCodeConstants:
    def test_all_constants_exist_with_correct_value(self):
        for attr, expected in _EXPECTED_CONSTANTS:
            assert hasattr(rc, attr), f"missing constant: {attr}"
            assert getattr(rc, attr) == expected, f"{attr} != {expected!r}"

    def test_every_constant_has_message(self):
        for attr, code in _EXPECTED_CONSTANTS:
            assert code in rc.REASON_CODE_MESSAGES, (
                f"{attr} ({code!r}) missing from REASON_CODE_MESSAGES"
            )
            msg = rc.REASON_CODE_MESSAGES[code]
            assert isinstance(msg, str) and len(msg) > 0, (
                f"empty message for {code}"
            )


# ---------------------------------------------------------------------------
# normalize_codes
# ---------------------------------------------------------------------------


class TestNormalizeCodes:
    def test_none_returns_empty(self):
        assert rc.normalize_codes(None) == []

    def test_empty_list_returns_empty(self):
        assert rc.normalize_codes([]) == []

    def test_drops_none_and_empty_strings(self):
        result = rc.normalize_codes(["A", None, "", "B", None])
        assert result == ["A", "B"]

    def test_deduplicates_keeping_first_occurrence(self):
        result = rc.normalize_codes(["X", "Y", "X", "Z", "Y"])
        assert result == ["X", "Y", "Z"]

    def test_preserves_insertion_order(self):
        codes = ["C", "A", "B", "A", "C"]
        assert rc.normalize_codes(codes) == ["C", "A", "B"]

    def test_accepts_tuple(self):
        assert rc.normalize_codes(("A", "B", "A")) == ["A", "B"]


# ---------------------------------------------------------------------------
# codes_to_messages
# ---------------------------------------------------------------------------


class TestCodesToMessages:
    def test_translates_known_codes(self):
        messages = rc.codes_to_messages([rc.SPREAD_ABNORMAL, rc.M15_STRICT_CONFIRMED])
        assert len(messages) == 2
        assert any("bất thường" in m for m in messages)
        assert any("chặt" in m for m in messages)

    def test_returns_raw_code_for_unknown(self):
        messages = rc.codes_to_messages(["UNKNOWN_CODE_XYZ"])
        assert messages == ["UNKNOWN_CODE_XYZ"]

    def test_handles_none_input(self):
        assert rc.codes_to_messages(None) == []

    def test_deduplicates_before_translating(self):
        messages = rc.codes_to_messages([rc.MACRO_ALIGNED, rc.MACRO_ALIGNED])
        assert len(messages) == 1


# ---------------------------------------------------------------------------
# append_code
# ---------------------------------------------------------------------------


class TestAppendCode:
    def test_appends_new_code(self):
        target: list[str] = []
        rc.append_code(target, rc.SPREAD_NORMAL)
        assert target == [rc.SPREAD_NORMAL]

    def test_does_not_append_duplicate(self):
        target = [rc.SPREAD_NORMAL]
        rc.append_code(target, rc.SPREAD_NORMAL)
        assert target == [rc.SPREAD_NORMAL]

    def test_ignores_none(self):
        target: list[str] = []
        rc.append_code(target, None)
        assert target == []

    def test_ignores_empty_string(self):
        target: list[str] = []
        rc.append_code(target, "")
        assert target == []
