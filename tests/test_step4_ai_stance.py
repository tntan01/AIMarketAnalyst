"""Test script for Step 4 — AI-powered hawkish/dovish stance analysis.

Usage: python tests/test_step4_ai_stance.py
"""

from __future__ import annotations

from datetime import datetime, UTC
from unittest.mock import MagicMock, patch

from services.news_service import NewsService, currency_stance


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_headline(title: str) -> dict[str, object]:
    return {"title": title}


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
    """AI returns 'hawkish' -> parsed and returned."""
    mock_ai = MagicMock()
    mock_ai.analyze.return_value = "hawkish"
    svc = NewsService()
    result = svc._ai_currency_stance("USD", ["Fed raises rate"], ai_service=mock_ai)
    assert result == "hawkish"


def test_ai_stance_tra_ve_dovish():
    """AI returns 'dovish' -> parsed and returned."""
    mock_ai = MagicMock()
    mock_ai.analyze.return_value = "dovish"
    svc = NewsService()
    result = svc._ai_currency_stance("JPY", ["BOJ maintains easing"], ai_service=mock_ai)
    assert result == "dovish"


def test_ai_stance_tra_ve_neutral():
    """AI returns 'neutral' -> parsed and returned."""
    mock_ai = MagicMock()
    mock_ai.analyze.return_value = "neutral"
    svc = NewsService()
    result = svc._ai_currency_stance("GBP", ["BOE holds steady"], ai_service=mock_ai)
    assert result == "neutral"


def test_ai_stance_strips_extra_text():
    """AI response with extra text -> first word extracted."""
    mock_ai = MagicMock()
    mock_ai.analyze.return_value = "hawkish because inflation is rising"
    svc = NewsService()
    result = svc._ai_currency_stance("USD", ["Fed raises rate"], ai_service=mock_ai)
    assert result == "hawkish"


def test_ai_stance_case_insensitive():
    """AI returns 'HAWKISH' -> normalized to lowercase."""
    mock_ai = MagicMock()
    mock_ai.analyze.return_value = "  HAWKISH  "
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
    """AI returns invalid word -> fallback to keyword matching."""
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
# _ai_currency_stance — cache
# ---------------------------------------------------------------------------


def test_ai_stance_cache_hit():
    """Second call with same headlines returns cached result (no AI call)."""
    mock_ai = MagicMock()
    mock_ai.analyze.return_value = "hawkish"
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
    mock_ai.analyze.return_value = "dovish"
    svc = NewsService()

    svc._ai_currency_stance("USD", ["Fed raises rate"], ai_service=mock_ai)
    assert mock_ai.analyze.call_count == 1

    svc._ai_currency_stance("EUR", ["ECB cuts rate"], ai_service=mock_ai)
    assert mock_ai.analyze.call_count == 2  # different cache key


# ---------------------------------------------------------------------------
# _compute_macro_tiers — uses _ai_currency_stance
# ---------------------------------------------------------------------------


def test_compute_macro_tiers_uses_ai_stance_with_service():
    """_compute_macro_tiers passes ai_service to _ai_currency_stance."""
    mock_ai = MagicMock()
    mock_ai.analyze.return_value = "hawkish"
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
        test_ai_stance_case_insensitive,
        test_ai_stance_fallback_khi_ai_loi,
        test_ai_stance_fallback_khi_ai_tra_ve_invalid,
        test_ai_stance_fallback_khi_ai_tra_ve_empty,
        # cache
        test_ai_stance_cache_hit,
        test_ai_stance_cache_miss_different_currency,
        # _compute_macro_tiers
        test_compute_macro_tiers_uses_ai_stance_with_service,
        test_compute_macro_tiers_without_ai_uses_keyword_fallback,
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
