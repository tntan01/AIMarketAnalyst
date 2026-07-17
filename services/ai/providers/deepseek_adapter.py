"""DeepSeek provider adapter — OpenAI-compatible chat completions with SSE streaming."""

from __future__ import annotations

from collections.abc import Generator

import requests

from services.ai.provider_adapter import BaseProviderAdapter
from services.ai.provider_catalog import ProviderCapability, ProviderInfo, provider_catalog

DEEPSEEK_BASE = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODELS = ("deepseek-v4-flash", "deepseek-v4-pro")
DEFAULT_DEEPSEEK_MODEL = DEEPSEEK_MODELS[0]

# DeepSeek v4 counts reasoning tokens toward budget; small max_tokens starves content
_REASONING_MODEL_MIN_TOKENS: dict[str, int] = {
    "deepseek-v4-pro": 4000,
    "deepseek-v4-flash": 4000,
}


class DeepSeekAdapter(BaseProviderAdapter):
    @staticmethod
    def provider_name() -> str:
        return "deepseek"

    # -- Model validation ----------------------------------------------------

    def validate_model(self, model: str) -> None:
        if model not in DEEPSEEK_MODELS:
            raise RuntimeError(
                "Model DeepSeek không hợp lệ. "
                "Hãy chọn deepseek-v4-flash hoặc deepseek-v4-pro trong Settings."
            )

    # -- Generate ------------------------------------------------------------

    def generate(self, prompt: str, model: str, api_key: str, max_tokens: int) -> str:
        self.validate_model(model)
        effective = max(max_tokens, _REASONING_MODEL_MIN_TOKENS.get(model, 0))
        payload = self._chat_completion_payload(prompt, model, effective)
        data = self._post_json(
            DEEPSEEK_BASE,
            payload,
            {"Authorization": f"Bearer {api_key}"},
        )
        content = self._extract_chat_completion_text(data)
        if content:
            return content
        raise RuntimeError(self._chat_completion_empty_reason(data))

    def generate_stream(
        self, prompt: str, model: str, api_key: str, max_tokens: int,
    ) -> Generator[str, None, None]:
        from services.sse_parser import iter_chat_completion_chunks

        self.validate_model(model)
        effective = max(max_tokens, _REASONING_MODEL_MIN_TOKENS.get(model, 0))
        payload = self._chat_completion_payload(prompt, model, effective, stream=True)
        try:
            response = requests.post(
                DEEPSEEK_BASE,
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


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

provider_catalog.register(
    ProviderInfo(
        name="deepseek",
        display_name="DeepSeek",
        capabilities=(
            ProviderCapability.CHAT
            | ProviderCapability.STREAM
            | ProviderCapability.SYSTEM_PROMPT
            | ProviderCapability.REASONING
            | ProviderCapability.JSON_MODE
        ),
        default_models=DEEPSEEK_MODELS,
        locked_models=True,
        adapter_class=DeepSeekAdapter,
    )
)
