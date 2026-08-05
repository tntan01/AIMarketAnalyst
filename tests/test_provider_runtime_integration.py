"""Integration tests for Provider Runtime Discovery architecture.

Covers all providers: Gemini, OpenAI, Anthropic, DeepSeek + OpenRouter (unregistered).
Tests: Provider Catalog, Capabilities, Model Discovery, Runtime Cache,
Offline Fallback, Backward Compatibility.
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# Provider Catalog
# ---------------------------------------------------------------------------

class TestProviderCatalog:
    """All providers are registered with correct metadata."""

    def test_all_four_providers_registered(self):
        from services.ai.provider_catalog import provider_catalog
        names = provider_catalog.list_all()
        assert "deepseek" in names
        assert "openai" in names
        assert "anthropic" in names
        assert "gemini" in names
        assert "openai_compatible" in names
        assert len(names) == 5

    def test_display_names_match_ui_expectations(self):
        from services.ai.provider_catalog import provider_catalog
        display = provider_catalog.list_display_names()
        assert display == [
            "DeepSeek", "OpenAI", "Anthropic", "Gemini",
            "OpenAI Compatible (Tùy chỉnh)",
        ]

    def test_each_provider_has_default_models(self):
        from services.ai.provider_catalog import provider_catalog
        for info in provider_catalog.list_infos():
            if info.name == "openai_compatible":
                continue  # user-supplied endpoint: no fixed default models
            assert len(info.default_models) >= 2, (
                f"{info.display_name} has only {len(info.default_models)} default models"
            )

    def test_each_provider_has_adapter(self):
        from services.ai.provider_catalog import provider_catalog
        for info in provider_catalog.list_infos():
            adapter = provider_catalog.get_adapter(info.name)
            assert adapter is not None, f"{info.display_name} has no adapter"
            assert adapter.provider_name() == info.name

    def test_deepseek_is_locked(self):
        from services.ai.provider_catalog import provider_catalog
        info = provider_catalog.get("deepseek")
        assert info.locked_models is True

    def test_other_providers_not_locked(self):
        from services.ai.provider_catalog import provider_catalog
        for name in ("openai", "anthropic", "gemini"):
            info = provider_catalog.get(name)
            assert info.locked_models is False, f"{name} should not be locked"


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------

class TestCapabilities:
    """Each provider declares correct capabilities."""

    def test_deepseek_capabilities(self):
        from services.ai.provider_catalog import ProviderCapability, provider_catalog
        caps = provider_catalog.get("deepseek").capabilities
        assert ProviderCapability.CHAT in caps
        assert ProviderCapability.STREAM in caps
        assert ProviderCapability.REASONING in caps
        assert ProviderCapability.JSON_MODE in caps
        assert ProviderCapability.MODEL_DISCOVERY not in caps
        assert ProviderCapability.VISION not in caps

    def test_openai_capabilities(self):
        from services.ai.provider_catalog import ProviderCapability, provider_catalog
        caps = provider_catalog.get("openai").capabilities
        assert ProviderCapability.MODEL_DISCOVERY in caps
        assert ProviderCapability.VISION in caps
        assert ProviderCapability.TOOL_CALLING in caps

    def test_anthropic_capabilities(self):
        from services.ai.provider_catalog import ProviderCapability, provider_catalog
        caps = provider_catalog.get("anthropic").capabilities
        assert ProviderCapability.VISION in caps
        assert ProviderCapability.TOOL_CALLING in caps

    def test_gemini_capabilities(self):
        from services.ai.provider_catalog import ProviderCapability, provider_catalog
        caps = provider_catalog.get("gemini").capabilities
        assert ProviderCapability.MODEL_DISCOVERY in caps
        assert ProviderCapability.VISION in caps

    def test_capability_labels_are_non_empty(self):
        from services.ai.provider_catalog import ProviderCapability, capability_labels
        for info in ["deepseek", "openai", "anthropic", "gemini"]:
            from services.ai.provider_catalog import provider_catalog
            caps = provider_catalog.get(info).capabilities
            labels = capability_labels(caps)
            assert len(labels) >= 1, f"{info}: no labels"
            assert all(isinstance(l, str) and l for l in labels)

    def test_only_discovery_providers_have_discovery_flag(self):
        from services.ai.provider_catalog import ProviderCapability, provider_catalog
        discovery_providers = {"openai", "gemini", "openai_compatible"}
        for info in provider_catalog.list_infos():
            has = ProviderCapability.MODEL_DISCOVERY in info.capabilities
            if info.name in discovery_providers:
                assert has, f"{info.name} should have MODEL_DISCOVERY"
            else:
                assert not has, f"{info.name} should NOT have MODEL_DISCOVERY"


# ---------------------------------------------------------------------------
# Model Discovery
# ---------------------------------------------------------------------------

class TestModelDiscovery:
    """Each provider's discover_models() works correctly."""

    def test_gemini_discovers_models(self):
        from services.ai.providers.gemini_adapter import GeminiAdapter, _GEMINI_MODELS_CACHE
        from unittest.mock import patch, MagicMock
        adapter = GeminiAdapter()
        _GEMINI_MODELS_CACHE.clear()

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "models": [
                {"name": "models/gemini-3.5-flash", "displayName": "G 3.5 Flash",
                 "supportedGenerationMethods": ["generateContent", "countTokens"]},
                {"name": "models/gemini-embedding-2", "displayName": "Embedding 2",
                 "supportedGenerationMethods": ["embedContent"]},
                {"name": "models/gemini-2.5-flash-image", "displayName": "Nano Banana",
                 "supportedGenerationMethods": ["generateContent", "generateImages"]},
            ]
        }).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)

        with patch("services.ai.providers.gemini_adapter.urlopen", return_value=mock_response):
            result = adapter.discover_models("test-key")

        names = [m["name"] for m in result]
        assert "gemini-3.5-flash" in names
        assert "gemini-2.5-flash-image" in names
        assert "gemini-embedding-2" not in names

    def test_openai_discovers_models(self):
        from services.ai.providers.openai_adapter import OpenAIAdapter, _OPENAI_MODELS_CACHE
        from unittest.mock import patch, MagicMock
        adapter = OpenAIAdapter()
        _OPENAI_MODELS_CACHE.clear()

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "data": [
                {"id": "gpt-4.1"}, {"id": "gpt-4.1-mini"}, {"id": "o4-mini"},
                {"id": "whisper-1"}, {"id": "text-embedding-3-small"}, {"id": "dall-e-3"},
            ]
        }).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)

        with patch("services.ai.providers.openai_adapter.urlopen", return_value=mock_response):
            result = adapter.discover_models("test-key")

        names = [m["name"] for m in result]
        assert "gpt-4.1" in names
        assert "o4-mini" in names
        assert "whisper-1" not in names
        assert "text-embedding-3-small" not in names
        assert "dall-e-3" not in names

    def test_anthropic_returns_empty(self):
        from services.ai.providers.anthropic_adapter import AnthropicAdapter
        adapter = AnthropicAdapter()
        result = adapter.discover_models("test-key")
        assert result == []

    def test_deepseek_returns_empty(self):
        from services.ai.providers.deepseek_adapter import DeepSeekAdapter
        adapter = DeepSeekAdapter()
        result = adapter.discover_models("test-key")
        assert result == []


# ---------------------------------------------------------------------------
# Runtime Cache
# ---------------------------------------------------------------------------

class TestRuntimeCache:
    """Disk cache persists and survives restarts."""

    def test_cache_survives_new_instance(self):
        from services.ai_provider_catalog_service import AIProviderCatalogService, _cache_dir
        import shutil

        # Clean
        cd = _cache_dir()
        if cd.exists():
            shutil.rmtree(cd)
        cd.mkdir(parents=True, exist_ok=True)

        try:
            # Instance 1: discover and cache
            catalog1 = AIProviderCatalogService()
            catalog1._cache_set("gemini", ["gemini-3.5-flash", "gemini-3.1-pro"])

            # Instance 2: should load from disk
            catalog2 = AIProviderCatalogService()
            models = catalog2.load()
            assert "gemini-3.5-flash" in models["Gemini"]
            assert "gemini-3.1-pro" in models["Gemini"]
        finally:
            shutil.rmtree(cd, ignore_errors=True)

    def test_cache_file_format_no_secrets(self):
        from services.ai_provider_catalog_service import AIProviderCatalogService, _cache_dir
        import shutil

        cd = _cache_dir()
        if cd.exists():
            shutil.rmtree(cd)
        cd.mkdir(parents=True, exist_ok=True)

        try:
            catalog = AIProviderCatalogService()
            catalog._cache_set("openai", ["gpt-4.1", "gpt-4.1-mini"])

            path = catalog._disk_path("openai")
            data = json.loads(path.read_text())

            assert "provider" in data
            assert "models" in data
            assert "last_sync" in data
            assert "metadata" in data
            # Absolutely no secrets
            raw = path.read_text().lower()
            for secret in ("api_key", "key", "secret", "token", "bearer", "auth", "password"):
                assert secret not in raw, f"SECRET LEAK: {secret}"
        finally:
            shutil.rmtree(cd, ignore_errors=True)

    def test_offline_fallback_on_api_error(self):
        from services.ai_provider_catalog_service import AIProviderCatalogService, _cache_dir
        import shutil

        cd = _cache_dir()
        if cd.exists():
            shutil.rmtree(cd)
        cd.mkdir(parents=True, exist_ok=True)

        try:
            # Pre-populate disk cache
            catalog = AIProviderCatalogService()
            catalog._cache_set("gemini", ["cached-model-1", "cached-model-2"])

            # New instance with API failure → should use disk cache
            catalog2 = AIProviderCatalogService()
            with patch("services.ai.providers.gemini_adapter.GeminiAdapter.discover_models",
                       side_effect=RuntimeError("Network down")):
                result = catalog2.refresh_models("gemini", "test-key")
                assert "cached-model-1" in result["Gemini"]
                assert "cached-model-2" in result["Gemini"]
        finally:
            shutil.rmtree(cd, ignore_errors=True)

    def test_no_cache_raises_on_api_error(self):
        from services.ai_provider_catalog_service import AIProviderCatalogService, _cache_dir
        import shutil

        cd = _cache_dir()
        if cd.exists():
            shutil.rmtree(cd)
        cd.mkdir(parents=True, exist_ok=True)

        try:
            catalog = AIProviderCatalogService()
            catalog._load_from_disk = lambda key: None  # no disk cache

            with patch("services.ai.providers.gemini_adapter.GeminiAdapter.discover_models",
                       side_effect=RuntimeError("Network down")):
                with pytest.raises(RuntimeError, match="Network down"):
                    catalog.refresh_models("gemini", "test-key")
        finally:
            shutil.rmtree(cd, ignore_errors=True)

    def test_non_discovery_provider_uses_defaults(self):
        from services.ai_provider_catalog_service import AIProviderCatalogService
        catalog = AIProviderCatalogService()
        catalog._load_all_from_disk = lambda: None
        # Anthropic has no MODEL_DISCOVERY → should silently use defaults
        result = catalog.refresh_models("anthropic", "fake-key")
        models = result.get("Anthropic", [])
        assert len(models) >= 2


# ---------------------------------------------------------------------------
# Backward Compatibility
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    """Old APIs still work after refactoring."""

    def test_aiprovider_config_unchanged(self):
        from services.ai_service import AIProviderConfig
        config = AIProviderConfig("gemini", "gemini-3.5-flash", "key")
        assert config.provider == "gemini"
        assert config.model == "gemini-3.5-flash"
        assert config.api_key == "key"

    def test_aiservice_public_api_unchanged(self):
        from services.ai_service import AIService, AIProviderConfig
        config = AIProviderConfig("deepseek", "deepseek-v4-flash", "sk-test")
        svc = AIService(config)
        assert svc.test_api_key() is True
        assert hasattr(svc, "analyze")
        assert hasattr(svc, "analyze_stream")
        assert hasattr(svc, "test_model_response")

    def test_fixed_ai_providers_still_works(self):
        from services.ai_provider_catalog_service import FIXED_AI_PROVIDERS
        assert isinstance(FIXED_AI_PROVIDERS, list)
        assert "DeepSeek" in FIXED_AI_PROVIDERS
        assert "Gemini" in FIXED_AI_PROVIDERS

    def test_gemini_fallback_models_still_works(self):
        from services.ai_provider_catalog_service import _GEMINI_FALLBACK_MODELS
        assert isinstance(_GEMINI_FALLBACK_MODELS, list)
        assert len(_GEMINI_FALLBACK_MODELS) >= 2

    def test_list_gemini_models_still_works(self):
        from services.ai_service import AIService
        # With valid mock
        with patch("services.ai.providers.gemini_adapter.GeminiAdapter.discover_models",
                   return_value=[{"name": "gemini-3.5-flash", "display_name": "G 3.5", "description": ""}]):
            result = AIService.list_gemini_models("test-key")
            assert len(result) == 1
            assert result[0]["name"] == "gemini-3.5-flash"

    def test_old_aiservice_unknown_provider_raises(self):
        from services.ai_service import AIService, AIProviderConfig
        with pytest.raises(RuntimeError, match="không được hỗ trợ"):
            AIService(AIProviderConfig("nonexistent", "m1", "k"))

    def test_refresh_gemini_models_alias_works(self):
        from services.ai_provider_catalog_service import AIProviderCatalogService, _cache_dir
        import shutil
        cd = _cache_dir()
        if cd.exists():
            shutil.rmtree(cd)
        cd.mkdir(parents=True, exist_ok=True)
        try:
            catalog = AIProviderCatalogService()
            catalog._load_all_from_disk = lambda: None
            catalog._load_from_disk = lambda key: None
            with patch("services.ai.providers.gemini_adapter.GeminiAdapter.discover_models",
                       return_value=[{"name": "gemini-3.5-flash", "display_name": "G", "description": ""}]):
                result = catalog.refresh_gemini_models("test-key")
                assert "gemini-3.5-flash" in result["Gemini"]
        finally:
            shutil.rmtree(cd, ignore_errors=True)

    def test_deepseek_models_constant_unchanged(self):
        from config.constants import DEEPSEEK_MODELS, DEFAULT_DEEPSEEK_MODEL
        assert DEEPSEEK_MODELS == ["deepseek-v4-flash", "deepseek-v4-pro"]
        assert DEFAULT_DEEPSEEK_MODEL == "deepseek-v4-flash"

    def test_default_ai_models_works(self):
        from config.constants import DEFAULT_AI_MODELS, AI_PROVIDERS
        assert "DeepSeek" in DEFAULT_AI_MODELS
        assert "Gemini" in DEFAULT_AI_MODELS
        assert len(AI_PROVIDERS) >= 4

    def test_ai_providers_json_format_unchanged(self):
        """ai_providers.json still has the expected structure."""
        path = Path(__file__).resolve().parent.parent / "config" / "ai_providers.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "providers" in data
        providers = {p["provider"] for p in data["providers"]}
        assert providers == {"DeepSeek", "OpenAI", "Anthropic", "Gemini"}


# ---------------------------------------------------------------------------
# OpenRouter (unregistered provider)
# ---------------------------------------------------------------------------

class TestOpenRouter:
    """Adding a new provider does not require changing any existing code."""

    def test_can_register_new_provider_at_runtime(self):
        from services.ai.provider_catalog import (
            ProviderCapability, ProviderInfo, provider_catalog,
        )
        from services.ai.provider_adapter import BaseProviderAdapter

        class OpenRouterAdapter(BaseProviderAdapter):
            @staticmethod
            def provider_name() -> str:
                return "openrouter"

            def generate(self, prompt, model, api_key, max_tokens):
                payload = self._chat_completion_payload(prompt, model, max_tokens)
                data = self._post_json(
                    "https://openrouter.ai/api/v1/chat/completions",
                    payload,
                    {"Authorization": f"Bearer {api_key}"},
                )
                content = self._extract_chat_completion_text(data)
                if content:
                    return content
                raise RuntimeError("No response")

        provider_catalog.register(ProviderInfo(
            name="openrouter",
            display_name="OpenRouter",
            capabilities=ProviderCapability.CHAT | ProviderCapability.STREAM,
            default_models=("openai/gpt-4.1", "anthropic/claude-sonnet-4-20250514"),
            adapter_class=OpenRouterAdapter,
        ))

        # Verify registration
        info = provider_catalog.get("openrouter")
        assert info is not None
        assert info.display_name == "OpenRouter"
        assert ProviderCapability.STREAM in info.capabilities

        # Verify adapter works
        adapter = provider_catalog.get_adapter("openrouter")
        assert adapter is not None
        assert isinstance(adapter, OpenRouterAdapter)

        # Verify it appears in list
        assert "OpenRouter" in provider_catalog.list_display_names()

        # Verify AIService can use it
        from services.ai_service import AIService, AIProviderConfig
        svc = AIService(AIProviderConfig("openrouter", "openai/gpt-4.1", "sk-test"))
        assert svc.test_api_key() is True

        # Cleanup: remove from catalog (not normally done, just for test isolation)
        provider_catalog._providers.pop("openrouter", None)
        provider_catalog._adapters.pop("openrouter", None)


# ---------------------------------------------------------------------------
# Adapter dispatch
# ---------------------------------------------------------------------------

class TestAdapterDispatch:
    """AIService correctly dispatches to the right adapter."""

    def test_deepseek_adapter_used(self):
        from services.ai_service import AIService, AIProviderConfig
        from services.ai.providers.deepseek_adapter import DeepSeekAdapter
        svc = AIService(AIProviderConfig("deepseek", "deepseek-v4-flash", "sk-"))
        assert isinstance(svc._adapter, DeepSeekAdapter)

    def test_openai_adapter_used(self):
        from services.ai_service import AIService, AIProviderConfig
        from services.ai.providers.openai_adapter import OpenAIAdapter
        svc = AIService(AIProviderConfig("openai", "gpt-4.1", "sk-"))
        assert isinstance(svc._adapter, OpenAIAdapter)

    def test_anthropic_adapter_used(self):
        from services.ai_service import AIService, AIProviderConfig
        from services.ai.providers.anthropic_adapter import AnthropicAdapter
        svc = AIService(AIProviderConfig("anthropic", "claude-3-5-sonnet-latest", "sk-"))
        assert isinstance(svc._adapter, AnthropicAdapter)

    def test_gemini_adapter_used(self):
        from services.ai_service import AIService, AIProviderConfig
        from services.ai.providers.gemini_adapter import GeminiAdapter
        svc = AIService(AIProviderConfig("gemini", "gemini-3.5-flash", "key"))
        assert isinstance(svc._adapter, GeminiAdapter)

    def test_deepseek_validates_model(self):
        from services.ai_service import AIService, AIProviderConfig
        svc = AIService(AIProviderConfig("deepseek", "invalid-model", "sk-"))
        with pytest.raises(RuntimeError, match="DeepSeek"):
            svc.analyze("test")

    def test_unknown_provider_raises_early(self):
        from services.ai_service import AIService, AIProviderConfig
        with pytest.raises(RuntimeError, match="không được hỗ trợ"):
            AIService(AIProviderConfig("madeup", "x", "y"))


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
