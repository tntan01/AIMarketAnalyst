"""Phase 17.5 — test journal tag serialization helpers."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.journal_service import normalize_tag_list, tags_to_json, tags_from_json


# ---------------------------------------------------------------------------
# normalize_tag_list
# ---------------------------------------------------------------------------


def test_normalize_list():
    result = normalize_tag_list(["Chased_Price", " chased_price ", ""])
    assert result == ["chased_price"]


def test_normalize_json_string():
    result = normalize_tag_list('["ignored_m15", "oversized_position"]')
    assert result == ["ignored_m15", "oversized_position"]


def test_normalize_comma_string():
    result = normalize_tag_list("ignored_m15, oversized_position")
    assert result == ["ignored_m15", "oversized_position"]


def test_normalize_none():
    assert normalize_tag_list(None) == []


def test_normalize_dirty():
    assert normalize_tag_list("") == []
    assert normalize_tag_list(123) == []  # type: ignore[arg-type]


def test_normalize_deduplicate():
    result = normalize_tag_list(["a", "b", "a", " A "])
    assert result == ["a", "b"]


# ---------------------------------------------------------------------------
# tags_to_json / tags_from_json
# ---------------------------------------------------------------------------


def test_tags_to_json_list():
    result = tags_to_json(["ignored_m15", "oversized_position"])
    assert "ignored_m15" in result
    assert result.startswith("[")
    assert result.endswith("]")


def test_tags_to_json_empty():
    assert tags_to_json(None) == "[]"
    assert tags_to_json([]) == "[]"


def test_tags_roundtrip():
    original = ["chased_price", "ignored_m15"]
    json_str = tags_to_json(original)
    back = tags_from_json(json_str)
    assert back == original


def test_tags_from_json_dirty():
    assert tags_from_json("") == []
    assert tags_from_json(None) == []
