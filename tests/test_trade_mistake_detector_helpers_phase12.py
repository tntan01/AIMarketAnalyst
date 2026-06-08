"""Phase 12.3 tests: verify safe helper functions in trade_mistake_detector."""

from __future__ import annotations

from datetime import UTC, datetime

from core.trade_mistake_detector import (
    add_unique,
    normalize_tags,
    safe_datetime,
    safe_float,
    truthy,
)


# ---------------------------------------------------------------------------
# safe_float
# ---------------------------------------------------------------------------

class TestSafeFloat:
    def test_int(self):
        assert safe_float(42) == 42.0

    def test_float(self):
        assert safe_float(3.14) == 3.14

    def test_valid_string(self):
        assert safe_float("1.25") == 1.25

    def test_string_with_whitespace(self):
        assert safe_float("  2.0 ") == 2.0

    def test_negative_string(self):
        assert safe_float("-0.5") == -0.5

    def test_invalid_string_returns_default(self):
        assert safe_float("abc", default=-1.0) == -1.0

    def test_none_returns_default(self):
        assert safe_float(None, default=99.0) == 99.0

    def test_empty_string_returns_default(self):
        assert safe_float("", default=7.0) == 7.0

    def test_nan_returns_default(self):
        assert safe_float(float("nan"), default=-1.0) == -1.0

    def test_inf_returns_default(self):
        assert safe_float(float("inf"), default=-1.0) == -1.0

    def test_default_default_is_zero(self):
        assert safe_float("xyz") == 0.0

    def test_bool_true_converts(self):
        assert safe_float(True) == 1.0

    def test_bool_false_converts(self):
        assert safe_float(False) == 0.0


# ---------------------------------------------------------------------------
# safe_datetime
# ---------------------------------------------------------------------------

class TestSafeDatetime:
    def test_datetime_object_passthrough(self):
        dt = datetime(2026, 6, 4, 9, 30, tzinfo=UTC)
        assert safe_datetime(dt) == dt

    def test_iso_with_z(self):
        result = safe_datetime("2026-06-04T09:30:00Z")
        assert result is not None
        assert result.year == 2026
        assert result.month == 6
        assert result.day == 4
        assert result.hour == 9
        assert result.minute == 30

    def test_iso_with_offset(self):
        result = safe_datetime("2026-06-04T09:30:00+00:00")
        assert result is not None

    def test_iso_with_positive_offset(self):
        result = safe_datetime("2026-06-04T16:30:00+07:00")
        assert result is not None
        # offset-preserving — hour stays as given, tzinfo records offset
        assert result.utcoffset() is not None

    def test_bad_string_returns_none(self):
        assert safe_datetime("bad") is None

    def test_none_returns_none(self):
        assert safe_datetime(None) is None

    def test_empty_string_returns_none(self):
        assert safe_datetime("") is None

    def test_no_timezone_treated_as_utc(self):
        result = safe_datetime("2026-06-04T09:30:00")
        assert result is not None
        assert result.tzinfo is not None


# ---------------------------------------------------------------------------
# truthy
# ---------------------------------------------------------------------------

class TestTruthy:
    def test_bool_true(self):
        assert truthy(True) is True

    def test_bool_false(self):
        assert truthy(False) is False

    def test_int_one(self):
        assert truthy(1) is True

    def test_int_zero(self):
        assert truthy(0) is False

    def test_str_true(self):
        assert truthy("true") is True

    def test_str_yes(self):
        assert truthy("yes") is True

    def test_str_y(self):
        assert truthy("y") is True

    def test_str_one(self):
        assert truthy("1") is True

    def test_str_false(self):
        assert truthy("false") is False

    def test_str_no(self):
        assert truthy("no") is False

    def test_str_zero(self):
        assert truthy("0") is False

    def test_vietnamese_co(self):
        assert truthy("có") is True

    def test_vietnamese_dung(self):
        assert truthy("đúng") is True

    def test_vietnamese_khong(self):
        assert truthy("không") is False

    def test_vietnamese_sai(self):
        assert truthy("sai") is False

    def test_none_is_false(self):
        assert truthy(None) is False

    def test_empty_string_is_false(self):
        assert truthy("") is False

    def test_unknown_string_is_false(self):
        assert truthy("maybe") is False


# ---------------------------------------------------------------------------
# normalize_tags
# ---------------------------------------------------------------------------

class TestNormalizeTags:
    def test_none_returns_empty(self):
        assert normalize_tags(None) == []

    def test_empty_list_returns_empty(self):
        assert normalize_tags([]) == []

    def test_list_of_strings(self):
        assert normalize_tags(["Chased_Price", "IGNORED_M15"]) == ["chased_price", "ignored_m15"]

    def test_tuple(self):
        assert normalize_tags(("A", "B")) == ["a", "b"]

    def test_json_list_string(self):
        result = normalize_tags('["ignored_m15", "oversized_position"]')
        assert result == ["ignored_m15", "oversized_position"]

    def test_comma_separated_string(self):
        result = normalize_tags("ignored_m15, oversized_position")
        assert result == ["ignored_m15", "oversized_position"]

    def test_comma_separated_with_spaces(self):
        result = normalize_tags(" chased_price , moved_stop_loss ")
        assert result == ["chased_price", "moved_stop_loss"]

    def test_empty_string_returns_empty(self):
        assert normalize_tags("") == []

    def test_filters_empty_elements(self):
        result = normalize_tags(["", "valid", "  "])
        assert result == ["valid"]

    def test_set_input(self):
        assert sorted(normalize_tags({"A", "B"})) == ["a", "b"]

    def test_invalid_json_falls_back_to_comma(self):
        result = normalize_tags("chased_price, oversized_position")
        assert result == ["chased_price", "oversized_position"]

    def test_broken_json_list_falls_back_to_comma(self):
        # "[broken, json" — does not start+end with [] pair, so comma-parsed
        result = normalize_tags("[broken, json")
        assert "json" in result


# ---------------------------------------------------------------------------
# add_unique
# ---------------------------------------------------------------------------

class TestAddUnique:
    def test_adds_new_item(self):
        items: list[str] = ["a"]
        add_unique(items, "b")
        assert items == ["a", "b"]

    def test_does_not_add_duplicate(self):
        items = ["a", "b"]
        add_unique(items, "a")
        assert items == ["a", "b"]

    def test_ignores_empty_string(self):
        items: list[str] = ["a"]
        add_unique(items, "")
        assert items == ["a"]

    def test_preserves_order(self):
        items = ["z", "a", "b"]
        add_unique(items, "c")
        assert items == ["z", "a", "b", "c"]
