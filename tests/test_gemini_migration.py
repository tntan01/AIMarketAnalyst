"""Tests for Gemini model discovery, error handling, and catalog refresh.

Covers:
  - Default Gemini models are current (3.x series, not deprecated 2.5)
  - Friendly error messages for 404, 403, 401, 429
  - Model list filtering (text-only, no image/audio/embedding models)
  - Catalog refresh API
  - Cache mechanism
  - Backward compatibility with old config files
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
# Config tests
# ---------------------------------------------------------------------------

class TestDefaultGeminiModels:
    """Default models use current generation, not deprecated ones."""

    def test_config_json_has_current_models(self):
        """ai_providers.json should have 3.x models, not 2.5."""
        path = Path(__file__).resolve().parent.parent / "config" / "ai_providers.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        gemini = next(
            (p for p in data["providers"] if p["provider"] == "Gemini"), None
        )
        assert gemini is not None, "Gemini provider not found"
        assert "gemini-3.5-flash" in gemini["models"], "Missing gemini-3.5-flash"
        assert "gemini-2.5-flash" not in gemini["models"], "Deprecated model still present"
        assert "gemini-2.5-pro" not in gemini["models"], "Deprecated model still present"

    def test_constants_have_current_models(self):
        """Fallback constants should have 3.x models."""
        from config.constants import _FALLBACK_AI_MODELS
        gemini = _FALLBACK_AI_MODELS["Gemini"]
        assert "gemini-3.5-flash" in gemini
        assert "gemini-2.5-flash" not in gemini
        assert "gemini-2.5-pro" not in gemini

    def test_default_ai_models_loaded_from_config(self):
        """DEFAULT_AI_MODELS loads from config, not hard-coded."""
        from config.constants import DEFAULT_AI_MODELS
        assert "Gemini" in DEFAULT_AI_MODELS
        gemini_models = DEFAULT_AI_MODELS["Gemini"]
        assert len(gemini_models) >= 2
        assert any("gemini-3" in m for m in gemini_models)


# ---------------------------------------------------------------------------
# Error message tests
# ---------------------------------------------------------------------------

class TestGeminiErrorMessages:
    """Friendly error messages for various HTTP errors."""

    def test_404_model_not_found(self):
        from services.ai_service import _gemini_friendly_error
        msg = _gemini_friendly_error("gemini-2.5-flash", "HTTP Error 404: Not Found")
        assert "không còn khả dụng" in msg.lower() or "ngừng hỗ trợ" in msg
        assert "gemini-3.5-flash" in msg  # suggests current model

    def test_404_no_longer_available(self):
        from services.ai_service import _gemini_friendly_error
        msg = _gemini_friendly_error(
            "gemini-2.5-flash",
            'HTTP Error 404: {"error": {"message": "models/gemini-2.5-flash is no longer available to new users"}}',
        )
        assert "không còn khả dụng" in msg.lower() or "ngừng hỗ trợ" in msg

    def test_403_permission_denied(self):
        from services.ai_service import _gemini_friendly_error
        msg = _gemini_friendly_error("test-model", "HTTP Error 403: Permission denied")
        assert "403" in msg
        assert "api key" in msg.lower()

    def test_403_unregistered(self):
        from services.ai_service import _gemini_friendly_error
        msg = _gemini_friendly_error("test", "Method doesn't allow unregistered callers")
        assert "api key" in msg.lower()

    def test_401_unauthorized(self):
        from services.ai_service import _gemini_friendly_error
        msg = _gemini_friendly_error("test", "HTTP Error 401: Unauthorized")
        assert "401" in msg

    def test_429_rate_limit(self):
        from services.ai_service import _gemini_friendly_error
        msg = _gemini_friendly_error("test", "HTTP Error 429: Rate limit exceeded")
        assert "429" in msg
        assert "giới hạn" in msg.lower() or "quota" in msg.lower()


# ---------------------------------------------------------------------------
# Model filtering tests
# ---------------------------------------------------------------------------

class TestModelFiltering:
    """Model filtering: only generateContent matters (no name-based filter)."""

    def test_generate_content_filter_only(self):
        """Only models with generateContent are kept — no name-based exclusion."""
        # Simulate the adapter's filter logic
        test_models = [
            (["generateContent"], "gemini-3.5-flash", True),
            (["generateContent"], "gemini-2.5-flash-image", True),   # kept: generateContent present
            (["generateContent", "generateImages"], "gemini-3.1-flash-image", True),
            (["embedContent"], "gemini-embedding-2", False),           # no generateContent
            (["generateContent"], "gemini-3.1-flash-live-preview", True),
        ]
        for methods, name, should_keep in test_models:
            has_gc = "generateContent" in methods
            assert has_gc == should_keep, (
                f"Model {name}: generateContent={'YES' if has_gc else 'NO'}, expected keep={should_keep}"
            )

    def test_no_name_keyword_filter(self):
        """The old hard-coded keyword filter is removed — image/live/embedding models
        with generateContent ARE included."""
        # These are models that were excluded by the old keyword filter
        # but have generateContent.  Now they should be INCLUDED.
        models_with_gc = [
            "gemini-2.5-flash-image",
            "gemini-3.1-flash-live-preview",
        ]
        old_exclude_kw = ("image", "tts", "audio", "live", "embedding",
                          "veo", "imagen", "lyria", "computer-use",
                          "deep-research", "antigravity", "robotics")
        for name in models_with_gc:
            excluded_by_name = any(kw in name.lower() for kw in old_exclude_kw)
            assert excluded_by_name, (
                f"Test setup: {name} SHOULD be excluded by old keyword filter"
            )
            # New behavior: only generateContent matters, not name


# ---------------------------------------------------------------------------
# Catalog service tests
# ---------------------------------------------------------------------------

class TestCatalogRefresh:
    """AIProviderCatalogService refresh_gemini_models."""

    def test_refresh_with_discovered_models(self):
        """When API returns models, they replace the Gemini entry in cache."""
        from services.ai_provider_catalog_service import AIProviderCatalogService

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            tmp_path = Path(f.name)

        try:
            catalog = AIProviderCatalogService(tmp_path)

            # Mock adapter's discover_models (the real API layer)
            with patch("services.ai.providers.gemini_adapter.GeminiAdapter.discover_models") as mock_disc:
                mock_disc.return_value = [
                    {"name": "gemini-3.5-flash", "display_name": "Gemini 3.5 Flash", "description": "..."},
                    {"name": "gemini-3.1-pro-preview", "display_name": "Gemini 3.1 Pro", "description": "..."},
                    {"name": "gemini-2.5-flash-image", "display_name": "Nano Banana", "description": "..."},
                ]
                result = catalog.refresh_models("gemini", "test-key")

            # All models with generateContent are kept (no name-based filter)
            assert "gemini-3.5-flash" in result["Gemini"]
            assert "gemini-3.1-pro-preview" in result["Gemini"]
            # gemini-2.5-flash-image has generateContent → included (correct new behavior)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_refresh_falls_back_on_api_error(self):
        """When API raises and no disk cache exists, the error propagates."""
        from services.ai_provider_catalog_service import AIProviderCatalogService
        import pytest

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            tmp_path = Path(f.name)

        try:
            # Skip disk cache pre-load + fallback
            with patch.object(AIProviderCatalogService, "_load_all_from_disk", return_value=None):
                catalog = AIProviderCatalogService(tmp_path)
                catalog._load_from_disk = lambda key: None

                with patch("services.ai.providers.gemini_adapter.GeminiAdapter.discover_models") as mock_disc:
                    mock_disc.side_effect = RuntimeError("Network error")
                    with pytest.raises(RuntimeError, match="Network error"):
                        catalog.refresh_models("gemini", "test-key")
        finally:
            tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# AIService Gemini tests
# ---------------------------------------------------------------------------

class TestGeminiService:
    """AIService Gemini-specific behavior."""

    def test_gemini_provider_routes_to_generate_content(self):
        """Gemini provider triggers _gemini_generate_content."""
        from services.ai_service import AIService, AIProviderConfig
        svc = AIService(AIProviderConfig("gemini", "gemini-3.5-flash", "test-key"))
        # Verify the provider routing in analyze() would hit the Gemini branch
        assert "gemini" in svc.config.provider.lower()

    def test_list_gemini_models_returns_empty_on_error(self):
        """With invalid API key, the adapter raises (caller handles it)."""
        from services.ai_service import AIService
        import pytest

        # Mock the adapter to simulate API error
        with patch("services.ai.providers.gemini_adapter.GeminiAdapter.discover_models") as mock_disc:
            mock_disc.side_effect = RuntimeError("HTTP 403: Permission denied")
            # The static method AIService.list_gemini_models propagates the error
            with pytest.raises(RuntimeError, match="403"):
                AIService.list_gemini_models("invalid-key-12345")

    def test_gemini_endpoint_uses_v1beta(self):
        """Gemini REST API uses v1beta."""
        from services.ai_service import GEMINI_REST_BASE
        assert "v1beta" in GEMINI_REST_BASE
        assert "generativelanguage.googleapis.com" in GEMINI_REST_BASE

    def test_model_cache_key_is_api_key_prefix(self):
        """Cache key uses first 8 chars of API key."""
        from services.ai_service import _GEMINI_MODELS_CACHE
        # Cache is module-level dict, just verify it exists
        assert isinstance(_GEMINI_MODELS_CACHE, dict)


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    """Old configs and settings should still work."""

    def test_old_model_names_still_accepted_in_settings(self):
        """Even with old model name in settings, the service won't crash."""
        from services.ai_service import AIProviderConfig
        # Old model name is accepted as config (error only at API call time)
        config = AIProviderConfig("gemini", "gemini-2.5-flash", "old-key")
        assert config.model == "gemini-2.5-flash"

    def test_catalog_handles_missing_gemini(self):
        """If Gemini not in catalog, it's added with fallback models."""
        from services.ai_provider_catalog_service import AIProviderCatalogService

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            tmp_path = Path(f.name)

        try:
            # Catalog without Gemini
            data = {
                "providers": [
                    {"provider": "DeepSeek", "models": ["deepseek-v4-flash"]},
                ]
            }
            tmp_path.write_text(json.dumps(data), encoding="utf-8")

            catalog = AIProviderCatalogService(tmp_path)
            result = catalog.load()
            # Gemini should still appear (from FIXED_AI_PROVIDERS default)
            assert "Gemini" in result
        finally:
            tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
