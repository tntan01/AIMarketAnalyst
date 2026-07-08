"""Test suite for Group B speed optimizations.

Covers:
  B1 — Streaming AI response via SSE
  B2 — max_tokens reduced from 4000 to 2500
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

sys = __import__("sys")
sys.path.insert(0, ".")

# ---------------------------------------------------------------------------
# B1 — SSE parser (reusable module)
# ---------------------------------------------------------------------------


class TestSSEParser:
    def test_yields_content_chunks(self):
        from services.sse_parser import iter_chat_completion_chunks

        lines = [
            b'data: {"choices":[{"delta":{"content":"Hello"}}]}',
            b"",
            b'data: {"choices":[{"delta":{"content":" World"}}]}',
            b"",
            b"data: [DONE]",
            b"",
        ]
        mock_response = MagicMock()
        mock_response.iter_lines.return_value = (
            line.decode() if isinstance(line, bytes) else line for line in lines
        )

        chunks = list(iter_chat_completion_chunks(mock_response))
        assert chunks == ["Hello", " World"], (
            f"B1 FAILED: expected ['Hello', ' World'], got {chunks}"
        )

    def test_reasoning_content_key(self):
        from services.sse_parser import iter_chat_completion_chunks

        lines = [
            b'data: {"choices":[{"delta":{"reasoning_content":"thinking..."}}]}',
            b"data: [DONE]",
        ]
        mock_response = MagicMock()
        mock_response.iter_lines.return_value = (
            line.decode() for line in lines
        )

        chunks = list(
            iter_chat_completion_chunks(mock_response, content_key="reasoning_content")
        )
        assert chunks == ["thinking..."], (
            f"B1 FAILED: expected ['thinking...'], got {chunks}"
        )

    def test_empty_lines_skipped(self):
        from services.sse_parser import iter_chat_completion_chunks

        lines = [
            b"",
            b"",
            b'data: {"choices":[{"delta":{"content":"A"}}]}',
            b"",
            b"data: [DONE]",
        ]
        mock_response = MagicMock()
        mock_response.iter_lines.return_value = (
            line.decode() for line in lines
        )

        chunks = list(iter_chat_completion_chunks(mock_response))
        assert chunks == ["A"], (
            f"B1 FAILED: expected ['A'], got {chunks}"
        )

    def test_non_data_lines_skipped(self):
        from services.sse_parser import iter_chat_completion_chunks

        lines = [
            b":ok\n",
            b'data: {"choices":[{"delta":{"content":"X"}}]}',
            b"data: [DONE]",
        ]
        mock_response = MagicMock()
        mock_response.iter_lines.return_value = (
            line.decode() for line in lines
        )

        chunks = list(iter_chat_completion_chunks(mock_response))
        assert chunks == ["X"], (
            f"B1 FAILED: expected ['X'], got {chunks}"
        )

    def test_no_choices_returns_nothing(self):
        from services.sse_parser import iter_chat_completion_chunks

        lines = [
            b'data: {"choices":[]}',
            b"data: [DONE]",
        ]
        mock_response = MagicMock()
        mock_response.iter_lines.return_value = (
            line.decode() for line in lines
        )

        chunks = list(iter_chat_completion_chunks(mock_response))
        assert chunks == [], (
            f"B1 FAILED: expected [], got {chunks}"
        )

    def test_invalid_json_skipped(self):
        from services.sse_parser import iter_chat_completion_chunks

        lines = [
            b"data: not-json",
            b'data: {"choices":[{"delta":{"content":"valid"}}]}',
            b"data: [DONE]",
        ]
        mock_response = MagicMock()
        mock_response.iter_lines.return_value = (
            line.decode() for line in lines
        )

        chunks = list(iter_chat_completion_chunks(mock_response))
        assert chunks == ["valid"], (
            f"B1 FAILED: expected ['valid'], got {chunks}"
        )

    def test_no_done_marker_ends_naturally(self):
        from services.sse_parser import iter_chat_completion_chunks

        lines = [
            b'data: {"choices":[{"delta":{"content":"one"}}]}',
            b'data: {"choices":[{"delta":{"content":"two"}}]}',
        ]
        mock_response = MagicMock()
        mock_response.iter_lines.return_value = (
            line.decode() for line in lines
        )

        chunks = list(iter_chat_completion_chunks(mock_response))
        assert chunks == ["one", "two"], (
            f"B1 FAILED: expected ['one', 'two'], got {chunks}"
        )


# ---------------------------------------------------------------------------
# B1 — AIService.analyze_stream dispatcher
# ---------------------------------------------------------------------------


class TestAnalyzeStreamDispatch:
    def test_deepseek_routes_to_stream(self):
        from services.ai_service import AIService, AIProviderConfig

        config = AIProviderConfig(
            provider="deepseek",
            model="deepseek-v4-flash",
            api_key="sk-test",
        )
        ai = AIService(config)

        with patch.object(ai, "_chat_completion_stream") as mock_stream:
            mock_stream.return_value = iter(["chunk1", "chunk2"])
            chunks = list(ai.analyze_stream("test prompt", max_tokens=500))
            assert chunks == ["chunk1", "chunk2"]
            # DeepSeek v4 models have a 4000 token floor (Proposal 3)
            mock_stream.assert_called_once_with(
                "https://api.deepseek.com/chat/completions", "test prompt", 4000
            )

    def test_deepseek_invalid_model_raises(self):
        from services.ai_service import AIService, AIProviderConfig

        config = AIProviderConfig(
            provider="deepseek",
            model="gpt-4",  # not in DEEPSEEK_MODELS
            api_key="sk-test",
        )
        ai = AIService(config)

        with pytest.raises(RuntimeError, match="Model DeepSeek không hợp lệ"):
            list(ai.analyze_stream("test"))

    def test_openai_falls_back_to_non_streaming(self):
        from services.ai_service import AIService, AIProviderConfig

        config = AIProviderConfig(
            provider="openai",
            model="gpt-4o",
            api_key="sk-test",
        )
        ai = AIService(config)

        with patch.object(ai, "_openai_response", return_value="fallback text"):
            chunks = list(ai.analyze_stream("test"))
            assert chunks == ["fallback text"]

    def test_anthropic_falls_back(self):
        from services.ai_service import AIService, AIProviderConfig

        config = AIProviderConfig(
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            api_key="sk-test",
        )
        ai = AIService(config)

        with patch.object(ai, "_anthropic_message", return_value="claude response"):
            chunks = list(ai.analyze_stream("test"))
            assert chunks == ["claude response"]

    def test_gemini_falls_back(self):
        from services.ai_service import AIService, AIProviderConfig

        config = AIProviderConfig(
            provider="gemini",
            model="gemini-2.5-flash",
            api_key="sk-test",
        )
        ai = AIService(config)

        with patch.object(ai, "_gemini_generate_content", return_value="gemini text"):
            chunks = list(ai.analyze_stream("test"))
            assert chunks == ["gemini text"]

    def test_default_routes_to_chat_completion_stream(self):
        from services.ai_service import AIService, AIProviderConfig

        config = AIProviderConfig(
            provider="other",
            model="custom-model",
            api_key="sk-test",
        )
        ai = AIService(config)

        with patch.object(ai, "_chat_completion_stream") as mock_stream:
            mock_stream.return_value = iter(["a", "b"])
            chunks = list(ai.analyze_stream("prompt", max_tokens=100))
            assert chunks == ["a", "b"]
            mock_stream.assert_called_once_with(
                "https://api.openai.com/v1/chat/completions", "prompt", 100
            )


# ---------------------------------------------------------------------------
# B1 — _chat_completion_stream payload and error handling
# ---------------------------------------------------------------------------


class TestChatCompletionStream:
    def test_payload_includes_stream_true(self):
        from services.ai_service import AIService, AIProviderConfig
        from services.sse_parser import iter_chat_completion_chunks

        config = AIProviderConfig(
            provider="deepseek",
            model="deepseek-v4-flash",
            api_key="sk-test",
        )
        ai = AIService(config)

        mock_response = MagicMock()
        mock_response.status_code = 200

        captured_payload = {}

        def fake_post(url, *, json, headers, stream, timeout):
            nonlocal captured_payload
            captured_payload = json
            return mock_response

        with patch("services.ai_service.requests.post", side_effect=fake_post):
            with patch.object(
                ai, "_chat_completion_stream",
                wraps=ai._chat_completion_stream,
            ):
                pass

        with patch("services.ai_service.requests.post", side_effect=fake_post):
            with patch(
                "services.sse_parser.iter_chat_completion_chunks",
                return_value=iter(["ok"]),
            ):
                chunks = list(ai._chat_completion_stream(
                    "https://api.deepseek.com/chat/completions", "test", 500
                ))

        assert captured_payload["stream"] is True, (
            f"B1 FAILED: stream not True in payload: {captured_payload}"
        )
        assert captured_payload["max_tokens"] == 500
        assert captured_payload["model"] == "deepseek-v4-flash"
        assert captured_payload["temperature"] == 0.2
        assert chunks == ["ok"]

    def test_http_error_raises(self):
        from services.ai_service import AIService, AIProviderConfig

        config = AIProviderConfig(
            provider="deepseek",
            model="deepseek-v4-flash",
            api_key="sk-test",
        )
        ai = AIService(config)

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch("services.ai_service.requests.post", return_value=mock_response):
            with pytest.raises(RuntimeError, match="AI API lỗi HTTP 500"):
                list(ai._chat_completion_stream(
                    "https://api.deepseek.com/chat/completions", "test"
                ))

    def test_connection_error_raises(self):
        from services.ai_service import AIService, AIProviderConfig
        import requests as req

        config = AIProviderConfig(
            provider="deepseek",
            model="deepseek-v4-flash",
            api_key="sk-test",
        )
        ai = AIService(config)

        with patch(
            "services.ai_service.requests.post",
            side_effect=req.ConnectionError("timeout"),
        ):
            with pytest.raises(RuntimeError, match="Không kết nối được AI API"):
                list(ai._chat_completion_stream(
                    "https://api.deepseek.com/chat/completions", "test"
                ))


# ---------------------------------------------------------------------------
# B2 — max_tokens reduced from 4000 to 2500
# ---------------------------------------------------------------------------


class TestB2MaxTokens:
    def test_max_tokens_is_2500_in_dashboard(self):
        import inspect
        from ui.screens.dashboard_screen import DashboardScreen

        source = inspect.getsource(DashboardScreen._show_market_help)
        assert "max_tokens=2500" in source, (
            "B2 FAILED: max_tokens=2500 not found in _show_market_help source"
        )
        assert "max_tokens=4000" not in source, (
            "B2 FAILED: old max_tokens=4000 still present in _show_market_help"
        )

    def test_analyze_stream_accepts_custom_max_tokens(self):
        from services.ai_service import AIService, AIProviderConfig

        config = AIProviderConfig(
            provider="deepseek",
            model="deepseek-v4-flash",
            api_key="sk-test",
        )
        ai = AIService(config)

        with patch.object(ai, "_chat_completion_stream") as mock_stream:
            mock_stream.return_value = iter(["ok"])
            list(ai.analyze_stream("prompt", max_tokens=2500))
            # DeepSeek v4 models floor to 4000 (Proposal 3)
            assert mock_stream.call_args[0][2] == 4000, (
                f"B2 FAILED: max_tokens not passed correctly, "
                f"got {mock_stream.call_args[0][2]}"
            )


# ---------------------------------------------------------------------------
# Integration — streaming with sse_parser + AIService
# ---------------------------------------------------------------------------


class TestB1Integration:
    def test_full_streaming_pipeline(self):
        """Simulate a full streaming pipeline: AI returns SSE chunks,
        sse_parser extracts them, analyze_stream yields them."""
        from services.ai_service import AIService, AIProviderConfig

        config = AIProviderConfig(
            provider="deepseek",
            model="deepseek-v4-flash",
            api_key="sk-test",
        )
        ai = AIService(config)

        # Simulate SSE response
        sse_lines = [
            b'data: {"choices":[{"delta":{"content":"## Phan tich"}}]}',
            b"",
            b'data: {"choices":[{"delta":{"content":"\\n\\n### DXY"}}]}',
            b"",
            b"data: [DONE]",
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = (
            line.decode() for line in sse_lines
        )

        with patch("services.ai_service.requests.post", return_value=mock_response):
            chunks = list(ai.analyze_stream("prompt", max_tokens=2500))

        combined = "".join(chunks)
        assert "## Phan tich" in combined
        assert "### DXY" in combined
        assert len(chunks) == 2


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
