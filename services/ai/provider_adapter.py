"""Base provider adapter — abstract interface every AI provider must implement.

Each concrete adapter (DeepSeek, OpenAI, Anthropic, Gemini, ...) subclasses
:class:`BaseProviderAdapter` and implements the required methods.  The adapter
is **stateless** — all parameters (api_key, model, prompt) are passed in at
call time.  Shared HTTP and response-parsing helpers live on this base class.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Generator
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class BaseProviderAdapter(ABC):
    """Stateless adapter for one AI provider.

    Subclasses MUST implement:
    * :meth:`provider_name`
    * :meth:`generate`

    Subclasses MAY override:
    * :meth:`generate_stream`     (default: falls back to :meth:`generate`)
    * :meth:`discover_models`     (default: returns empty list)
    * :meth:`friendly_error`      (default: returns raw message)
    * :meth:`validate_model`      (default: always valid)
    """

    # ------------------------------------------------------------------
    # Subclass contract
    # ------------------------------------------------------------------

    @staticmethod
    @abstractmethod
    def provider_name() -> str:
        """Return the canonical internal name, e.g. ``"deepseek"``."""
        ...

    @abstractmethod
    def generate(self, prompt: str, model: str, api_key: str, max_tokens: int) -> str:
        """Send *prompt* to the provider and return the text response."""
        ...

    def generate_stream(
        self, prompt: str, model: str, api_key: str, max_tokens: int,
    ) -> Generator[str, None, None]:
        """Stream response chunks.  Default: single-chunk fallback."""
        yield self.generate(prompt, model, api_key, max_tokens)

    def discover_models(self, api_key: str) -> list[dict[str, object]]:
        """Return available models from the provider's API.

        Each dict SHOULD have keys: ``name``, ``display_name``, ``description``.
        Returns an empty list when discovery is unsupported or fails.
        """
        return []

    def friendly_error(self, model: str, raw_message: str) -> str:
        """Translate a raw HTTP error into a user-friendly message."""
        return raw_message

    def validate_model(self, model: str) -> None:
        """Raise :class:`RuntimeError` if *model* is not valid for this provider.

        Default: no-op (accept all models).
        """
        return

    # ------------------------------------------------------------------
    # Shared HTTP helpers
    # ------------------------------------------------------------------

    def _post_json(
        self, url: str, payload: dict[str, object], headers: dict[str, str],
    ) -> dict[str, object]:
        """POST JSON *payload* to *url*, return parsed JSON response dict."""
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        try:
            with urlopen(request, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(
                self.friendly_error("", f"HTTP {exc.code}: {detail[:300]}")
            ) from exc
        except URLError as exc:
            raise RuntimeError(f"Không kết nối được AI API: {exc.reason}") from exc

    def _get_json(self, url: str, timeout: int = 30) -> dict[str, object]:
        """GET JSON from *url*, return parsed dict."""
        request = Request(url, method="GET")
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"HTTP {exc.code}: {detail[:300]}") from exc
        except URLError as exc:
            raise RuntimeError(f"Không kết nối được API: {exc.reason}") from exc

    # ------------------------------------------------------------------
    # Shared chat-completion helpers (OpenAI-compatible endpoints)
    # ------------------------------------------------------------------

    SYSTEM_PROMPT_TEXT = (
        "Bạn là AI Writer của AI Market Analyst. "
        "Không tự bịa số liệu; chỉ diễn giải dữ liệu do app cung cấp."
    )

    def _chat_completion_payload(
        self, prompt: str, model: str, max_tokens: int, *, stream: bool = False,
    ) -> dict[str, object]:
        """Build a standard chat-completion request body."""
        return {
            "model": model,
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT_TEXT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
            **({"stream": True} if stream else {}),
        }

    def _extract_chat_completion_text(self, data: dict[str, object]) -> str:
        """Extract text from a chat-completion response dict."""
        choices = data.get("choices", [])
        if not isinstance(choices, list) or not choices:
            return ""
        choice = choices[0]
        if not isinstance(choice, dict):
            return ""

        message = choice.get("message", {})
        if isinstance(message, dict):
            for key in ("content", "reasoning_content"):
                text = self._text_from_chat_value(message.get(key))
                if text:
                    return text

        text = self._text_from_chat_value(choice.get("text"))
        if text:
            return text

        delta = choice.get("delta", {})
        if isinstance(delta, dict):
            for key in ("content", "reasoning_content"):
                text = self._text_from_chat_value(delta.get(key))
                if text:
                    return text
        return ""

    @staticmethod
    def _text_from_chat_value(value: object) -> str:
        """Normalize a possibly-nested chat message value to a string."""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                    if text:
                        parts.append(str(text))
            return "\n".join(
                part.strip() for part in parts if part and part.strip()
            ).strip()
        return ""

    def _chat_completion_empty_reason(self, data: dict[str, object]) -> str:
        """Build a human-readable reason for an empty chat-completion response."""
        choices = data.get("choices", [])
        if not isinstance(choices, list) or not choices:
            return "AI không trả về lựa chọn phản hồi."
        choice = choices[0] if choices else {}
        if not isinstance(choice, dict):
            return "AI trả về phản hồi không đúng định dạng."
        finish_reason = str(choice.get("finish_reason") or "").strip()
        if finish_reason == "content_filter":
            return "AI đã chặn nội dung phản hồi theo bộ lọc an toàn."
        if finish_reason == "length":
            return "AI hết giới hạn token trước khi tạo được nội dung."
        if finish_reason == "insufficient_system_resource":
            return "Thiếu tài nguyên suy luận tạm thời. Hãy thử lại sau ít phút."
        if finish_reason == "tool_calls":
            return "AI yêu cầu tool call nhưng ứng dụng không bật chế độ tool."
        if finish_reason:
            return f"AI không trả về nội dung phân tích. finish_reason={finish_reason}."
        return "AI không trả về nội dung phân tích."
