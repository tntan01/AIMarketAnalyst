"""Anthropic provider adapter — Messages API."""

from __future__ import annotations

from services.ai.provider_adapter import BaseProviderAdapter
from services.ai.provider_catalog import ProviderCapability, ProviderInfo, provider_catalog

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class AnthropicAdapter(BaseProviderAdapter):
    @staticmethod
    def provider_name() -> str:
        return "anthropic"

    def generate(self, prompt: str, model: str, api_key: str, max_tokens: int) -> str:
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "system": self.SYSTEM_PROMPT_TEXT,
            "messages": [{"role": "user", "content": prompt}],
        }
        data = self._post_json(
            ANTHROPIC_MESSAGES_URL,
            payload,
            {
                "x-api-key": api_key,
                "anthropic-version": ANTHROPIC_VERSION,
            },
        )
        texts = [
            item.get("text", "")
            for item in data.get("content", [])
            if item.get("type") == "text"
        ]
        if texts:
            return "\n".join(texts).strip()
        raise RuntimeError("AI không trả về nội dung phân tích.")


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

provider_catalog.register(
    ProviderInfo(
        name="anthropic",
        display_name="Anthropic",
        capabilities=(
            ProviderCapability.CHAT
            | ProviderCapability.SYSTEM_PROMPT
            | ProviderCapability.VISION
            | ProviderCapability.TOOL_CALLING
        ),
        default_models=("claude-3-5-sonnet-latest", "claude-3-5-haiku-latest"),
        locked_models=False,
        adapter_class=AnthropicAdapter,
    )
)
