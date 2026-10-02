"""Prompt bản tin AI: giờ sự kiện theo múi giờ hiển thị của Settings.

Regression: trước đây prompt luôn in giờ UTC khiến AI nói lệch với Countdown
hiển thị trên UI (đã convert sang múi giờ Settings). Prompt phải cùng múi giờ.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from ui.screens.dashboard_screen import _build_briefing_prompt

HCM = ZoneInfo("Asia/Ho_Chi_Minh")


def _event(when: datetime) -> dict:
    return {
        "currency": "USD",
        "event": "Non-Farm Payrolls",
        "display_time": when,
        "time_utc": "2026-10-02T12:30:00Z",
        "forecast": "140K",
        "previous": "150K",
    }


def test_prompt_converts_event_time_to_settings_timezone():
    events = [_event(datetime(2026, 10, 2, 12, 30, tzinfo=timezone.utc))]
    prompt = _build_briefing_prompt({}, events, tz=HCM)

    # 12:30 UTC == 19:30 giờ Asia/Ho_Chi_Minh
    assert "lúc 02/10 19:30" in prompt
    assert "giờ Asia/Ho_Chi_Minh" in prompt


def test_prompt_keeps_utc_when_no_timezone_passed():
    events = [_event(datetime(2026, 10, 2, 12, 30, tzinfo=timezone.utc))]
    prompt = _build_briefing_prompt({}, events, tz=None)

    assert "giờ UTC" in prompt
    assert "lúc 02/10 12:30" in prompt


def test_prompt_treats_naive_event_time_as_utc():
    events = [_event(datetime(2026, 10, 2, 12, 30))]
    prompt = _build_briefing_prompt({}, events, tz=HCM)

    assert "lúc 02/10 19:30" in prompt


def test_prompt_includes_creation_timestamp_in_settings_timezone():
    prompt = _build_briefing_prompt({}, [], tz=HCM)

    assert "Thời điểm tạo bản tin" in prompt
    assert "giờ Asia/Ho_Chi_Minh" in prompt
