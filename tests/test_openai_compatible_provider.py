"""Test for the new "OpenAI Compatible" provider.

Checks (all via mocked HTTP — NO real network calls):
  1. Provider exists in the catalog with correct metadata + capabilities.
  2. Adapter calls the correct ``/chat/completions`` URL (base URL supplied at
     call time, not hard-coded) and parses the response.
  3. Adapter discovers models from ``{base_url}/models`` and caches results.
  4. Streaming (SSE) posts to the correct URL.
  5. Existing adapters (DeepSeek, OpenAI, Anthropic, Gemini) are UNAFFECTED —
     they still target their original endpoints and their signatures did not
     change (no ``base_url`` parameter added).

Run directly:  python tests/test_openai_compatible_provider.py
  → prints per-check results and a final ✅ PASS / ❌ FAIL.
Also runnable under pytest.
"""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_urlopen(captured: dict, payload: dict):
    """Return a fake ``urlopen`` that records the request and returns *payload*."""
    def fake_urlopen(request, *args, **kwargs):
        captured["url"] = request.get_full_url()
        captured["method"] = request.get_method()
        captured["auth"] = request.get_header("Authorization")
        body = getattr(request, "data", None)
        captured["body"] = json.loads(body.decode("utf-8")) if body else None
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(payload).encode("utf-8")
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)
        return mock_response
    return fake_urlopen


def _adapter():
    from services.ai.providers.openai_compatible_adapter import OpenAICompatibleAdapter
    return OpenAICompatibleAdapter()


# ---------------------------------------------------------------------------
# 1. Catalog registration
# ---------------------------------------------------------------------------

def test_provider_registered_in_catalog():
    from services.ai import provider_catalog
    assert "openai_compatible" in provider_catalog.list_all()
    info = provider_catalog.get("openai_compatible")
    assert info is not None
    assert info.display_name == "OpenAI Compatible (Tùy chỉnh)"
    assert "OpenAI Compatible (Tùy chỉnh)" in provider_catalog.list_display_names()


def test_provider_capabilities():
    from services.ai.provider_catalog import ProviderCapability, provider_catalog
    caps = provider_catalog.get("openai_compatible").capabilities
    assert ProviderCapability.CHAT in caps
    assert ProviderCapability.STREAM in caps
    assert ProviderCapability.MODEL_DISCOVERY in caps
    assert ProviderCapability.VISION in caps


def test_provider_default_models_empty_and_unlocked():
    from services.ai.provider_catalog import provider_catalog
    info = provider_catalog.get("openai_compatible")
    assert info.default_models == ()
    assert info.locked_models is False


def test_provider_has_adapter():
    from services.ai import provider_catalog
    from services.ai.providers.openai_compatible_adapter import OpenAICompatibleAdapter
    adapter = provider_catalog.get_adapter("openai_compatible")
    assert isinstance(adapter, OpenAICompatibleAdapter)
    assert adapter.provider_name() == "openai_compatible"


def test_aiservice_dispatches_to_new_adapter():
    from services.ai_service import AIService, AIProviderConfig
    from services.ai.providers.openai_compatible_adapter import OpenAICompatibleAdapter
    svc = AIService(AIProviderConfig("openai_compatible", "any-model", "sk-"))
    assert isinstance(svc._adapter, OpenAICompatibleAdapter)


def test_aiservice_forwards_base_url_end_to_end():
    """AIService.analyze passes base_url from AIProviderConfig to the adapter URL."""
    from services.ai_service import AIService, AIProviderConfig
    captured: dict = {}
    response = {"choices": [{"message": {"content": "e2e"}}]}
    config = AIProviderConfig(
        "openai_compatible", "my-model", "sk-test", base_url="http://e2e-host/v1",
    )
    with patch("services.ai.provider_adapter.urlopen",
               _make_fake_urlopen(captured, response)):
        result = AIService(config).analyze("prompt")
    assert result == "e2e"
    assert captured["url"] == "http://e2e-host/v1/chat/completions"


def test_aiservice_empty_base_url_does_not_touch_other_adapters():
    """With no base_url, fixed-vendor adapters are called exactly as before."""
    from services.ai_service import AIService, AIProviderConfig
    captured: dict = {}
    response = {"choices": [{"message": {"content": "ds"}}]}
    config = AIProviderConfig("deepseek", "deepseek-v4-flash", "sk-")
    with patch("services.ai.provider_adapter.urlopen",
               _make_fake_urlopen(captured, response)):
        AIService(config).analyze("prompt")
    assert captured["url"] == "https://api.deepseek.com/chat/completions"


# ---------------------------------------------------------------------------
# 2. generate → /chat/completions
# ---------------------------------------------------------------------------

def test_generate_calls_chat_completions_url():
    adapter = _adapter()
    captured: dict = {}
    response = {"choices": [{"message": {"content": "xin chào"}}]}
    with patch("services.ai.provider_adapter.urlopen",
               _make_fake_urlopen(captured, response)):
        result = adapter.generate(
            "prompt", "my-model", "sk-test", 100,
            base_url="http://localhost:1234/v1",
        )
    assert result == "xin chào"
    assert captured["url"] == "http://localhost:1234/v1/chat/completions"
    assert captured["method"] == "POST"
    assert captured["auth"] == "Bearer sk-test"
    # Chat-completions body shape (NOT Responses API)
    assert captured["body"]["model"] == "my-model"
    assert "messages" in captured["body"]
    assert "input" not in captured["body"]  # Responses API field must be absent


def test_generate_handles_trailing_slash_base_url():
    adapter = _adapter()
    captured: dict = {}
    response = {"choices": [{"message": {"content": "ok"}}]}
    with patch("services.ai.provider_adapter.urlopen",
               _make_fake_urlopen(captured, response)):
        adapter.generate("p", "m", "k", 50, base_url="https://my-host/v1/")
    assert captured["url"] == "https://my-host/v1/chat/completions"


def test_generate_empty_base_url_raises_clear_error():
    adapter = _adapter()
    try:
        adapter.generate("p", "m", "k", 50, base_url="")
    except RuntimeError as exc:
        assert "Base URL" in str(exc)
    else:
        raise AssertionError("generate with empty base_url must raise RuntimeError")


# ---------------------------------------------------------------------------
# 3. discover_models → {base_url}/models (+ caching)
# ---------------------------------------------------------------------------

def test_discover_models_calls_models_url():
    from services.ai.providers import openai_compatible_adapter as mod
    mod._OPENAI_COMPATIBLE_MODELS_CACHE.clear()
    adapter = _adapter()
    captured: dict = {}
    payload = {"data": [{"id": "model-a"}, {"id": "model-b"}, {"id": ""}]}
    with patch("services.ai.providers.openai_compatible_adapter.urlopen",
               _make_fake_urlopen(captured, payload)):
        result = adapter.discover_models("sk-test", base_url="http://localhost:1234/v1")
    assert captured["url"] == "http://localhost:1234/v1/models"
    assert captured["method"] == "GET"
    assert captured["auth"] == "Bearer sk-test"
    names = [m["name"] for m in result]
    assert names == ["model-a", "model-b"]  # empty id skipped


def test_discover_models_is_cached():
    from services.ai.providers import openai_compatible_adapter as mod
    mod._OPENAI_COMPATIBLE_MODELS_CACHE.clear()
    adapter = _adapter()
    payload = {"data": [{"id": "cached-model"}]}
    calls = {"n": 0}

    def counting_urlopen(request, *a, **k):
        calls["n"] += 1
        return _make_fake_urlopen({}, payload)(request)

    with patch("services.ai.providers.openai_compatible_adapter.urlopen", counting_urlopen):
        first = adapter.discover_models("sk-test", base_url="http://host/v1")
        second = adapter.discover_models("sk-test", base_url="http://host/v1")
    assert [m["name"] for m in first] == ["cached-model"]
    assert [m["name"] for m in second] == ["cached-model"]
    assert calls["n"] == 1  # second call served from cache, no network


# ---------------------------------------------------------------------------
# 4. Streaming (SSE)
# ---------------------------------------------------------------------------

def test_generate_stream_posts_to_chat_completions():
    adapter = _adapter()
    sse_lines = [
        'data: {"choices":[{"delta":{"content":"Xin"}}]}',
        'data: {"choices":[{"delta":{"content":" chào"}}]}',
        'data: [DONE]',
    ]
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.iter_lines.return_value = iter(sse_lines)
    with patch("services.ai.providers.openai_compatible_adapter.requests.post",
               return_value=fake_resp) as mock_post:
        chunks = list(adapter.generate_stream(
            "p", "m", "k", 50, base_url="http://localhost:8000/v1",
        ))
    assert "".join(chunks) == "Xin chào"
    called_url = mock_post.call_args[0][0]
    assert called_url == "http://localhost:8000/v1/chat/completions"


# ---------------------------------------------------------------------------
# 5. Existing adapters unaffected
# ---------------------------------------------------------------------------

def test_deepseek_still_targets_original_endpoint():
    from services.ai.providers.deepseek_adapter import DeepSeekAdapter, DEEPSEEK_BASE
    captured: dict = {}
    response = {"choices": [{"message": {"content": "ds"}}]}
    with patch("services.ai.provider_adapter.urlopen",
               _make_fake_urlopen(captured, response)):
        DeepSeekAdapter().generate("p", "deepseek-v4-flash", "sk-", 100)
    assert captured["url"] == DEEPSEEK_BASE


def test_openai_still_uses_responses_api():
    from services.ai.providers.openai_adapter import OpenAIAdapter, OPENAI_RESPONSES_URL
    captured: dict = {}
    response = {"output_text": "oa"}
    with patch("services.ai.provider_adapter.urlopen",
               _make_fake_urlopen(captured, response)):
        OpenAIAdapter().generate("p", "gpt-4.1", "sk-", 100)
    assert captured["url"] == OPENAI_RESPONSES_URL
    assert "responses" in captured["url"]
    assert "chat/completions" not in captured["url"]


def test_anthropic_still_targets_messages_api():
    from services.ai.providers.anthropic_adapter import AnthropicAdapter, ANTHROPIC_MESSAGES_URL
    captured: dict = {}
    response = {"content": [{"type": "text", "text": "an"}]}
    with patch("services.ai.provider_adapter.urlopen",
               _make_fake_urlopen(captured, response)):
        AnthropicAdapter().generate("p", "claude-3-5-sonnet-latest", "sk-", 100)
    assert captured["url"] == ANTHROPIC_MESSAGES_URL


def test_gemini_still_targets_rest_base():
    from services.ai.providers.gemini_adapter import GeminiAdapter, GEMINI_REST_BASE
    captured: dict = {}
    response = {"candidates": [{"content": {"parts": [{"text": "ge"}]}}]}
    # GeminiAdapter.generate uses the shared BaseProviderAdapter._post_json,
    # which resolves urlopen from the provider_adapter module namespace.
    with patch("services.ai.provider_adapter.urlopen",
               _make_fake_urlopen(captured, response)):
        GeminiAdapter().generate("p", "gemini-3.5-flash", "key", 100)
    assert captured["url"].startswith(GEMINI_REST_BASE)
    assert "generateContent" in captured["url"]


def test_old_adapter_signatures_unchanged():
    """No existing adapter gained a base_url parameter."""
    from services.ai.providers.deepseek_adapter import DeepSeekAdapter
    from services.ai.providers.openai_adapter import OpenAIAdapter
    from services.ai.providers.anthropic_adapter import AnthropicAdapter
    from services.ai.providers.gemini_adapter import GeminiAdapter
    for cls in (DeepSeekAdapter, OpenAIAdapter, AnthropicAdapter, GeminiAdapter):
        for method in ("generate", "generate_stream", "discover_models"):
            fn = getattr(cls, method)
            params = inspect.signature(fn).parameters
            assert "base_url" not in params, f"{cls.__name__}.{method} changed signature"


def test_provider_settings_carries_base_url():
    """AIProviderSettings stores base_url and serializes it via asdict (save path)."""
    import dataclasses
    from config.settings import AIProviderSettings
    default = AIProviderSettings(provider="OpenAI Compatible (Tùy chỉnh)", model="m")
    assert default.base_url == ""
    custom = AIProviderSettings(provider="x", model="m", base_url="http://h/v1")
    assert custom.base_url == "http://h/v1"
    assert dataclasses.asdict(custom)["base_url"] == "http://h/v1"


def test_settings_service_loads_base_url():
    """SettingsService._load_ai_settings reads base_url from JSON."""
    from services.settings_service import SettingsService
    svc = SettingsService.__new__(SettingsService)  # skip __init__ (no storage needed)
    data = {"providers": [
        {"provider": "OpenAI Compatible (Tùy chỉnh)", "model": "m",
         "api_key": "sk-set", "base_url": "http://loaded/v1", "is_active": True},
    ]}
    ai = svc._load_ai_settings(data)
    assert ai.providers[0].base_url == "http://loaded/v1"


# ---------------------------------------------------------------------------
# Runner — prints ✅ PASS / ❌ FAIL
# ---------------------------------------------------------------------------

_CHECKS = [
    test_provider_registered_in_catalog,
    test_provider_capabilities,
    test_provider_default_models_empty_and_unlocked,
    test_provider_has_adapter,
    test_aiservice_dispatches_to_new_adapter,
    test_aiservice_forwards_base_url_end_to_end,
    test_aiservice_empty_base_url_does_not_touch_other_adapters,
    test_generate_calls_chat_completions_url,
    test_generate_handles_trailing_slash_base_url,
    test_generate_empty_base_url_raises_clear_error,
    test_discover_models_calls_models_url,
    test_discover_models_is_cached,
    test_generate_stream_posts_to_chat_completions,
    test_deepseek_still_targets_original_endpoint,
    test_openai_still_uses_responses_api,
    test_anthropic_still_targets_messages_api,
    test_gemini_still_targets_rest_base,
    test_old_adapter_signatures_unchanged,
    test_provider_settings_carries_base_url,
    test_settings_service_loads_base_url,
]


def main() -> int:
    failed = 0
    for check in _CHECKS:
        try:
            check()
            print(f"  ✅ {check.__name__}")
        except Exception as exc:  # noqa: BLE001 — report any failure
            failed += 1
            print(f"  ❌ {check.__name__}: {exc}")

    print()
    if failed == 0:
        print(f"✅ PASS — all {len(_CHECKS)} checks passed.")
        return 0
    print(f"❌ FAIL — {failed}/{len(_CHECKS)} checks failed.")
    return 1


if __name__ == "__main__":
    # Windows consoles default to a non-UTF-8 code page (e.g. cp1258) that
    # cannot encode the ✅/❌ markers — force UTF-8 so direct runs don't crash.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001 — stdout may not support reconfigure
        pass
    raise SystemExit(main())
