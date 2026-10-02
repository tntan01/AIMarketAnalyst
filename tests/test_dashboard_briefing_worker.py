"""BriefingWorker: ngân sách token & fallback khi stream về rỗng.

Regression của lỗi "AI trả về phản hồi rỗng": model suy luận đốt hết ngân sách
vào ``reasoning_content`` (SSE parser cố ý bỏ qua) → stream rỗng → worker phải
fallback sang đường non-stream với ngân sách cao hơn (khuôn news §9.1 — tối đa
2 lần gọi), và báo tin thân thiện khi cả fallback hết ngân sách.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QApplication

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

from services.ai.provider_adapter import AIOutputBudgetError  # noqa: E402
from ui.screens.dashboard_screen import (  # noqa: E402
    _BRIEFING_FALLBACK_MAX_TOKENS,
    _BRIEFING_MAX_TOKENS,
    BriefingWorker,
)


def _make_worker() -> tuple[BriefingWorker, dict[str, list]]:
    worker = BriefingWorker(MagicMock(), market_values={"DXY": (104.2, -0.4)})
    received: dict[str, list] = {
        "status": [],
        "events": [],
        "chunks": [],
        "finished": [],
        "error": [],
    }
    worker.status.connect(received["status"].append)
    worker.events_ready.connect(received["events"].append)
    worker.chunk_ready.connect(received["chunks"].append)
    worker.finished.connect(received["finished"].append)
    worker.error.connect(received["error"].append)
    return worker, received


def _run_worker(ai_instance) -> dict[str, list]:
    worker, received = _make_worker()
    with (
        patch("ui.screens.dashboard_screen._fetch_upcoming_red_events", return_value=[]),
        patch("services.ai_service.AIService", return_value=ai_instance),
    ):
        worker.run()
    return received


def test_stream_with_content_finishes_without_fallback():
    ai = MagicMock()
    ai.analyze_stream.return_value = iter(["### Bối cảnh\n", "USD đi ngang."])

    received = _run_worker(ai)

    assert received["error"] == []
    assert len(received["finished"]) == 1
    assert received["finished"][0]["text"] == "### Bối cảnh\nUSD đi ngang."
    ai.analyze.assert_not_called()

    ai.analyze_stream.assert_called_once()
    assert ai.analyze_stream.call_args.kwargs.get("max_tokens") == _BRIEFING_MAX_TOKENS


def test_empty_stream_falls_back_to_non_stream_with_raised_budget():
    ai = MagicMock()
    ai.analyze_stream.return_value = iter([])
    ai.analyze.return_value = "Bản tin dự phòng đầy đủ."

    received = _run_worker(ai)

    assert received["error"] == []
    assert len(received["finished"]) == 1
    assert received["finished"][0]["text"] == "Bản tin dự phòng đầy đủ."

    ai.analyze.assert_called_once()
    assert ai.analyze.call_args.kwargs.get("max_tokens") == _BRIEFING_FALLBACK_MAX_TOKENS
    # Fallback text vẫn được emit như chunk để UI render ngay
    assert "Bản tin dự phòng đầy đủ." in received["chunks"]


def test_budget_error_after_empty_stream_reports_friendly_message():
    ai = MagicMock()
    ai.analyze_stream.return_value = iter([])
    ai.analyze.side_effect = AIOutputBudgetError(
        "AI hết giới hạn token trước khi tạo được nội dung."
    )

    received = _run_worker(ai)

    assert received["finished"] == []
    assert len(received["error"]) == 1
    assert "hết giới hạn token" in received["error"][0]
    assert "đổi model" in received["error"][0]


def test_provider_error_propagates_as_error():
    ai = MagicMock()
    ai.analyze_stream.side_effect = RuntimeError("Không kết nối được AI API: timeout")

    received = _run_worker(ai)

    assert received["finished"] == []
    assert received["error"] == ["Không kết nối được AI API: timeout"]
