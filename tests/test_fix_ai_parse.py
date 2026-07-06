"""Test fix for BUG #2: _parse_with_ai() falls back to regex when AI
returns reasoning text (> 20 chars).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.news_service import NewsService


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _mock_ai_service(return_value: str):
    """Create a mock AI service that returns the given value."""
    mock = MagicMock()
    mock.analyze.return_value = return_value
    return mock


def _mock_settings(has_key: bool = True):
    """Mock SettingsService to return configured AI."""
    mock_provider = MagicMock()
    mock_provider.provider = "DeepSeek"
    mock_provider.model = "deepseek-v4-pro"
    mock_provider.api_key = "sk-test" if has_key else ""

    mock_ai_settings = MagicMock()
    mock_ai_settings.active_provider.return_value = mock_provider if has_key else None

    mock_settings = MagicMock()
    mock_settings.ai = mock_ai_settings

    mock_service = MagicMock()
    mock_service.load.return_value = mock_settings
    return mock_service


# ---------------------------------------------------------------------------
# _parse_with_ai — short valid responses
# ---------------------------------------------------------------------------


def test_parse_short_numeric_value():
    """AI returns short numeric -> used directly."""
    svc = NewsService()
    with patch("services.news_service.SettingsService", return_value=_mock_settings()):
        with patch("services.news_service.AIService", return_value=_mock_ai_service("0.1%")):
            result = svc._parse_with_ai("search results...", "CPI m/m", "0.2%", "0.1%")
    assert result == "0.1%"


def test_parse_short_with_unit_k():
    """AI returns '122K' -> used directly."""
    svc = NewsService()
    with patch("services.news_service.SettingsService", return_value=_mock_settings()):
        with patch("services.news_service.AIService", return_value=_mock_ai_service("122K")):
            result = svc._parse_with_ai("NFP 122K jobs added", "NFP", "150K", "120K")
    assert result == "122K"


def test_parse_negative_number():
    """AI returns '-2.5B' -> used directly."""
    svc = NewsService()
    with patch("services.news_service.SettingsService", return_value=_mock_settings()):
        with patch("services.news_service.AIService", return_value=_mock_ai_service("-2.5B")):
            result = svc._parse_with_ai("trade balance -2.5B", "Trade Balance", "-2.0B", "-1.8B")
    assert result == "-2.5B"


def test_parse_none_response():
    """AI returns 'NONE' -> empty string."""
    svc = NewsService()
    with patch("services.news_service.SettingsService", return_value=_mock_settings()):
        with patch("services.news_service.AIService", return_value=_mock_ai_service("NONE")):
            result = svc._parse_with_ai("no data available", "Holiday", "", "")
    assert result == ""


# ---------------------------------------------------------------------------
# _parse_with_ai — long response -> regex fallback
# ---------------------------------------------------------------------------


def test_parse_long_reasoning_falls_back_to_regex():
    """AI returns long reasoning (>20 chars) -> regex extracts number."""
    long_response = (
        "We are asked: Extract actual economic data value from search results. "
        "Event: ISM Manufacturing PMI. The search results mention ISM Manufacturing PMI "
        "was 48.5 for June. The actual value is 48.5."
    )
    svc = NewsService()
    with patch("services.news_service.SettingsService", return_value=_mock_settings()):
        with patch("services.news_service.AIService", return_value=_mock_ai_service(long_response)):
            result = svc._parse_with_ai(
                "ISM Manufacturing PMI came in at 48.5% missing expectations",
                "ISM Manufacturing PMI", "49.5", "48.7",
            )
    # regex should find "48.5%" from the search text
    assert result == "48.5%"


def test_parse_long_reasoning_no_number_in_text():
    """AI returns long reasoning, no number in text -> empty."""
    svc = NewsService()
    with patch("services.news_service.SettingsService", return_value=_mock_settings()):
        with patch("services.news_service.AIService", return_value=_mock_ai_service("very long reasoning about market conditions and outlook")):
            result = svc._parse_with_ai(
                "The FOMC meeting concluded with no change to rates.",
                "FOMC Meeting", "", "",
            )
    assert result == ""


def test_parse_exactly_20_chars_uses_ai():
    """AI returns exactly 20 chars -> used as AI result (not fallback)."""
    valid_20 = "12345678901234567890"  # 20 chars
    svc = NewsService()
    with patch("services.news_service.SettingsService", return_value=_mock_settings()):
        with patch("services.news_service.AIService", return_value=_mock_ai_service(valid_20)):
            result = svc._parse_with_ai("search text", "Event", "", "")
    assert result == valid_20


# ---------------------------------------------------------------------------
# _parse_with_ai — no AI fallback
# ---------------------------------------------------------------------------


def test_parse_no_ai_key_uses_regex():
    """No AI API key -> uses regex directly."""
    svc = NewsService()
    with patch("services.news_service.SettingsService", return_value=_mock_settings(has_key=False)):
        result = svc._parse_with_ai(
            "US GDP grew 2.8% in Q2 beating expectations",
            "GDP q/q", "2.5%", "2.3%",
        )
    assert result == "2.8%"


def test_parse_empty_text_returns_empty():
    """Empty search text -> returns empty."""
    svc = NewsService()
    with patch("services.news_service.SettingsService", return_value=_mock_settings(has_key=False)):
        result = svc._parse_with_ai("", "Event", "", "")
    assert result == ""


# ---------------------------------------------------------------------------
# _parse_fallback_regex — edge cases
# ---------------------------------------------------------------------------


def test_regex_extracts_percent():
    """Regex extracts percentage values."""
    assert NewsService._parse_fallback_regex("GDP was 3.2% in Q1") == "3.2%"
    assert NewsService._parse_fallback_regex("inflation at 2.1% y/y") == "2.1%"


def test_regex_extracts_million():
    """Regex extracts million values."""
    assert NewsService._parse_fallback_regex("payrolls +187M") == "187M"
    assert NewsService._parse_fallback_regex("256M jobs") == "256M"


def test_regex_extracts_thousand():
    """Regex extracts thousand values."""
    assert NewsService._parse_fallback_regex("122K jobs added") == "122K"


def test_regex_extracts_billion():
    """Regex extracts billion values."""
    assert NewsService._parse_fallback_regex("trade deficit -2.5B widening") == "2.5B"


def test_regex_no_match_returns_empty():
    """No numeric pattern -> empty."""
    assert NewsService._parse_fallback_regex("The Fed held rates steady") == ""
    assert NewsService._parse_fallback_regex("") == ""


def test_regex_html_stripped():
    """HTML tags are stripped before regex."""
    assert NewsService._parse_fallback_regex("GDP <strong>2.8%</strong> growth") == "2.8%"


# ---------------------------------------------------------------------------
# _parse_with_ai — exception handling
# ---------------------------------------------------------------------------


def test_parse_ai_exception_returns_empty():
    """AI raises exception -> returns empty (not crash)."""
    mock_ai = MagicMock()
    mock_ai.analyze.side_effect = RuntimeError("connection timeout")

    svc = NewsService()
    with patch("services.news_service.SettingsService", return_value=_mock_settings()):
        with patch("services.news_service.AIService", return_value=mock_ai):
            result = svc._parse_with_ai("search text", "Event", "", "")
    assert result == ""


def test_parse_settings_exception_returns_empty():
    """SettingsService raises -> returns empty."""
    mock_svc = MagicMock()
    mock_svc.load.side_effect = RuntimeError("settings corrupt")

    svc = NewsService()
    with patch("services.news_service.SettingsService", return_value=mock_svc):
        result = svc._parse_with_ai("search text 2.5% growth", "Event", "", "")
    assert result == ""


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    tests = [
        test_parse_short_numeric_value,
        test_parse_short_with_unit_k,
        test_parse_negative_number,
        test_parse_none_response,
        test_parse_long_reasoning_falls_back_to_regex,
        test_parse_long_reasoning_no_number_in_text,
        test_parse_exactly_20_chars_uses_ai,
        test_parse_no_ai_key_uses_regex,
        test_parse_empty_text_returns_empty,
        test_regex_extracts_percent,
        test_regex_extracts_million,
        test_regex_extracts_thousand,
        test_regex_extracts_billion,
        test_regex_no_match_returns_empty,
        test_regex_html_stripped,
        test_parse_ai_exception_returns_empty,
        test_parse_settings_exception_returns_empty,
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
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} PASS, {failed} FAIL out of {len(tests)}")
    sys.exit(0 if failed == 0 else 1)
