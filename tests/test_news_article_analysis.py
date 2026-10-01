"""Prompt "Phân tích bài viết" — hợp đồng hàm thuần (Owner yêu cầu 30/09/2026).

Khung prompt là chủ sở hữu của module này (L1/S1): dựng từ đúng dữ kiện của tin
(giờ đăng, nguồn, loại, tiêu đề, đồng tiền, nội dung), yêu cầu AI phân tích NGẮN
GỌN và luôn nói tin liên quan đồng tiền nào + có thể tác động ra sao.  Kết quả là
tư vấn tham khảo, không lưu (§9.2).
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from core.article_analysis import build_analysis_prompt
from core.news_models import (
    ImpactHint,
    NewsItem,
    NewsItemKind,
    NewsItemSource,
)

MODULE_PATH = Path(inspect.getfile(build_analysis_prompt))


def _item(**overrides) -> NewsItem:
    base = dict(
        kind=NewsItemKind.HEADLINE,
        source=NewsItemSource.GOOGLE_NEWS_RSS,
        title="Fed signals patience",
        content="Powell said the committee can wait.",
        url="https://example.com/fed",
        published_utc="2026-09-21T08:00:00Z",
        currencies=["USD", "EUR"],
        impact_hint=ImpactHint.MEDIUM,
        dedupe_key="item-1",
        fetched_at="2026-09-21T09:00:00Z",
        id=11,
    )
    base.update(overrides)
    return NewsItem(**base)


class TestPromptContent:
    def test_prompt_prints_the_item_fields(self):
        text = build_analysis_prompt(_item())

        assert "- time (UTC): 2026-09-21T08:00:00Z" in text
        assert "- source: google_news_rss" in text
        assert "- kind: headline" in text
        assert "- headline: Fed signals patience" in text
        assert "- currencies named by the outlet: USD, EUR" in text
        assert "- body: Powell said the committee can wait." in text

    def test_prompt_asks_for_a_short_read_naming_the_currencies(self):
        text = build_analysis_prompt(_item())

        assert "three to five sentences" in text
        assert "which currencies it concerns and how it could move them" in text

    def test_prompt_forbids_inventing_and_advice(self):
        text = build_analysis_prompt(_item())

        assert "Never invent figures, dates or quotations" in text
        assert "never investment advice" in text

    def test_missing_fields_print_a_dash(self):
        text = build_analysis_prompt(_item(content=None, currencies=[]))

        assert "- body: -" in text
        assert "- currencies named by the outlet: -" in text


class TestPurityAndLayerBoundary:
    def _source(self) -> str:
        return MODULE_PATH.read_text(encoding="utf-8")

    def test_module_source_is_ascii(self):
        assert self._source().isascii()

    def test_module_is_a_pure_function_with_no_state(self):
        assert list(inspect.signature(build_analysis_prompt).parameters) == ["item"]

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
