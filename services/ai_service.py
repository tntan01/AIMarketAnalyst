from __future__ import annotations

import json
from collections.abc import Generator
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import requests

from config.constants import DEEPSEEK_MODELS

# Minimum max_tokens for reasoning models.  DeepSeek v4 counts reasoning
# tokens toward the budget; small values cause content to be starved.
_REASONING_MODEL_MIN_TOKENS: dict[str, int] = {
    "deepseek-v4-pro": 4000,
    "deepseek-v4-flash": 4000,
}


@dataclass(frozen=True, slots=True)
class AIProviderConfig:
    provider: str
    model: str
    api_key: str


class AIService:
    def __init__(self, config: AIProviderConfig) -> None:
        self.config = config

    def test_api_key(self) -> bool:
        return bool(self.config.provider and self.config.model and self.config.api_key)

    def test_model_response(self) -> bool:
        response = self.analyze("Trả lời đúng một câu ngắn bằng tiếng Việt: Kết nối AI hợp lệ.")
        return bool(response.strip())

    def analyze(self, prompt: str, *, max_tokens: int = 1800) -> str:
        provider = self.config.provider.lower()
        if "openai" in provider:
            return self._openai_response(prompt, max_tokens)
        if "deepseek" in provider:
            if self.config.model not in DEEPSEEK_MODELS:
                raise RuntimeError(
                    "Model DeepSeek không hợp lệ. Hãy chọn deepseek-v4-flash hoặc deepseek-v4-pro trong Settings."
                )
            return self._chat_completion("https://api.deepseek.com/chat/completions", prompt, max_tokens)
        if "anthropic" in provider or "claude" in provider:
            return self._anthropic_message(prompt, max_tokens)
        if "gemini" in provider or "google" in provider:
            return self._gemini_generate_content(prompt)
        return self._chat_completion("https://api.openai.com/v1/chat/completions", prompt, max_tokens)

    def analyze_stream(self, prompt: str, *, max_tokens: int = 1800) -> Generator[str, None, None]:
        """Stream AI response chunks via SSE (chat completion providers only).

        Yields plain-text content chunks as they arrive.  Falls back to a
        single-chunk yield for providers that do not support streaming
        (Anthropic, Gemini, OpenAI Responses API).
        """
        effective = self._effective_max_tokens(max_tokens)
        provider = self.config.provider.lower()
        if "openai" in provider:
            # OpenAI Responses API does not support streaming — fall back
            yield self._openai_response(prompt, effective)
            return
        if "deepseek" in provider:
            if self.config.model not in DEEPSEEK_MODELS:
                raise RuntimeError(
                    "Model DeepSeek không hợp lệ. Hãy chọn deepseek-v4-flash hoặc deepseek-v4-pro trong Settings."
                )
            yield from self._chat_completion_stream(
                "https://api.deepseek.com/chat/completions", prompt, effective
            )
            return
        if "anthropic" in provider or "claude" in provider:
            yield self._anthropic_message(prompt, effective)
            return
        if "gemini" in provider or "google" in provider:
            yield self._gemini_generate_content(prompt)
            return
        yield from self._chat_completion_stream(
            "https://api.openai.com/v1/chat/completions", prompt, effective
        )

    def _effective_max_tokens(self, requested: int) -> int:
        """Return a safe max_tokens floor for reasoning-heavy models."""
        floor = _REASONING_MODEL_MIN_TOKENS.get(self.config.model, 0)
        return max(requested, floor)

    def _openai_response(self, prompt: str, max_tokens: int = 1800) -> str:
        payload = {
            "model": self.config.model,
            "input": prompt,
            "max_output_tokens": max_tokens,
        }
        data = self._post_json(
            "https://api.openai.com/v1/responses",
            payload,
            {"Authorization": f"Bearer {self.config.api_key}"},
        )
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

    def _chat_completion(self, url: str, prompt: str, max_tokens: int = 1800) -> str:
        payload = {
            "model": self.config.model,
            "messages": [
                {
                    "role": "system",
                    "content": "Bạn là AI Writer của AI Market Analyst. Không tự bịa số liệu; chỉ diễn giải dữ liệu do app cung cấp.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        data = self._post_json(url, payload, {"Authorization": f"Bearer {self.config.api_key}"})
        content = self._extract_chat_completion_text(data)
        if content:
            return content
        raise RuntimeError(self._chat_completion_empty_reason(data))

    def _chat_completion_stream(self, url: str, prompt: str, max_tokens: int = 1800) -> Generator[str, None, None]:
        """Stream chat completion chunks via SSE."""
        from services.sse_parser import iter_chat_completion_chunks

        payload = {
            "model": self.config.model,
            "messages": [
                {
                    "role": "system",
                    "content": "Bạn là AI Writer của AI Market Analyst. Không tự bịa số liệu; chỉ diễn giải dữ liệu do app cung cấp.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
            "stream": True,
        }
        try:
            response = requests.post(
                url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.config.api_key}",
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

    def _extract_chat_completion_text(self, data: dict[str, object]) -> str:
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

    def _text_from_chat_value(self, value: object) -> str:
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
            return "\n".join(part.strip() for part in parts if part and part.strip()).strip()
        return ""

    def _chat_completion_empty_reason(self, data: dict[str, object]) -> str:
        choices = data.get("choices", [])
        if not isinstance(choices, list) or not choices:
            return "AI không trả về lựa chọn phản hồi. Hãy thử lại hoặc kiểm tra model trong Settings."
        choice = choices[0] if choices else {}
        if not isinstance(choice, dict):
            return "AI trả về phản hồi không đúng định dạng."
        finish_reason = str(choice.get("finish_reason") or "").strip()
        if finish_reason == "content_filter":
            return "AI đã chặn nội dung phản hồi theo bộ lọc an toàn."
        if finish_reason == "length":
            return "AI hết giới hạn token trước khi tạo được nội dung. Hãy thử lại với model deepseek-v4-pro hoặc giảm độ dài dữ liệu phân tích."
        if finish_reason == "insufficient_system_resource":
            return "DeepSeek báo thiếu tài nguyên suy luận tạm thời. Hãy thử lại sau ít phút."
        if finish_reason == "tool_calls":
            return "AI yêu cầu tool call nhưng ứng dụng không bật chế độ tool cho nhận định."
        if finish_reason:
            return f"AI không trả về nội dung phân tích. finish_reason={finish_reason}."
        return "AI không trả về nội dung phân tích."

    def _anthropic_message(self, prompt: str, max_tokens: int = 1800) -> str:
        payload = {
            "model": self.config.model,
            "max_tokens": max_tokens,
            "system": "Bạn là AI Writer của AI Market Analyst. Không tự bịa số liệu; chỉ diễn giải dữ liệu do app cung cấp.",
            "messages": [{"role": "user", "content": prompt}],
        }
        data = self._post_json(
            "https://api.anthropic.com/v1/messages",
            payload,
            {
                "x-api-key": self.config.api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        texts = [item.get("text", "") for item in data.get("content", []) if item.get("type") == "text"]
        if texts:
            return "\n".join(texts).strip()
        raise RuntimeError("AI không trả về nội dung phân tích.")

    def _gemini_generate_content(self, prompt: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.config.model}:generateContent?key={self.config.api_key}"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                "Bạn là AI Writer của AI Market Analyst. Không tự bịa số liệu; "
                                "chỉ diễn giải dữ liệu do app cung cấp.\n\n" + prompt
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1800},
        }
        data = self._post_json(url, payload, {})
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            texts = [part.get("text", "") for part in parts if part.get("text")]
            if texts:
                return "\n".join(texts).strip()
        raise RuntimeError("AI không trả về nội dung phân tích.")

    def _post_json(self, url: str, payload: dict[str, object], headers: dict[str, str]) -> dict[str, object]:
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
            raise RuntimeError(f"AI API lỗi HTTP {exc.code}: {detail[:300]}") from exc
        except URLError as exc:
            raise RuntimeError(f"Không kết nối được AI API: {exc.reason}") from exc
