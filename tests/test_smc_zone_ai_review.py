"""Unit tests for the AI review of the selected SMC zone (mock AI only)."""

from __future__ import annotations

import json

import pytest

from core.smc_zone_ai_review import (
    build_zone_review_prompt,
    default_zone_review,
    parse_zone_review,
    review_selected_zone,
)


def _zone_data(**overrides):
    payload = {
        "symbol": "XAU/USD",
        "zone_type": "order_block",
        "direction": "buy",
        "timeframe": "H4",
        "displacement": 2.4,
        "price": 2001.0,
        "low": 2000.0,
        "high": 2003.0,
        "atr": 10.0,
        "liquidity": {"swept_lows": 1, "equal_highs": False},
    }
    payload.update(overrides)
    return payload


class _FakeAIService:
    """Stands in for services.ai_service.AIService (mock AI responses)."""

    def __init__(self, response):
        self.response = response
        self.calls = []

    def analyze(self, prompt, *, max_tokens=4000):
        self.calls.append({"prompt": prompt, "max_tokens": max_tokens})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _valid_response(**overrides):
    payload = {
        "zone_validity": 8,
        "liquidity_setup": "strong",
        "displacement_quality": 7.5,
        "confidence": 0.9,
        "reasons": ["OB tươi chưa bị mitigate", "Đã quét liquidity trước đó"],
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


def test_review_selected_zone_parses_valid_response():
    ai = _FakeAIService(_valid_response())

    result = review_selected_zone(_zone_data(), ai)

    assert result["status"] == "valid"
    assert result["zone_validity"] == 8
    assert result["liquidity_setup"] == "strong"
    assert result["displacement_quality"] == 7.5
    assert result["confidence"] == 0.9
    assert result["reasons"] == [
        "OB tươi chưa bị mitigate",
        "Đã quét liquidity trước đó",
    ]
    assert result["review_error"] == ""
    assert len(ai.calls) == 1
    assert "XAU/USD" in ai.calls[0]["prompt"]


def test_review_selected_zone_accepts_fenced_json_and_normalizes_enum():
    raw = """```json
    {
      "zone_validity": 6.5,
      "liquidity_setup": "Strong",
      "displacement_quality": 4,
      "confidence": 0.55,
      "reasons": ["  Zone đã được test một lần  "]
    }
    ```"""
    ai = _FakeAIService(raw)

    result = review_selected_zone(_zone_data(), ai)

    assert result["status"] == "valid"
    assert result["zone_validity"] == 6.5
    assert result["liquidity_setup"] == "strong"
    assert result["displacement_quality"] == 4
    assert result["confidence"] == 0.55
    assert result["reasons"] == ["Zone đã được test một lần"]


def test_review_selected_zone_ai_exception_is_uncertain():
    ai = _FakeAIService(RuntimeError("provider HTTP 500"))

    result = review_selected_zone(_zone_data(), ai)

    assert result["status"] == "uncertain"
    assert result["review_error"] == "ai_error"
    assert result["zone_validity"] is None
    assert result["liquidity_setup"] is None
    assert result["displacement_quality"] is None
    assert result["confidence"] == 0.0
    assert result["reasons"] == []


def test_review_selected_zone_invalid_json_is_uncertain():
    ai = _FakeAIService("không phải json")

    result = review_selected_zone(_zone_data(), ai)

    assert result["status"] == "uncertain"
    assert result["review_error"] == "invalid_json"
    assert result["raw_response"] == "không phải json"
    assert result["zone_validity"] is None


@pytest.mark.parametrize(
    "response",
    [
        # Missing required key (displacement_quality).
        {"zone_validity": 5, "liquidity_setup": "weak", "confidence": 0.5,
         "reasons": []},
        # zone_validity out of range.
        {"zone_validity": 15, "liquidity_setup": "weak",
         "displacement_quality": 5, "confidence": 0.5, "reasons": []},
        # displacement_quality negative.
        {"zone_validity": 5, "liquidity_setup": "weak",
         "displacement_quality": -1, "confidence": 0.5, "reasons": []},
        # confidence out of range.
        {"zone_validity": 5, "liquidity_setup": "weak",
         "displacement_quality": 5, "confidence": 1.5, "reasons": []},
        # liquidity_setup outside the enum.
        {"zone_validity": 5, "liquidity_setup": "maybe",
         "displacement_quality": 5, "confidence": 0.5, "reasons": []},
        # reasons not a list.
        {"zone_validity": 5, "liquidity_setup": "weak",
         "displacement_quality": 5, "confidence": 0.5,
         "reasons": "zone đẹp"},
        # Numeric fields must be JSON numbers, not strings.
        {"zone_validity": "8", "liquidity_setup": "weak",
         "displacement_quality": 5, "confidence": 0.5, "reasons": []},
        # Booleans are not valid scores.
        {"zone_validity": True, "liquidity_setup": "weak",
         "displacement_quality": 5, "confidence": 0.5, "reasons": []},
    ],
)
def test_review_selected_zone_schema_violation_is_uncertain(response):
    ai = _FakeAIService(json.dumps(response, ensure_ascii=False))

    result = review_selected_zone(_zone_data(), ai)

    assert result["status"] == "uncertain"
    assert result["review_error"] == "invalid_schema"
    assert result["zone_validity"] is None
    assert result["liquidity_setup"] is None
    assert result["displacement_quality"] is None
    assert result["confidence"] == 0.0
    assert result["reasons"] == []


def test_review_selected_zone_without_ai_service_is_uncertain():
    result = review_selected_zone(_zone_data(), None)

    assert result["status"] == "uncertain"
    assert result["review_error"] == "ai_unavailable"


def test_review_selected_zone_missing_zone_data_does_not_call_ai():
    ai = _FakeAIService(_valid_response())

    assert (
        review_selected_zone({}, ai)["review_error"] == "missing_zone_data"
    )
    assert (
        review_selected_zone(None, ai)["review_error"] == "missing_zone_data"
    )
    assert ai.calls == []


def test_build_zone_review_prompt_includes_schema_and_zone_data():
    prompt = build_zone_review_prompt(_zone_data())

    assert '"zone_validity": 0-10' in prompt
    assert '"liquidity_setup": "strong|weak|none"' in prompt
    assert '"displacement_quality": 0-10' in prompt
    assert '"confidence": 0-1' in prompt
    assert "XAU/USD" in prompt
    assert "order_block" in prompt
    assert "H4" in prompt
    # Price 2001 lies inside the zone [2000, 2003].
    assert "inside_zone" in prompt


def test_zone_review_prompt_price_position_and_distance():
    above = build_zone_review_prompt(_zone_data(price=2013.0))
    assert "above_zone" in above
    assert '"distance_atr": 1.0' in above

    below = build_zone_review_prompt(_zone_data(price=1990.0))
    assert "below_zone" in below
    assert '"distance_atr": 1.0' in below

    unknown = build_zone_review_prompt(_zone_data(price=None))
    assert "unknown" in unknown


def test_parse_zone_review_normalizes_reasons_list():
    raw = _valid_response(reasons=[
        "  lý do một  ",
        "",
        "   ",
        "lý do hai",
        123,
    ])

    result = parse_zone_review(raw)

    assert result["status"] == "valid"
    assert result["reasons"] == ["lý do một", "lý do hai", "123"]


def test_parse_zone_review_caps_reason_count():
    raw = _valid_response(reasons=[f"lý do {i}" for i in range(20)])

    result = parse_zone_review(raw)

    assert result["status"] == "valid"
    assert len(result["reasons"]) == 8


def test_default_zone_review_is_uncertain_and_applies_nothing():
    review = default_zone_review("ai_error")

    assert review["status"] == "uncertain"
    assert review["zone_validity"] is None
    assert review["liquidity_setup"] is None
    assert review["displacement_quality"] is None
    assert review["confidence"] == 0.0
    assert review["reasons"] == []
    assert review["review_error"] == "ai_error"
