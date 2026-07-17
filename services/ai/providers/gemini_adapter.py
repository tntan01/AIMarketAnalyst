"""Gemini provider adapter — Google Generative Language REST API (v1beta)."""

from __future__ import annotations

import json
import time as _time
from collections.abc import Generator
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from services.ai.provider_adapter import BaseProviderAdapter
from services.ai.provider_catalog import ProviderCapability, ProviderInfo, provider_catalog

GEMINI_REST_BASE = "https://generativelanguage.googleapis.com/v1beta"
_GEMINI_MODELS_CACHE: dict[str, Any] = {}  # api_key_prefix -> {"models": [...], "ts": float}


class GeminiAdapter(BaseProviderAdapter):
    @staticmethod
    def provider_name() -> str:
        return "gemini"

    # -- Generate ------------------------------------------------------------

    def generate(self, prompt: str, model: str, api_key: str, max_tokens: int) -> str:
        url = f"{GEMINI_REST_BASE}/models/{model}:generateContent?key={api_key}"
        payload = {
            "systemInstruction": {
                "role": "user",
                "parts": [{"text": self.SYSTEM_PROMPT_TEXT}],
            },
            "contents": [
                {"role": "user", "parts": [{"text": prompt}]},
            ],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": max_tokens},
        }
        try:
            data = self._post_json(url, payload, {})
        except RuntimeError as exc:
            raise RuntimeError(
                self.friendly_error(model, str(exc))
            ) from exc

        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            texts = [part.get("text", "") for part in parts if part.get("text")]
            if texts:
                return "\n".join(texts).strip()

        feedback = data.get("promptFeedback", {})
        if feedback.get("blockReason"):
            raise RuntimeError(
                f"Gemini chặn nội dung: {feedback.get('blockReason')}. "
                "Hãy thử lại với prompt khác."
            )
        raise RuntimeError("AI không trả về nội dung phân tích.")

    # -- Model discovery -----------------------------------------------------

    def discover_models(self, api_key: str) -> list[dict[str, object]]:
        """Fetch text-generation models from Gemini REST API.  Cached 30 min.

        Raises :class:`RuntimeError` on API error so the UI can show the
        specific failure reason.
        """
        prefix = api_key[:8] if len(api_key) >= 8 else api_key
        cached = _GEMINI_MODELS_CACHE.get(prefix)
        if cached and _time.time() - cached["ts"] < 1800:
            return list(cached["models"])

        url = f"{GEMINI_REST_BASE}/models?key={api_key}"
        try:
            req = Request(url, method="GET")
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(
                self.friendly_error("", f"HTTP {exc.code}: {detail[:300]}")
            ) from exc
        except Exception as exc:
            raise RuntimeError(
                f"Không kết nối được Gemini API: {exc}"
            ) from exc

        models: list[dict[str, object]] = []
        for m in data.get("models", []):
            methods = m.get("supportedGenerationMethods", [])
            if "generateContent" not in methods:
                continue
            name = str(m.get("name", ""))
            if name.startswith("models/"):
                name = name[7:]
            models.append({
                "name": name,
                "display_name": str(m.get("displayName", name)),
                "description": str(m.get("description", "")),
            })

        _GEMINI_MODELS_CACHE[prefix] = {"models": list(models), "ts": _time.time()}
        return models

    # -- Error handling ------------------------------------------------------

    def friendly_error(self, model: str, raw_message: str) -> str:
        """Translate Gemini REST API errors into Vietnamese."""
        msg_lower = raw_message.lower()

        if "404" in raw_message or "not found" in msg_lower or "no longer available" in msg_lower:
            return (
                f"Model Gemini \"{model}\" không còn khả dụng hoặc đã bị Google ngừng hỗ trợ.\n\n"
                "Hành động đề xuất:\n"
                "1. Vào Settings > AI > chọn model Gemini mới hơn (vd: gemini-3.5-flash).\n"
                "2. Nếu chưa có model mới trong danh sách, bấm nút Làm mới model.\n"
                "3. Kiểm tra https://ai.google.dev/gemini-api/docs/models để xem model khả dụng."
            )

        if "403" in raw_message or "permission" in msg_lower or "unregistered" in msg_lower:
            if "unregistered" in msg_lower:
                return (
                    "API Key Gemini không hợp lệ hoặc thiếu quyền truy cập.\n"
                    "Hãy kiểm tra lại API Key trong Settings > AI."
                )
            return (
                "API Key Gemini bị từ chối truy cập (HTTP 403).\n"
                "Hãy kiểm tra:\n"
                "• API Key còn hạn sử dụng không\n"
                "• API Key có quyền truy cập Generative Language API không\n"
                "• API Key được tạo tại https://aistudio.google.com/apikey"
            )

        if "401" in raw_message or "unauthorized" in msg_lower:
            return (
                "API Key Gemini không được xác thực (HTTP 401).\n"
                "Hãy kiểm tra API Key trong Settings > AI."
            )

        if "429" in raw_message or "quota" in msg_lower or "rate limit" in msg_lower:
            return (
                "Đã vượt giới hạn gọi API Gemini (HTTP 429).\n"
                "Hãy đợi vài phút rồi thử lại, hoặc kiểm tra quota trong Google AI Studio."
            )

        return raw_message


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

provider_catalog.register(
    ProviderInfo(
        name="gemini",
        display_name="Gemini",
        capabilities=(
            ProviderCapability.CHAT
            | ProviderCapability.MODEL_DISCOVERY
            | ProviderCapability.SYSTEM_PROMPT
            | ProviderCapability.VISION
        ),
        default_models=("gemini-3.5-flash", "gemini-3.1-pro-preview", "gemini-3-flash-preview"),
        locked_models=False,
        adapter_class=GeminiAdapter,
    )
)
