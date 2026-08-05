"""Reusable SSE (Server-Sent Events) stream parser for chat completion APIs.

Yields delta text chunks from a streaming chat completion response.
Works with OpenAI-compatible and DeepSeek endpoints.
"""

from __future__ import annotations

import json
from collections.abc import Generator


def iter_chat_completion_chunks(response, *, content_key: str = "content") -> Generator[str, None, None]:
    """Yield delta text chunks from a streaming chat completion response.

    Only yields actual ``content`` delta text — reasoning/thinking tokens
    are skipped to prevent internal model instructions from appearing in
    the user-visible output.

    Args:
        response: A ``requests.Response`` object with ``stream=True``.
        content_key: Preferred delta key (default ``"content"``).

    Yields:
        Plain-text content chunks as they arrive via SSE.
    """
    # SSE payloads are always UTF-8 (spec), but requests decodes text streams
    # with ISO-8859-1 when the server omits charset in Content-Type — which
    # garbles Vietnamese (e.g. "xin chào" -> "xin chÃ o"). Force UTF-8.
    response.encoding = "utf-8"
    for line in response.iter_lines(decode_unicode=True):
        if not line:
            continue
        if line.startswith("data: "):
            data_str = line[6:]
            if data_str.strip() == "[DONE]":
                return
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                continue
            delta_text = _extract_delta_text(data, content_key=content_key)
            if delta_text:
                yield delta_text


def _extract_delta_text(data: dict, *, content_key: str = "content") -> str:
    """Extract delta text from a single SSE data payload."""
    choices = data.get("choices", [])
    if not isinstance(choices, list) or not choices:
        return ""
    choice = choices[0]
    if not isinstance(choice, dict):
        return ""
    delta = choice.get("delta", {})
    if not isinstance(delta, dict):
        return ""
    text = delta.get(content_key)
    if isinstance(text, str) and text:
        return text
    return ""
