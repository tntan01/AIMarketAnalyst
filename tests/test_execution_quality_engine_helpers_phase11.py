"""Phase 11.3: verify execution quality helper functions."""

from __future__ import annotations

from core.execution_quality_engine import has_tag, normalize_tags, truthy


class TestTruthy:
    def test_bool_types(self):
        assert truthy(True) is True
        assert truthy(False) is False

    def test_numeric(self):
        assert truthy(1) is True
        assert truthy(0) is False
        assert truthy(-1) is True  # non-zero

    def test_english_strings(self):
        for v in ("true", "True", "TRUE", "yes", "y", "1"):
            assert truthy(v) is True, f"{v!r}"
        for v in ("false", "False", "no", "n", "0"):
            assert truthy(v) is False, f"{v!r}"

    def test_vietnamese_strings(self):
        for v in ("có", "co", "đúng", "dung"):
            assert truthy(v) is True, f"{v!r}"
        for v in ("không", "khong", "sai"):
            assert truthy(v) is False, f"{v!r}"

    def test_whitespace(self):
        assert truthy("  yes  ") is True
        assert truthy("  no  ") is False

    def test_none_returns_false(self):
        assert truthy(None) is False

    def test_empty_string_returns_false(self):
        assert truthy("") is False

    def test_unknown_string_returns_false(self):
        assert truthy("maybe") is False
        assert truthy("abc") is False


class TestNormalizeTags:
    def test_list(self):
        assert normalize_tags(["chased_price", "oversized_position"]) == ["chased_price", "oversized_position"]

    def test_tuple(self):
        assert normalize_tags(("chased_price",)) == ["chased_price"]

    def test_set(self):
        result = normalize_tags({"a", "b"})
        assert sorted(result) == ["a", "b"]

    def test_json_list_string(self):
        assert normalize_tags('["chased_price", "moved_sl_further"]') == ["chased_price", "moved_sl_further"]

    def test_comma_separated_string(self):
        assert normalize_tags("chased_price, oversized_position") == ["chased_price", "oversized_position"]

    def test_strips_whitespace(self):
        assert normalize_tags(["  chased_price  "]) == ["chased_price"]

    def test_lowercases(self):
        assert normalize_tags(["Chased_Price"]) == ["chased_price"]

    def test_removes_empty_entries(self):
        result = normalize_tags(["a", "", "  ", "b"])
        assert result == ["a", "b"]

    def test_none_returns_empty(self):
        assert normalize_tags(None) == []

    def test_empty_string_returns_empty(self):
        assert normalize_tags("") == []

    def test_non_parseable_returns_empty(self):
        assert normalize_tags(123) == []
        assert normalize_tags(object()) == []


class TestHasTag:
    def test_manual_mistake_tags(self):
        trade = {"manual_mistake_tags": ["chased_price", "oversized_position"]}
        assert has_tag(trade, "chased_price") is True
        assert has_tag(trade, "oversized_position") is True
        assert has_tag(trade, "revenge_trade") is False

    def test_auto_mistake_tags_string(self):
        trade = {"auto_mistake_tags": "moved_sl_further, revenge_trade"}
        assert has_tag(trade, "moved_sl_further") is True
        assert has_tag(trade, "revenge_trade") is True

    def test_execution_tags_json(self):
        trade = {"execution_tags": '["chased_price", "moved_sl_further"]'}
        assert has_tag(trade, "chased_price") is True
        assert has_tag(trade, "moved_sl_further") is True

    def test_mistake_tags_field(self):
        trade = {"mistake_tags": ["oversized_position"]}
        assert has_tag(trade, "oversized_position") is True

    def test_case_insensitive(self):
        trade = {"manual_mistake_tags": ["Chased_Price"]}
        assert has_tag(trade, "CHASED_PRICE") is True
        assert has_tag(trade, "chased_price") is True

    def test_non_dict_returns_false(self):
        assert has_tag("not_a_dict", "chased_price") is False  # type: ignore[arg-type]
        assert has_tag(None, "chased_price") is False  # type: ignore[arg-type]

    def test_empty_tag_returns_false(self):
        trade = {"manual_mistake_tags": ["chased_price"]}
        assert has_tag(trade, "") is False

    def test_multiple_fields_searched(self):
        trade = {
            "auto_mistake_tags": ["a"],
            "manual_mistake_tags": ["b"],
            "mistake_tags": ["c"],
            "execution_tags": ["d"],
        }
        assert has_tag(trade, "a") is True
        assert has_tag(trade, "b") is True
        assert has_tag(trade, "c") is True
        assert has_tag(trade, "d") is True
        assert has_tag(trade, "e") is False
