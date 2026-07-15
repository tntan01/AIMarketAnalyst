"""Test SSE parser khong yield reasoning_content vao output hien thi.

Kiem tra:
1. reasoning_content bi bo qua, chi content duoc yield
2. content bình thuong van duoc yield
3. Khong crash khi chi co reasoning_content
"""
from __future__ import annotations

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class MockResponse:
    """Mock requests.Response voi iter_lines de kiem tra SSE parser."""
    def __init__(self, lines: list[str]):
        self._lines = lines

    def iter_lines(self, decode_unicode=True):
        yield from self._lines


def _make_sse_line(data: dict) -> str:
    return f"data: {json.dumps(data)}"


def test_skip_reasoning_content():
    from services.sse_parser import iter_chat_completion_chunks

    errors: list[str] = []

    # ---- Test 1: reasoning_content first, then content ----
    print("[TEST 1] reasoning_content before content: should skip reasoning")
    sse_lines = [
        _make_sse_line({"choices": [{"delta": {"reasoning_content": "Can dam bao ngon ngu phan tich chuyen nghiep..."}}]}),
        _make_sse_line({"choices": [{"delta": {"reasoning_content": "Cau truc bai: dung yeu cau..."}}]}),
        _make_sse_line({"choices": [{"delta": {"content": "## Phan tich"}}]}),
        _make_sse_line({"choices": [{"delta": {"content": " DXY\n- DXY hien tai dang o muc cao..."}}]}),
        "data: [DONE]",
    ]
    response = MockResponse(sse_lines)
    chunks = list(iter_chat_completion_chunks(response))

    reasoning_in_output = any("Can dam bao" in c or "Cau truc bai" in c for c in chunks)
    content_present = any("Phan tich" in c for c in chunks)

    if not reasoning_in_output:
        print(f"  [TEST 1a] PASS: reasoning_content skipped")
    else:
        errors.append("[TEST 1a] FAIL: reasoning_content leaked into output")
        print(f"  [TEST 1a] FAIL: got reasoning in output: {chunks}")

    if content_present:
        print(f"  [TEST 1b] PASS: content chunks yielded: {chunks}")
    else:
        errors.append("[TEST 1b] FAIL: no content chunks")
        print(f"  [TEST 1b] FAIL: got {chunks}")

    # ---- Test 2: content only (no reasoning) ----
    print("[TEST 2] Content only (no reasoning): should yield normally")
    sse_lines = [
        _make_sse_line({"choices": [{"delta": {"content": "Chunk 1"}}]}),
        _make_sse_line({"choices": [{"delta": {"content": "Chunk 2"}}]}),
        "data: [DONE]",
    ]
    response = MockResponse(sse_lines)
    chunks = list(iter_chat_completion_chunks(response))

    if chunks == ["Chunk 1", "Chunk 2"]:
        print(f"  [TEST 2] PASS: {chunks}")
    else:
        errors.append(f"[TEST 2] FAIL: expected ['Chunk 1', 'Chunk 2'], got {chunks}")
        print(f"  [TEST 2] FAIL: got {chunks}")

    # ---- Test 3: only reasoning_content, no content ----
    print("[TEST 3] Only reasoning_content: should yield nothing")
    sse_lines = [
        _make_sse_line({"choices": [{"delta": {"reasoning_content": "thinking..."}}]}),
        _make_sse_line({"choices": [{"delta": {"reasoning_content": "still thinking..."}}]}),
        "data: [DONE]",
    ]
    response = MockResponse(sse_lines)
    chunks = list(iter_chat_completion_chunks(response))

    if chunks == []:
        print(f"  [TEST 3] PASS: no output when only reasoning_content")
    else:
        errors.append(f"[TEST 3] FAIL: expected [], got {chunks}")
        print(f"  [TEST 3] FAIL: got {chunks}")

    # ---- Test 4: empty delta ----
    print("[TEST 4] Empty delta: should skip silently")
    sse_lines = [
        _make_sse_line({"choices": [{"delta": {}}]}),
        _make_sse_line({"choices": [{"delta": {"content": "Real content"}}]}),
        "data: [DONE]",
    ]
    response = MockResponse(sse_lines)
    chunks = list(iter_chat_completion_chunks(response))

    if chunks == ["Real content"]:
        print(f"  [TEST 4] PASS: {chunks}")
    else:
        errors.append(f"[TEST 4] FAIL: expected ['Real content'], got {chunks}")
        print(f"  [TEST 4] FAIL: got {chunks}")

    # ---- Results ----
    if errors:
        print(f"\nFAILED: {len(errors)} error(s)")
        for e in errors:
            print(f"  - {e}")
        return 1
    else:
        print("\nALL TESTS PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(test_skip_reasoning_content())
