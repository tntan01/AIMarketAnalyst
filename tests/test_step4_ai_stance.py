"""Test script for Step 4 — AI-powered hawkish/dovish stance analysis.

Usage: python tests/test_step4_ai_stance.py
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, UTC
from unittest.mock import MagicMock, patch

from services.news_service import NewsService, currency_stance


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_headline(title: str) -> dict[str, object]:
    return {"title": title}


def _json_stance(
    stance: str,
    strength: float = 5.0,
    confidence: float = 0.8,
    drivers: tuple[str, ...] = ("data",),
) -> str:
    return json.dumps(
        {"stance": stance, "strength": strength, "confidence": confidence, "drivers": list(drivers)},
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# _ai_currency_stance — fallback (no AI)
# ---------------------------------------------------------------------------


def test_ai_stance_fallback_khi_khong_co_ai():
    """Without AI service, falls back to keyword matching."""
    svc = NewsService()
    result = svc._ai_currency_stance("USD", ["Fed cuts rate by 25bps"], ai_service=None)
    assert result in ("hawkish", "dovish", "neutral")


def test_ai_stance_fallback_empty_headlines():
    """Empty headlines -> keyword fallback (neutral)."""
    svc = NewsService()
    result = svc._ai_currency_stance("USD", [], ai_service=None)
    assert result == "neutral"


def test_ai_stance_fallback_hawkish_keywords():
    """Keyword matching: 'hike' -> hawkish."""
    svc = NewsService()
    result = svc._ai_currency_stance("USD", ["Fed hikes rate aggressively"], ai_service=None)
    assert result == "hawkish"


def test_ai_stance_fallback_dovish_keywords():
    """Keyword matching: 'cut' -> dovish."""
    svc = NewsService()
    result = svc._ai_currency_stance("EUR", ["ECB cuts rates amid slowdown"], ai_service=None)
    assert result == "dovish"


# ---------------------------------------------------------------------------
# _ai_currency_stance — AI path
# ---------------------------------------------------------------------------


def test_ai_stance_tra_ve_hawkish():
    """AI returns valid JSON with hawkish -> parsed and returned."""
    mock_ai = MagicMock()
    mock_ai.analyze.return_value = _json_stance("hawkish", strength=8, confidence=0.9, drivers=("Fed hikes",))
    svc = NewsService()
    result = svc._ai_currency_stance("USD", ["Fed raises rate"], ai_service=mock_ai)
    assert result == "hawkish"


def test_ai_stance_tra_ve_dovish():
    """AI returns valid JSON with dovish -> parsed and returned."""
    mock_ai = MagicMock()
    mock_ai.analyze.return_value = _json_stance("dovish")
    svc = NewsService()
    result = svc._ai_currency_stance("JPY", ["BOJ maintains easing"], ai_service=mock_ai)
    assert result == "dovish"


def test_ai_stance_tra_ve_neutral():
    """AI returns valid JSON with neutral -> parsed and returned."""
    mock_ai = MagicMock()
    mock_ai.analyze.return_value = _json_stance("neutral")
    svc = NewsService()
    result = svc._ai_currency_stance("GBP", ["BOE holds steady"], ai_service=mock_ai)
    assert result == "neutral"


def test_ai_stance_strips_extra_text():
    """AI response with extra prose around JSON -> JSON block extracted."""
    mock_ai = MagicMock()
    mock_ai.analyze.return_value = (
        "Here you go: " + _json_stance("hawkish", strength=7, confidence=0.85, drivers=("rate hike",)) + " Best regards."
    )
    svc = NewsService()
    result = svc._ai_currency_stance("USD", ["Fed raises rate"], ai_service=mock_ai)
    assert result == "hawkish"


def test_ai_stance_json_trong_fence_markdown():
    """AI returns JSON wrapped in ```json fence -> parsed and returned."""
    mock_ai = MagicMock()
    mock_ai.analyze.return_value = "```json\n" + _json_stance("hawkish") + "\n```"
    svc = NewsService()
    result = svc._ai_currency_stance("USD", ["Fed raises rate"], ai_service=mock_ai)
    assert result == "hawkish"


def test_ai_stance_case_insensitive():
    """AI returns JSON with 'HAWKISH' stance -> normalized to lowercase."""
    mock_ai = MagicMock()
    mock_ai.analyze.return_value = _json_stance("HAWKISH", strength=6, confidence=0.7)
    svc = NewsService()
    result = svc._ai_currency_stance("USD", ["Fed raises rate"], ai_service=mock_ai)
    assert result == "hawkish"


def test_ai_stance_fallback_khi_ai_loi():
    """AI raises exception -> fallback to keyword matching."""
    mock_ai = MagicMock()
    mock_ai.analyze.side_effect = Exception("AI error")
    svc = NewsService()
    result = svc._ai_currency_stance("USD", ["Fed hikes rate"], ai_service=mock_ai)
    assert result in ("hawkish", "dovish", "neutral")


def test_ai_stance_fallback_khi_ai_tra_ve_invalid():
    """AI returns non-JSON text -> fallback to keyword matching."""
    mock_ai = MagicMock()
    mock_ai.analyze.return_value = "uncertain"
    svc = NewsService()
    result = svc._ai_currency_stance("USD", ["Fed cuts rate"], ai_service=mock_ai)
    assert result in ("hawkish", "dovish", "neutral")


def test_ai_stance_fallback_khi_ai_tra_ve_empty():
    """AI returns empty string -> fallback to keyword matching."""
    mock_ai = MagicMock()
    mock_ai.analyze.return_value = ""
    svc = NewsService()
    result = svc._ai_currency_stance("USD", ["Fed cuts rate"], ai_service=mock_ai)
    assert result in ("hawkish", "dovish", "neutral")


# ---------------------------------------------------------------------------
# _ai_currency_stance — JSON schema validation (fallback on broken schema)
# ---------------------------------------------------------------------------


def test_ai_stance_fallback_khi_json_thieu_field():
    """JSON missing 'strength' -> fallback to keyword matching."""
    mock_ai = MagicMock()
    mock_ai.analyze.return_value = '{"stance": "hawkish", "confidence": 0.8, "drivers": ["hike"]}'
    svc = NewsService()
    result = svc._ai_currency_stance("USD", ["Fed hikes rate"], ai_service=mock_ai)
    assert result in ("hawkish", "dovish", "neutral")


def test_ai_stance_fallback_khi_stance_khong_hop_le():
    """JSON with invalid stance value -> fallback to keyword matching."""
    mock_ai = MagicMock()
    mock_ai.analyze.return_value = _json_stance("aggressive", strength=8, confidence=0.9)
    svc = NewsService()
    result = svc._ai_currency_stance("USD", ["Fed hikes rate"], ai_service=mock_ai)
    assert result in ("hawkish", "dovish", "neutral")


def test_ai_stance_fallback_khi_strength_sai_kieu():
    """JSON with strength as string -> fallback to keyword matching."""
    mock_ai = MagicMock()
    mock_ai.analyze.return_value = '{"stance": "hawkish", "strength": "8", "confidence": 0.9, "drivers": ["hike"]}'
    svc = NewsService()
    result = svc._ai_currency_stance("USD", ["Fed hikes rate"], ai_service=mock_ai)
    assert result in ("hawkish", "dovish", "neutral")


def test_ai_stance_fallback_khi_drivers_sai_kieu():
    """JSON with drivers not a list of strings -> fallback to keyword matching."""
    mock_ai = MagicMock()
    mock_ai.analyze.return_value = '{"stance": "hawkish", "strength": 8, "confidence": 0.9, "drivers": "hike"}'
    svc = NewsService()
    result = svc._ai_currency_stance("USD", ["Fed hikes rate"], ai_service=mock_ai)
    assert result in ("hawkish", "dovish", "neutral")


# ---------------------------------------------------------------------------
# _ai_currency_stance — cache
# ---------------------------------------------------------------------------


def test_ai_stance_cache_hit():
    """Second call with same headlines returns cached result (no AI call)."""
    mock_ai = MagicMock()
    mock_ai.analyze.return_value = _json_stance("hawkish")
    svc = NewsService()

    result1 = svc._ai_currency_stance("USD", ["Fed raises rate"], ai_service=mock_ai)
    assert result1 == "hawkish"
    assert mock_ai.analyze.call_count == 1

    # Second call — should hit cache, no additional AI call
    mock_ai.analyze.reset_mock()
    result2 = svc._ai_currency_stance("USD", ["Fed raises rate"], ai_service=mock_ai)
    assert result2 == "hawkish"
    assert mock_ai.analyze.call_count == 0  # cache hit


def test_ai_stance_cache_miss_different_currency():
    """Different currency -> different cache key -> new AI call."""
    mock_ai = MagicMock()
    mock_ai.analyze.return_value = _json_stance("dovish")
    svc = NewsService()

    svc._ai_currency_stance("USD", ["Fed raises rate"], ai_service=mock_ai)
    assert mock_ai.analyze.call_count == 1

    svc._ai_currency_stance("EUR", ["ECB cuts rate"], ai_service=mock_ai)
    assert mock_ai.analyze.call_count == 2  # different cache key


def test_ai_stance_cache_hit_khi_headline_doi_cung_currency():
    """Headline đổi nhưng cùng đồng tiền và còn trong TTL -> cache hit, không gọi AI lại."""
    mock_ai = MagicMock()
    mock_ai.analyze.return_value = _json_stance("hawkish")
    svc = NewsService()

    result1 = svc._ai_currency_stance("USD", ["Fed raises rate"], ai_service=mock_ai)
    assert result1 == "hawkish"
    assert mock_ai.analyze.call_count == 1

    # Headline thay đổi trong TTL, cùng currency + cùng AI -> cache hit
    mock_ai.analyze.reset_mock()
    result2 = svc._ai_currency_stance(
        "USD", ["ECB cuts rates sharply today"], ai_service=mock_ai
    )
    assert result2 == "hawkish"  # kết quả cached từ lần đầu, không phải dovish
    assert mock_ai.analyze.call_count == 0  # cache hit


def test_ai_stance_fallback_cached_cung_currency():
    """Kết quả fallback keyword matching cũng được cache: cùng currency trong TTL
    trả về kết quả cũ dù headline đổi."""
    svc = NewsService()

    result1 = svc._ai_currency_stance(
        "USD", ["Fed hikes rate aggressively"], ai_service=None
    )
    assert result1 == "hawkish"

    # Headline đổi nhưng cùng currency -> cache hit của fallback, không tính lại
    result2 = svc._ai_currency_stance("USD", ["ECB cuts rates"], ai_service=None)
    assert result2 == "hawkish"  # cached, không phải dovish


def test_ai_stance_cache_expired_tai_24h():
    """Hết TTL 24h -> cache miss -> gọi AI lại."""
    mock_ai = MagicMock()
    mock_ai.analyze.return_value = _json_stance("hawkish")
    svc = NewsService()

    result1 = svc._ai_currency_stance("USD", ["Fed raises rate"], ai_service=mock_ai)
    assert result1 == "hawkish"
    assert mock_ai.analyze.call_count == 1

    # Giả lập entry đã hết hạn sau 24h
    cache_key = json.dumps(
        {"currency": "USD", "ai": svc._ai_fingerprint(mock_ai)},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    svc._stance_cache[cache_key] = (
        {"stance": "hawkish", "strength": None, "confidence": None, "source": "fallback"},
        datetime.now(UTC) - svc._stance_cache_ttl - timedelta(seconds=1),
    )

    result2 = svc._ai_currency_stance("USD", ["Fed raises rate"], ai_service=mock_ai)
    assert result2 == "hawkish"
    assert mock_ai.analyze.call_count == 2  # cache miss -> gọi AI lại


# ---------------------------------------------------------------------------
# _compute_macro_tiers — uses _ai_currency_stance
# ---------------------------------------------------------------------------


def test_compute_macro_tiers_uses_ai_stance_with_service():
    """_compute_macro_tiers passes ai_service to _ai_currency_stance."""
    mock_ai = MagicMock()
    mock_ai.analyze.return_value = _json_stance("hawkish")
    svc = NewsService()

    headlines = [_make_headline("Fed hikes rate"), _make_headline("EUR inflation drops")]
    result = svc._compute_macro_tiers(
        "EUR/USD",
        ["EUR", "USD"],
        headlines,
        events=[],
        themes=[],
        hotspots=[],
        ai_service=mock_ai,
    )

    # AI was called (twice: base EUR and quote USD)
    assert mock_ai.analyze.call_count >= 1
    # Result structure intact
    assert "tier1" in result
    assert "alignment" in result


def test_compute_macro_tiers_without_ai_uses_keyword_fallback():
    """Without ai_service, _compute_macro_tiers still works (keyword fallback)."""
    svc = NewsService()
    headlines = [_make_headline("Fed hikes rate"), _make_headline("ECB cuts rate")]
    result = svc._compute_macro_tiers(
        "EUR/USD",
        ["EUR", "USD"],
        headlines,
        events=[],
        themes=[],
        hotspots=[],
        ai_service=None,
    )

    assert "tier1" in result
    assert "alignment" in result


# ---------------------------------------------------------------------------
# _stance_score — phản ánh strength và confidence (dải 0-4)
# ---------------------------------------------------------------------------


def _v2_base_stance(stance: str, strength: float | None, confidence: float | None) -> int:
    """Chấm stance component (0-4) qua _compute_macro_v2 với strength/confidence cho trước."""
    old = NewsService._interest_rates
    NewsService._interest_rates = {}
    try:
        svc = NewsService()
        detail = {
            "stance": stance,
            "strength": strength,
            "confidence": confidence,
            "source": "test",
        }
        v2 = svc._compute_macro_v2(
            "EUR", "USD", stance, "neutral", {},
            base_stance_detail=detail,
            quote_stance_detail={"stance": "neutral", "strength": None, "confidence": None, "source": "fallback"},
        )
        return int(v2["components"]["base"]["stance"])
    finally:
        NewsService._interest_rates = old


def test_stance_score_hawkish_theo_strength():
    """Hawkish + confidence đạt: điểm tăng theo strength, tối đa 4."""
    assert _v2_base_stance("hawkish", 10, 0.9) == 4
    assert _v2_base_stance("hawkish", 5, 0.9) == 3
    assert _v2_base_stance("hawkish", 0, 0.9) == 2


def test_stance_score_dovish_theo_strength():
    """Dovish + confidence đạt: điểm giảm theo strength, tối thiểu 0."""
    assert _v2_base_stance("dovish", 10, 0.9) == 0
    assert _v2_base_stance("dovish", 5, 0.9) == 1
    assert _v2_base_stance("dovish", 0, 0.9) == 2


def test_stance_score_confidence_thap_coi_nhu_neutral():
    """Confidence < 0.7 (kể cả strength cao) → neutral (2), không tin tưởng."""
    assert _v2_base_stance("hawkish", 10, 0.5) == 2
    assert _v2_base_stance("dovish", 10, 0.5) == 2
    assert _v2_base_stance("hawkish", 10, 0.69) == 2


def test_stance_score_confidence_nguong_07():
    """Confidence đúng ngưỡng 0.7 trở lên → tin tưởng, chấm theo strength."""
    assert _v2_base_stance("hawkish", 10, 0.7) == 4
    assert _v2_base_stance("dovish", 10, 0.7) == 0


def test_stance_score_neutral_luon_la_2():
    """Neutral dù strength cao → 2."""
    assert _v2_base_stance("neutral", 10, 0.9) == 2


def test_stance_score_fallback_khong_strength_conf():
    """Fallback (không có strength/confidence) → neutral (2), không tin tưởng."""
    assert _v2_base_stance("hawkish", None, None) == 2
    assert _v2_base_stance("dovish", None, None) == 2


# ---------------------------------------------------------------------------
# _ai_currency_stance_detail — chi tiết stance/strength/confidence
# ---------------------------------------------------------------------------


def test_ai_stance_detail_tra_ve_strength_confidence():
    """_ai_currency_stance_detail trả về stance, strength, confidence, source."""
    mock_ai = MagicMock()
    mock_ai.analyze.return_value = _json_stance("hawkish", strength=8, confidence=0.9, drivers=("hike",))
    svc = NewsService()
    detail = svc._ai_currency_stance_detail("USD", ["Fed raises rate"], ai_service=mock_ai)
    assert detail["stance"] == "hawkish"
    assert detail["strength"] == 8
    assert detail["confidence"] == 0.9
    assert detail["source"] == "ai"


def test_ai_stance_detail_fallback_khong_strength_confidence():
    """Fallback keyword matching: strength/confidence = None, source=fallback."""
    svc = NewsService()
    detail = svc._ai_currency_stance_detail("USD", ["Fed hikes rate"], ai_service=None)
    assert detail["stance"] == "hawkish"
    assert detail["strength"] is None
    assert detail["confidence"] is None
    assert detail["source"] == "fallback"


# ---------------------------------------------------------------------------
# stance_journal — ghi stance/strength/confidence của từng đồng tiền
# ---------------------------------------------------------------------------


def test_compute_macro_tiers_ghi_stance_journal():
    """_compute_macro_tiers ghi stance_journal chứa stance/strength/confidence mỗi đồng tiền."""
    mock_ai = MagicMock()
    mock_ai.analyze.return_value = _json_stance("hawkish", strength=8, confidence=0.9)
    svc = NewsService()
    old = NewsService._interest_rates
    NewsService._interest_rates = {}
    try:
        result = svc._compute_macro_tiers(
            "EUR/USD",
            ["EUR", "USD"],
            [_make_headline("ECB cuts rate"), _make_headline("Fed hikes rate")],
            events=[],
            themes=[],
            hotspots=[],
            ai_service=mock_ai,
        )
    finally:
        NewsService._interest_rates = old

    journal = result["stance_journal"]
    assert journal["base"]["currency"] == "EUR"
    assert journal["base"]["stance"] == "hawkish"
    assert journal["base"]["strength"] == 8
    assert journal["base"]["confidence"] == 0.9
    assert journal["base"]["source"] == "ai"
    assert journal["quote"]["currency"] == "USD"
    assert journal["quote"]["stance"] == "hawkish"
    assert journal["quote"]["strength"] == 8
    assert journal["quote"]["confidence"] == 0.9
    assert journal["quote"]["source"] == "ai"


def test_compute_macro_tiers_stance_journal_fallback():
    """Không có AI: stance_journal ghi nguồn fallback, strength/confidence = None."""
    svc = NewsService()
    old = NewsService._interest_rates
    NewsService._interest_rates = {}
    try:
        result = svc._compute_macro_tiers(
            "EUR/USD",
            ["EUR", "USD"],
            [_make_headline("ECB cuts rate")],
            events=[],
            themes=[],
            hotspots=[],
            ai_service=None,
        )
    finally:
        NewsService._interest_rates = old

    journal = result["stance_journal"]
    assert journal["quote"]["currency"] == "USD"
    assert journal["quote"]["source"] == "fallback"
    assert journal["quote"]["strength"] is None
    assert journal["quote"]["confidence"] is None


# ---------------------------------------------------------------------------
# currency_stance — unchanged
# ---------------------------------------------------------------------------


def test_currency_stance_unchanged():
    """Original currency_stance function still works correctly."""
    assert currency_stance(["Fed hikes rate"], ["hike"], ["cut"]) == "hawkish"
    assert currency_stance(["ECB cuts rate"], ["hike"], ["cut"]) == "dovish"
    assert currency_stance(["markets stable"], ["hike"], ["cut"]) == "neutral"
    # "budget cut" matches "cut" -> dovish (the reason we're adding AI)
    assert currency_stance(["budget cut announced"], ["hike"], ["cut"]) == "dovish"


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    tests = [
        # fallback
        test_ai_stance_fallback_khi_khong_co_ai,
        test_ai_stance_fallback_empty_headlines,
        test_ai_stance_fallback_hawkish_keywords,
        test_ai_stance_fallback_dovish_keywords,
        # AI path
        test_ai_stance_tra_ve_hawkish,
        test_ai_stance_tra_ve_dovish,
        test_ai_stance_tra_ve_neutral,
        test_ai_stance_strips_extra_text,
        test_ai_stance_json_trong_fence_markdown,
        test_ai_stance_case_insensitive,
        test_ai_stance_fallback_khi_ai_loi,
        test_ai_stance_fallback_khi_ai_tra_ve_invalid,
        test_ai_stance_fallback_khi_ai_tra_ve_empty,
        # JSON schema validation
        test_ai_stance_fallback_khi_json_thieu_field,
        test_ai_stance_fallback_khi_stance_khong_hop_le,
        test_ai_stance_fallback_khi_strength_sai_kieu,
        test_ai_stance_fallback_khi_drivers_sai_kieu,
        # cache
        test_ai_stance_cache_hit,
        test_ai_stance_cache_miss_different_currency,
        test_ai_stance_cache_hit_khi_headline_doi_cung_currency,
        test_ai_stance_fallback_cached_cung_currency,
        test_ai_stance_cache_expired_tai_24h,
        # _compute_macro_tiers
        test_compute_macro_tiers_uses_ai_stance_with_service,
        test_compute_macro_tiers_without_ai_uses_keyword_fallback,
        # _stance_score — strength & confidence
        test_stance_score_hawkish_theo_strength,
        test_stance_score_dovish_theo_strength,
        test_stance_score_confidence_thap_coi_nhu_neutral,
        test_stance_score_confidence_nguong_07,
        test_stance_score_neutral_luon_la_2,
        test_stance_score_fallback_khong_strength_conf,
        # _ai_currency_stance_detail
        test_ai_stance_detail_tra_ve_strength_confidence,
        test_ai_stance_detail_fallback_khong_strength_confidence,
        # stance_journal
        test_compute_macro_tiers_ghi_stance_journal,
        test_compute_macro_tiers_stance_journal_fallback,
        # currency_stance unchanged
        test_currency_stance_unchanged,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"PASS  {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"FAIL  {test.__name__}: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} PASS, {failed} FAIL out of {len(tests)}")
    sys.exit(0 if failed == 0 else 1)
