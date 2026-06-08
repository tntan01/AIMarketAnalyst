from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config.constants import DEEPSEEK_MODELS


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

    def analyze(self, prompt: str) -> str:
        provider = self.config.provider.lower()
        if "openai" in provider:
            return self._openai_response(prompt)
        if "deepseek" in provider:
            if self.config.model not in DEEPSEEK_MODELS:
                raise RuntimeError(
                    "Model DeepSeek không hợp lệ. Hãy chọn deepseek-v4-flash hoặc deepseek-v4-pro trong Settings."
                )
            return self._chat_completion("https://api.deepseek.com/chat/completions", prompt)
        if "anthropic" in provider or "claude" in provider:
            return self._anthropic_message(prompt)
        if "gemini" in provider or "google" in provider:
            return self._gemini_generate_content(prompt)
        return self._chat_completion("https://api.openai.com/v1/chat/completions", prompt)

    def _openai_response(self, prompt: str) -> str:
        payload = {
            "model": self.config.model,
            "input": prompt,
            "max_output_tokens": 1800,
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

    def _chat_completion(self, url: str, prompt: str) -> str:
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
            "max_tokens": 1800,
        }
        data = self._post_json(url, payload, {"Authorization": f"Bearer {self.config.api_key}"})
        content = self._extract_chat_completion_text(data)
        if content:
            return content
        raise RuntimeError(self._chat_completion_empty_reason(data))

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
            return "AI khong tra ve lua chon phan hoi. Hay thu lai hoac kiem tra model trong Settings."
        choice = choices[0] if choices else {}
        if not isinstance(choice, dict):
            return "AI tra ve phan hoi khong dung dinh dang."
        finish_reason = str(choice.get("finish_reason") or "").strip()
        if finish_reason == "content_filter":
            return "AI da chan noi dung phan hoi theo bo loc an toan."
        if finish_reason == "length":
            return "AI het gioi han token truoc khi tao duoc noi dung. Hay thu lai voi model deepseek-v4-pro hoac giam do dai du lieu phan tich."
        if finish_reason == "insufficient_system_resource":
            return "DeepSeek bao thieu tai nguyen suy luan tam thoi. Hay thu lai sau it phut."
        if finish_reason == "tool_calls":
            return "AI yeu cau tool call nhung ung dung khong bat che do tool cho nhan dinh."
        if finish_reason:
            return f"AI khong tra ve noi dung phan tich. finish_reason={finish_reason}."
        return "AI khong tra ve noi dung phan tich."

    def _anthropic_message(self, prompt: str) -> str:
        payload = {
            "model": self.config.model,
            "max_tokens": 1800,
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
            with urlopen(request, timeout=45) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"AI API lỗi HTTP {exc.code}: {detail[:300]}") from exc
        except URLError as exc:
            raise RuntimeError(f"Không kết nối được AI API: {exc.reason}") from exc
