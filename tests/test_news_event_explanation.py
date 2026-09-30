"""Prompt giải thích chỉ số của một sự kiện FF — hợp đồng hàm thuần (Owner yêu cầu 30/09/2026).

Khung prompt là chủ sở hữu của module này (L1/S1): dựng từ đúng dữ kiện của sự
kiện, yêu cầu AI chú trọng **tác động tới đồng tiền của sự kiện**, cấm bịa số
liệu và cấm khuyến nghị mua/bán.  Kết quả là tư vấn tham khảo, không lưu (§9.2).
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from core.event_explanation import build_explanation_prompt
from core.news_models import (
    CalendarEvent,
    EventImpact,
    EventSource,
    EventStatus,
)

MODULE_PATH = Path(inspect.getfile(build_explanation_prompt))


def _event(**overrides) -> CalendarEvent:
    base = dict(
        day_key="2026-09-30",
        event_time_utc="2026-09-30T14:55:00Z",
        currency="EUR",
        title="German Unemployment Change",
        impact=EventImpact.HIGH,
        status=EventStatus.RELEASED,
        source=EventSource.FF_HTML,
        dedupe_key="key-1",
        fetched_at="2026-09-30T15:00:00Z",
        previous="4K",
        forecast="1K",
        actual="-2K",
    )
    base.update(overrides)
    return CalendarEvent(**base)


class TestPromptContent:
    def test_prompt_prints_the_event_figures(self):
        text = build_explanation_prompt(_event())

        assert "- currency: EUR" in text
        assert "- indicator: German Unemployment Change" in text
        assert "- impact level: high" in text
        assert "- time (UTC): 2026-09-30T14:55:00Z" in text
        assert "- previous: 4K" in text
        assert "- forecast: 1K" in text
        assert "- actual: -2K" in text

    def test_prompt_demands_the_currency_impact(self):
        text = build_explanation_prompt(_event())

        assert "how this release affects EUR" in text
        assert "above all" in text.lower()
        assert 'impact level\n   "high"' in text

    def test_prompt_forbids_inventing_and_advice(self):
        text = build_explanation_prompt(_event())

        assert "Never invent, estimate or extrapolate" in text
        assert "never tell the reader to buy or\n  sell" in text

    def test_missing_figures_print_a_dash(self):
        text = build_explanation_prompt(_event(actual=None, previous="", forecast="  "))

        assert "- actual: -" in text
        assert "- previous: -" in text
        assert "- forecast: -" in text


class TestPurityAndLayerBoundary:
    def _source(self) -> str:
        return MODULE_PATH.read_text(encoding="utf-8")

    def test_module_source_is_ascii(self):
        # core/ thuần: khung prompt là dữ liệu máy đọc, nhãn tiếng Việt thuộc tầng
        # trình bày (khuôn trend_prompt_builder).
        assert self._source().isascii()

    def test_module_is_a_pure_function_with_no_state(self):
        assert list(inspect.signature(build_explanation_prompt).parameters) == ["event"]

    def test_module_reads_no_policy_and_hard_codes_no_number(self):
        source = self._source()

        assert "load_news_policy" not in source
        assert "news_policy.json" not in source
        numbers = {
            node.value
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Constant)
            and isinstance(node.value, int)
            and not isinstance(node.value, bool)
            and node.value not in (0, 1)
        }
        assert numbers == set()
