"""OpenAI provider adapter — uses Responses API (not Chat Completions)."""

from __future__ import annotations

import json
import time as _time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from services.ai.provider_adapter import BaseProviderAdapter
from services.ai.provider_catalog import ProviderCapability, ProviderInfo, provider_catalog

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
OPENAI_MODELS_URL = "https://api.openai.com/v1/models"
_OPENAI_MODELS_CACHE: dict[str, object] = {}  # api_key_prefix -> {"models": [...], "ts": float}

# OpenAI models to exclude from discovery (non-chat models)
_OPENAI_EXCLUDE_PREFIXES = (
    "whisper-", "tts-", "dall-e", "text-embedding", "text-moderation",
    "babbage", "davinci", "omni-moderation",
)


class OpenAIAdapter(BaseProviderAdapter):
    @staticmethod
    def provider_name() -> str:
        return "openai"

    def generate(self, prompt: str, model: str, api_key: str, max_tokens: int) -> str:
        payload = {
            "model": model,
            "input": prompt,
            "max_output_tokens": max_tokens,
        }
        data = self._post_json(
            OPENAI_RESPONSES_URL,
            payload,
            {"Authorization": f"Bearer {api_key}"},
        )
        # Responses API has two places for output text
        if data.get("output_text"):
            return str(data["output_text"]).strip()
        texts: list[str] = []
        for item in data.get("output", []):
            for content in item.get("content", []):
                text = content.get("text")
                if text:
                    texts.append(text)
        if texts:
            return "\n".join(texts).strip()
        raise RuntimeError("AI không trả về nội dung phân tích.")

    def discover_models(self, api_key: str) -> list[dict[str, object]]:
        """Fetch chat models from OpenAI API.  Cached 30 min per API key prefix.

        Raises :class:`RuntimeError` on API error so the UI can show the
        specific failure reason.
        """
        prefix = api_key[:8] if len(api_key) >= 8 else api_key
        cached = _OPENAI_MODELS_CACHE.get(prefix)
        if cached and _time.time() - cached["ts"] < 1800:
            return list(cached["models"])

        try:
            req = Request(
                OPENAI_MODELS_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                method="GET",
            )
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(
                f"OpenAI API lỗi HTTP {exc.code}: {detail[:300]}"
            ) from exc
        except Exception as exc:
            raise RuntimeError(
                f"Không kết nối được OpenAI API: {exc}"
            ) from exc

        models: list[dict[str, object]] = []
        for m in data.get("data", []):
            model_id = str(m.get("id", ""))
            if not model_id:
                continue
            # Filter out non-chat models
            if any(model_id.startswith(p) for p in _OPENAI_EXCLUDE_PREFIXES):
                continue
            # Only include gpt-*, o* series
            if not (model_id.startswith("gpt-") or model_id.startswith("o")):
                continue
            models.append({
                "name": model_id,
                "display_name": model_id,
                "description": str(m.get("owned_by", "")),
            })

        _OPENAI_MODELS_CACHE[prefix] = {"models": list(models), "ts": _time.time()}
        return models


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

provider_catalog.register(
    ProviderInfo(
        name="openai",
        display_name="OpenAI",
        capabilities=(
            ProviderCapability.CHAT
            | ProviderCapability.MODEL_DISCOVERY
            | ProviderCapability.VISION
            | ProviderCapability.TOOL_CALLING
            | ProviderCapability.JSON_MODE
        ),
        default_models=("gpt-4.1", "gpt-4.1-mini", "o4-mini"),
        locked_models=False,
        adapter_class=OpenAIAdapter,
    )
)
