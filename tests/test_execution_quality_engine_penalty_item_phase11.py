"""Phase 11.4: verify penalty item helpers."""

from __future__ import annotations

from core.execution_quality_engine import make_penalty_item, sum_penalty_points


class TestMakePenaltyItem:
    def test_normal_item(self):
        item = make_penalty_item("EXECUTION_CHASED_PRICE", 25, "Đuổi giá")
        assert item["code"] == "EXECUTION_CHASED_PRICE"
        assert item["points"] == 25
        assert item["description"] == "Đuổi giá"

    def test_negative_points_converted_to_positive(self):
        item = make_penalty_item("EXECUTION_OVERSIZED", -30)
        assert item["points"] == 30

    def test_empty_code_fallback(self):
        item = make_penalty_item("", 10)
        assert item["code"] == "UNKNOWN_EXECUTION_PENALTY"

    def test_whitespace_code_fallback(self):
        item = make_penalty_item("   ", 10)
        assert item["code"] == "UNKNOWN_EXECUTION_PENALTY"

    def test_zero_points(self):
        item = make_penalty_item("CODE", 0)
        assert item["points"] == 0

    def test_description_defaults_empty(self):
        item = make_penalty_item("CODE", 5)
        assert item["description"] == ""

    def test_non_integer_points_still_works(self):
        item = make_penalty_item("CODE", "abc")  # type: ignore[arg-type]
        assert item["points"] == 0

    def test_float_points_truncated_to_int(self):
        item = make_penalty_item("CODE", 25.7)
        assert item["points"] == 25  # int(25.7) = 25


class TestSumPenaltyPoints:
    def test_normal_list(self):
        items = [
            make_penalty_item("A", 25),
            make_penalty_item("B", 30),
            make_penalty_item("C", 15),
        ]
        assert sum_penalty_points(items) == 70

    def test_empty_list(self):
        assert sum_penalty_points([]) == 0

    def test_none_returns_zero(self):
        assert sum_penalty_points(None) == 0

    def test_skips_non_dict_items(self):
        items = [
            make_penalty_item("A", 25),
            "not_a_dict",
            None,
            make_penalty_item("B", 10),
        ]
        assert sum_penalty_points(items) == 35  # type: ignore[arg-type]

    def test_skips_missing_points(self):
        items = [
            make_penalty_item("A", 25),
            {"code": "B"},  # no points key
        ]
        assert sum_penalty_points(items) == 25
