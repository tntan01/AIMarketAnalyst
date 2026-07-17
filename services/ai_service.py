"""AI Service — thin dispatcher that routes to the correct provider adapter.

All provider-specific logic (endpoints, auth, payload format, response
parsing, streaming, error messages) now lives in individual adapter
classes under :mod:`services.ai.providers`.

:class:`AIService` keeps its **exact same public API** for backward
compatibility.  Internally it delegates to the adapter obtained from
:data:`services.ai.provider_catalog.provider_catalog`.
"""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from typing import Any

from services.ai import provider_catalog


@dataclass(frozen=True, slots=True)
class AIProviderConfig:
    """Minimal config needed to call an AI provider (unchanged public API)."""
    provider: str
    model: str
    api_key: str


class AIService:
    """Unified entry point for AI text generation.

    Usage::

        config = AIProviderConfig("deepseek", "deepseek-v4-flash", "sk-...")
        svc = AIService(config)
        result = svc.analyze("Hello")
    """

    def __init__(self, config: AIProviderConfig) -> None:
        self.config = config
        # Resolve adapter eagerly — fail fast on unknown provider
        self._adapter = provider_catalog.get_adapter(config.provider)
        if self._adapter is None:
            raise RuntimeError(
                f"Provider '{config.provider}' không được hỗ trợ. "
                f"Các provider hiện có: {', '.join(provider_catalog.list_display_names())}"
            )

    # ------------------------------------------------------------------
    # Public API (unchanged signatures)
    # ------------------------------------------------------------------

    def test_api_key(self) -> bool:
        """Validate that provider, model, and api_key are all present."""
        return bool(self.config.provider and self.config.model and self.config.api_key)

    def test_model_response(self) -> bool:
        """Send a short test prompt to verify the model works."""
        response = self.analyze(
            "Trả lời đúng một câu ngắn bằng tiếng Việt: Kết nối AI hợp lệ."
        )
        return bool(response.strip())

    def analyze(self, prompt: str, *, max_tokens: int = 1800) -> str:
        """Generate a text response from *prompt*."""
        return self._adapter.generate(
            prompt, self.config.model, self.config.api_key, max_tokens,
        )

    def analyze_stream(self, prompt: str, *, max_tokens: int = 1800) -> Generator[str, None, None]:
        """Stream response chunks via SSE (falls back to single chunk)."""
        yield from self._adapter.generate_stream(
            prompt, self.config.model, self.config.api_key, max_tokens,
        )

    # ------------------------------------------------------------------
    # Provider-specific helpers (kept for backward compat)
    # ------------------------------------------------------------------

    @staticmethod
    def list_gemini_models(api_key: str) -> list[dict[str, object]]:
        """Fetch text-generation Gemini models from the REST API (cached).

        Kept as a static convenience for :class:`AIProviderCatalogService`.
        """
        adapter = provider_catalog.get_adapter("gemini")
        if adapter is not None:
            return adapter.discover_models(api_key)
        return []

    def _effective_max_tokens(self, requested: int) -> int:
        """Floor max_tokens for reasoning models (backward compat)."""
        floor: dict[str, int] = {
            "deepseek-v4-pro": 4000,
            "deepseek-v4-flash": 4000,
        }
        return max(requested, floor.get(self.config.model, 0))


# ------------------------------------------------------------------
# Backward-compatible re-exports (symbols moved to adapters)
# ------------------------------------------------------------------

# These were previously module-level in ai_service.py.  They now live on
# the adapters but are re-exported here so existing imports don't break.

from services.ai.providers.gemini_adapter import GEMINI_REST_BASE  # noqa: E402, F401
from services.ai.providers.gemini_adapter import _GEMINI_MODELS_CACHE  # noqa: E402, F401


def _gemini_friendly_error(model: str, raw_message: str) -> str:
    """Backward-compatible shim — delegates to GeminiAdapter."""
    from services.ai.providers.gemini_adapter import GeminiAdapter
    return GeminiAdapter().friendly_error(model, raw_message)
