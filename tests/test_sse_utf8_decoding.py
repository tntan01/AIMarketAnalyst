"""Test SSE streaming always decodes UTF-8 correctly (Vietnamese).

Root cause: ``requests`` decodes text streams with ISO-8859-1 when the
server omits ``charset`` in ``Content-Type``, so UTF-8 bytes arrive garbled
("xin chào" -> "xin chÃ o").  The fix forces ``response.encoding = "utf-8"``
in ``services/sse_parser.iter_chat_completion_chunks`` before iterating.

This test mocks an SSE stream whose bytes are UTF-8 but whose response
carries NO charset declaration (requests' default ISO-8859-1), and verifies
the parser output is the correct Vietnamese string.

Run directly:  python tests/test_sse_utf8_decoding.py
  → prints per-check results and a final ✅ PASS / ❌ FAIL.
Also runnable under pytest.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# UTF-8 encoded SSE stream with Vietnamese delta content, no charset declared
SSE_VIETNAMESE_BYTES = (
    'data: {"choices":[{"delta":{"content":"xin chào bạn"}}]}\n\n'
    'data: {"choices":[{"delta":{"content":", tôi là AI."}}]}\n\n'
    'data: [DONE]\n'
).encode("utf-8")


class FakeNoCharsetResponse:
    """Mimics ``requests.Response.iter_lines(decode_unicode=True)``.

    Decodes the raw UTF-8 bytes using ``self.encoding or "utf-8"`` — exactly
    what requests' ``stream_decode_response_unicode`` does.  ``encoding``
    starts as ISO-8859-1 to simulate a server that omits charset in
    Content-Type (requests' default for text bodies).
    """

    encoding = "ISO-8859-1"

    def __init__(self, raw_bytes: bytes) -> None:
        self._raw = raw_bytes

    def iter_lines(self, decode_unicode=True):
        text = self._raw.decode(self.encoding or "utf-8", errors="replace")
        yield from text.splitlines()


def test_vietnamese_sse_decodes_utf8_without_charset():
    from services.sse_parser import iter_chat_completion_chunks

    response = FakeNoCharsetResponse(SSE_VIETNAMESE_BYTES)
    chunks = list(iter_chat_completion_chunks(response))
    output = "".join(chunks)
    assert output == "xin chào bạn, tôi là AI.", f"got: {output!r}"


def test_vietnamese_sse_works_through_adapter_stream():
    """The OpenAI Compatible adapter's SSE path uses the same parser."""
    from unittest.mock import patch

    from services.ai.providers.openai_compatible_adapter import OpenAICompatibleAdapter

    fake_resp = FakeNoCharsetResponse(SSE_VIETNAMESE_BYTES)
    fake_resp.status_code = 200

    with patch("services.ai.providers.openai_compatible_adapter.requests.post",
               return_value=fake_resp):
        chunks = list(OpenAICompatibleAdapter().generate_stream(
            "p", "m", "k", 50, base_url="http://localhost:1234/v1",
        ))
    assert "".join(chunks) == "xin chào bạn, tôi là AI."


def test_same_bytes_garble_under_iso8859_default():
    """Control: the identical UTF-8 bytes decode to mojibake under
    ISO-8859-1 (requests' default when no charset is declared) — proving the
    mock reproduces the real defect that the UTF-8 fix eliminates."""
    raw = FakeNoCharsetResponse(SSE_VIETNAMESE_BYTES)._raw
    # ISO-8859-1 maps byte 0xA0 to U+00A0 (no-break space); normalize it so the
    # mojibake matches the user-visible symptom "xin chÃ o báº¡n".
    garbled = raw.decode("ISO-8859-1", errors="replace").replace("\xa0", " ")
    assert "chÃ o báº¡n" in garbled, "control: ISO-8859-1 must garble Vietnamese"
    assert "xin chào bạn" not in garbled
    clean = raw.decode("utf-8", errors="replace")
    assert "xin chào bạn" in clean


# ---------------------------------------------------------------------------
# Runner — prints ✅ PASS / ❌ FAIL
# ---------------------------------------------------------------------------

_CHECKS = [
    test_vietnamese_sse_decodes_utf8_without_charset,
    test_vietnamese_sse_works_through_adapter_stream,
    test_same_bytes_garble_under_iso8859_default,
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