"""OpenAI Compatible provider adapter — any endpoint speaking the OpenAI
Chat Completions protocol (``/chat/completions``).

Unlike the fixed-vendor adapters, the base URL is **not hard-coded**: it is
supplied at call time (``base_url``) so the same adapter can talk to any
OpenAI-compatible server (LM Studio, Ollama, vLLM, OpenRouter, a corporate
gateway, ...).  The base URL defaults to an empty string and must be provided
by the caller for a request to succeed.

Only the Chat Completions API is used — the OpenAI Responses API is NOT used.
"""

from __future__ import annotations

import json
import time as _time
from collections.abc import Generator
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import requests

from services.ai.provider_adapter import BaseProviderAdapter
from services.ai.provider_catalog import ProviderCapability, ProviderInfo, provider_catalog

# Model-discovery cache: "{api_key_prefix}|{base_url}" -> {"models": [...], "ts": float}
_OPENAI_COMPATIBLE_MODELS_CACHE: dict[str, object] = {}


def _normalize_base_url(base_url: str) -> str:
    """Trim and strip a trailing slash from *base_url*.

    Raises :class:`RuntimeError` when *base_url* is empty — an OpenAI-compatible
    endpoint has no fixed host, so the caller must always supply one.
    """
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise RuntimeError(
            "Nhà cung cấp OpenAI Compatible cần Base URL. "
            "Hãy nhập Base URL của endpoint tương thích OpenAI "
            "(vd: http://localhost:1234/v1)."
        )
    return base


class OpenAICompatibleAdapter(BaseProviderAdapter):
    @staticmethod
    def provider_name() -> str:
        return "openai_compatible"

    # -- Generate (Chat Completions) ----------------------------------------

    def generate(
        self, prompt: str, model: str, api_key: str, max_tokens: int,
        base_url: str = "",
    ) -> str:
        base = _normalize_base_url(base_url)
        url = f"{base}/chat/completions"
        payload = self._chat_completion_payload(prompt, model, max_tokens)
        data = self._post_json(
            url,
            payload,
            {"Authorization": f"Bearer {api_key}"},
        )
        content = self._extract_chat_completion_text(data)
        if content:
            return content
        raise RuntimeError(self._chat_completion_empty_reason(data))

    def generate_stream(
        self, prompt: str, model: str, api_key: str, max_tokens: int,
        base_url: str = "",
    ) -> Generator[str, None, None]:
        from services.sse_parser import iter_chat_completion_chunks

        base = _normalize_base_url(base_url)
        url = f"{base}/chat/completions"
        payload = self._chat_completion_payload(prompt, model, max_tokens, stream=True)
        try:
            response = requests.post(
                url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                stream=True,
                timeout=120,
            )
            if response.status_code != 200:
                detail = response.text[:300]
                raise RuntimeError(f"AI API lỗi HTTP {response.status_code}: {detail}")
            yield from iter_chat_completion_chunks(response)
        except requests.RequestException as exc:
            raise RuntimeError(f"Không kết nối được AI API: {exc}") from exc

    # -- Model discovery ({base_url}/models) --------------------------------

    def discover_models(self, api_key: str, base_url: str = "") -> list[dict[str, object]]:
        """Fetch models from ``{base_url}/models``.  Cached 30 min per
        (API key prefix, base URL) pair.

        Raises :class:`RuntimeError` on API error so the UI can show the
        specific failure reason.
        """
        base = _normalize_base_url(base_url)
        prefix = api_key[:8] if len(api_key) >= 8 else api_key
        cache_key = f"{prefix}|{base}"
        cached = _OPENAI_COMPATIBLE_MODELS_CACHE.get(cache_key)
        if cached and _time.time() - cached["ts"] < 1800:
            return list(cached["models"])

        url = f"{base}/models"
        try:
            req = Request(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                method="GET",
            )
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(
                f"OpenAI Compatible API lỗi HTTP {exc.code}: {detail[:300]}"
            ) from exc
        except Exception as exc:
            raise RuntimeError(
                f"Không kết nối được OpenAI Compatible API: {exc}"
            ) from exc

        models: list[dict[str, object]] = []
        for m in data.get("data", []):
            model_id = str(m.get("id", ""))
            if not model_id:
                continue
            models.append({
                "name": model_id,
                "display_name": model_id,
                "description": str(m.get("owned_by", "")),
            })

        _OPENAI_COMPATIBLE_MODELS_CACHE[cache_key] = {"models": list(models), "ts": _time.time()}
        return models


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

provider_catalog.register(
    ProviderInfo(
        name="openai_compatible",
        display_name="OpenAI Compatible (Tùy chỉnh)",
        capabilities=(
            ProviderCapability.CHAT
            | ProviderCapability.STREAM
            | ProviderCapability.MODEL_DISCOVERY
            | ProviderCapability.VISION
        ),
        default_models=(),
        locked_models=False,
        adapter_class=OpenAICompatibleAdapter,
    )
)
