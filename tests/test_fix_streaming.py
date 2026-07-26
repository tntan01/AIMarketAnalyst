"""Test suite for Proposal 3 — reasoning model token floor + SSE fallback.

Covers:
  F1 — _effective_max_tokens floors reasoning models at 4000
  F2 — SSE parser yields reasoning_content when content is empty
  F3 — Integration: streaming + small max_tokens still produces content
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, ".")

# ---------------------------------------------------------------------------
# F1 — _effective_max_tokens
# ---------------------------------------------------------------------------


class TestEffectiveMaxTokens:
    def test_deepseek_v4_pro_floor(self):
        from services.ai_service import AIService, AIProviderConfig

        config = AIProviderConfig(provider="deepseek", model="deepseek-v4-pro", api_key="sk-")
        ai = AIService(config)
        assert ai._effective_max_tokens(100) == 4000
        assert ai._effective_max_tokens(2500) == 4000
        assert ai._effective_max_tokens(4000) == 4000
        assert ai._effective_max_tokens(8000) == 8000

    def test_deepseek_v4_flash_floor(self):
        from services.ai_service import AIService, AIProviderConfig

        config = AIProviderConfig(provider="deepseek", model="deepseek-v4-flash", api_key="sk-")
        ai = AIService(config)
        assert ai._effective_max_tokens(2500) == 4000

    def test_non_reasoning_model_passthrough(self):
        from services.ai_service import AIService, AIProviderConfig

        config = AIProviderConfig(provider="openai", model="gpt-4o", api_key="sk-")
        ai = AIService(config)
        assert ai._effective_max_tokens(100) == 100
        assert ai._effective_max_tokens(2500) == 2500

    def test_unknown_model_passthrough(self):
        from services.ai_service import AIService, AIProviderConfig

        # Unknown providers now raise early — this is correct behavior
        with pytest.raises(RuntimeError, match="không được hỗ trợ"):
            AIService(AIProviderConfig(provider="other", model="custom-model", api_key="sk-"))

    def test_analyze_stream_uses_effective_tokens(self):
        """DeepSeekAdapter floors max_tokens for reasoning models."""
        from services.ai.providers.deepseek_adapter import DeepSeekAdapter

        adapter = DeepSeekAdapter()
        # Mock _chat_completion_payload to capture the effective max_tokens
        with patch.object(adapter, "_chat_completion_payload") as mock_payload:
            mock_payload.return_value = {}
            with patch.object(adapter, "_post_json", return_value={
                "choices": [{"message": {"content": "ok"}}]
            }):
                adapter.generate("test", "deepseek-v4-pro", "sk-", 2500)
                _, _, effective = mock_payload.call_args[0]
                assert effective == 4000, (
                    f"F1 FAILED: expected effective=4000, got {effective}"
                )

    def test_non_deepseek_uses_requested_tokens(self):
        from services.ai_service import AIService, AIProviderConfig
        from unittest.mock import patch

        config = AIProviderConfig(provider="anthropic", model="claude-sonnet-4-20250514", api_key="sk-")
        ai = AIService(config)

        # Mock adapter's generate_stream (moved from AIService._anthropic_message)
        with patch.object(ai._adapter, "generate_stream", return_value=iter(["ok"])):
            list(ai.analyze_stream("prompt", max_tokens=777))


# ---------------------------------------------------------------------------
# F2 — SSE parser never exposes private reasoning_content
# ---------------------------------------------------------------------------


class TestSSEParserReasoningFallback:
    def test_yields_content_when_present(self):
        from services.sse_parser import iter_chat_completion_chunks

        lines = [
            b'data: {"choices":[{"delta":{"content":"Hello"}}]}',
            b"data: [DONE]",
        ]
        mock = MagicMock()
        mock.iter_lines.return_value = (l.decode() for l in lines)
        assert list(iter_chat_completion_chunks(mock)) == ["Hello"]

    def test_skips_reasoning_when_content_empty(self):
        from services.sse_parser import iter_chat_completion_chunks

        lines = [
            b'data: {"choices":[{"delta":{"content":null,"reasoning_content":"thinking step 1"}}]}',
            b'data: {"choices":[{"delta":{"content":null,"reasoning_content":"thinking step 2"}}]}',
            b"data: [DONE]",
        ]
        mock = MagicMock()
        mock.iter_lines.return_value = (l.decode() for l in lines)
        chunks = list(iter_chat_completion_chunks(mock))
        assert chunks == []

    def test_prefers_content_over_reasoning(self):
        from services.sse_parser import iter_chat_completion_chunks

        lines = [
            b'data: {"choices":[{"delta":{"content":"actual","reasoning_content":"think"}}]}',
            b"data: [DONE]",
        ]
        mock = MagicMock()
        mock.iter_lines.return_value = (l.decode() for l in lines)
        chunks = list(iter_chat_completion_chunks(mock))
        assert chunks == ["actual"], (
            f"F2 FAILED: should prefer content, got {chunks}"
        )

    def test_mixed_reasoning_then_content(self):
        from services.sse_parser import iter_chat_completion_chunks

        lines = [
            # Reasoning phase
            b'data: {"choices":[{"delta":{"content":null,"reasoning_content":"We are asked"}}]}',
            b'data: {"choices":[{"delta":{"content":null,"reasoning_content":" to analyze"}}]}',
            # Content phase
            b'data: {"choices":[{"delta":{"content":"## Phan tich"}}]}',
            b'data: {"choices":[{"delta":{"content":"\\n\\nDXY..."}}]}',
            b"data: [DONE]",
        ]
        mock = MagicMock()
        mock.iter_lines.return_value = (l.decode() for l in lines)
        chunks = list(iter_chat_completion_chunks(mock))
        assert chunks == ["## Phan tich", "\n\nDXY..."]

    def test_both_empty_yields_nothing(self):
        from services.sse_parser import iter_chat_completion_chunks

        lines = [
            b'data: {"choices":[{"delta":{"role":"assistant"}}]}',
            b"data: [DONE]",
        ]
        mock = MagicMock()
        mock.iter_lines.return_value = (l.decode() for l in lines)
        assert list(iter_chat_completion_chunks(mock)) == []


# ---------------------------------------------------------------------------
# F3 — Integration: small max_tokens + reasoning model still produces content
# ---------------------------------------------------------------------------


class TestF3Integration:
    def test_streaming_pipeline_with_reasoning_model(self):
        """Simulate DeepSeek v4 streaming: reasoning first, then content."""
        from services.sse_parser import iter_chat_completion_chunks

        reasoning_lines = []
        for i in range(5):
            reasoning_lines.append(
                f'data: {{"choices":[{{"delta":{{"content":null,"reasoning_content":"think {i}"}}}}]}}'.encode()
            )
            reasoning_lines.append(b"")

        content_lines = [
            b'data: {"choices":[{"delta":{"content":"## Analysis"}}]}',
            b"",
            b'data: {"choices":[{"delta":{"content":"\\n\\nResult here"}}]}',
            b"",
            b"data: [DONE]",
        ]

        mock = MagicMock()
        mock.iter_lines.return_value = (
            l.decode() for l in (reasoning_lines + content_lines)
        )
        chunks = list(iter_chat_completion_chunks(mock))

        assert not any(chunk.startswith("think ") for chunk in chunks)
        assert "## Analysis" in chunks
        assert len(chunks) == 2

    def test_effective_tokens_applied_in_full_streaming(self):
        """DeepSeekAdapter floors max_tokens for reasoning models in streaming."""
        from services.ai.providers.deepseek_adapter import DeepSeekAdapter

        adapter = DeepSeekAdapter()
        called_tokens = []

        def fake_stream(prompt, model, api_key, max_tokens=1800):
            called_tokens.append(max_tokens)
            return {"choices": [{"message": {"content": "result"}}]}

        with patch.object(adapter, "_chat_completion_payload") as mock_payload:
            mock_payload.return_value = {}
            with patch.object(adapter, "_post_json", side_effect=fake_stream):
                adapter.generate("test", "deepseek-v4-pro", "sk-", 2500)
                _, _, effective = mock_payload.call_args[0]
                assert effective == 4000, (
                    f"F3 FAILED: expected effective=4000, got {effective}"
                )


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
