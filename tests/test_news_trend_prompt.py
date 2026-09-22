"""Pure tests for the AI trend-prompt builder (contract §9.1 bước 3, plan lô L3.1).

``core/trend_prompt_builder.py`` is the registered owner of "dựng prompt nhận
định xu hướng" (contract §11b).  Its contract, verified here:

* the prompt carries every mandatory element: the scope, the data window, the
  three horizons **as the policy declares them** (unit kept, not converted),
  one line per domain row with its id, and the bare-JSON answer contract with
  the frozen direction/confidence values;
* ``prompt_hash`` is the hash of the FRAME (contract §4.5): editing the template,
  or re-defining a horizon, changes it; new rows, new ids, a new window or a new
  scope never do;
* ``input_snapshot`` carries exactly the window and the counts of §4.5;
* the ``ai_min_items`` floor of §9.1 bước 2 is enforced in this one place - below
  it no prompt exists (fail-closed, B4) - and the three ``ai_*`` keys arrive as
  parameters (R4: the module loads nothing);
* the module stays pure and layer-clean: stdlib + ``core.news_models`` +
  ``core.news_policy`` only, ASCII source, no Qt/network/clock beyond ``now``.

Khuôn test: no mock, no Qt, no I/O - every fixture is a plain domain model.
"""

from __future__ import annotations

import ast
import inspect
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from core import trend_prompt_builder as builder
from core.news_models import (
    CalendarEvent,
    EventImpact,
    EventSource,
    EventStatus,
    NewsItem,
    NewsItemKind,
    NewsItemSource,
)
from core.news_policy import HorizonDefinition
from core.trend_prompt_builder import TrendPromptOutcome, build_trend_prompt

BUILDER_PY = Path(builder.__file__)
NOW = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)


def _horizons(
    short: tuple[str, int, int] = ("day", 0, 3),
    mid: tuple[str, int, int] = ("week", 1, 4),
    long: tuple[str, int, int] = ("month", 1, 6),
) -> dict[str, HorizonDefinition]:
    return {
        "short": HorizonDefinition(*short),
        "mid": HorizonDefinition(*mid),
        "long": HorizonDefinition(*long),
    }


def _event(row_id: int | None = 11, **overrides: object) -> CalendarEvent:
    data: dict[str, object] = {
        "day_key": "2026-09-20",
        "event_time_utc": "2026-09-20T14:30:00Z",
        "currency": "USD",
        "title": "FOMC Meeting",
        "impact": EventImpact.HIGH,
        "status": EventStatus.SCHEDULED,
        "source": EventSource.FF_JSON,
        "dedupe_key": "event-11",
        "fetched_at": "2026-09-20T00:00:00Z",
        "id": row_id,
    }
    data.update(overrides)
    return CalendarEvent(**data)  # type: ignore[arg-type]


def _item(row_id: int | None = 22, **overrides: object) -> NewsItem:
    data: dict[str, object] = {
        "kind": NewsItemKind.HEADLINE,
        "source": NewsItemSource.GOOGLE_NEWS_RSS,
        "title": "Fed signals patience",
        "published_utc": "2026-09-21T08:00:00Z",
        "currencies": ["USD"],
        "dedupe_key": "item-22",
        "fetched_at": "2026-09-21T09:00:00Z",
        "id": row_id,
    }
    data.update(overrides)
    return NewsItem(**data)  # type: ignore[arg-type]


def _build(
    events: list[CalendarEvent] | None = None,
    items: list[NewsItem] | None = None,
    *,
    scope_type: str = "pair",
    scope_value: str = "EUR/USD",
    now: datetime = NOW,
    window_days: int = 7,
    horizons: dict[str, HorizonDefinition] | None = None,
    min_items: int = 2,
) -> TrendPromptOutcome:
    return build_trend_prompt(
        scope_type=scope_type,
        scope_value=scope_value,
        events=events if events is not None else [_event()],
        items=items if items is not None else [_item()],
        now=now,
        window_days=window_days,
        horizons=horizons if horizons is not None else _horizons(),
        min_items=min_items,
    )


# ---- 1. prompt ổn định + hash của KHUÔN ----------------------------------------


class TestPromptStabilityAndHash:
    def test_same_input_gives_the_same_prompt_and_hash(self):
        first = _build()
        second = _build()

        assert first.prompt is not None and second.prompt is not None
        assert first.prompt.text == second.prompt.text
        assert first.prompt.prompt_hash == second.prompt.prompt_hash

    def test_hash_ignores_the_news_data(self):
        """§4.5: hash khuôn, KHÔNG hash dữ liệu — đổi tin/sự kiện/id/cửa sổ/phạm vi
        thì hash giữ nguyên, còn prompt thì đổi."""
        base = _build()
        other = _build(
            events=[_event(row_id=101, title="ECB Press Conference", currency="EUR")],
            items=[_item(row_id=202, title="Lagarde hints at a cut")],
            scope_value="GBP/JPY",
            now=NOW - timedelta(days=30),
            window_days=3,
        )

        assert base.prompt is not None and other.prompt is not None
        assert base.prompt.prompt_hash == other.prompt.prompt_hash
        assert base.prompt.text != other.prompt.text

    def test_hash_changes_when_the_template_changes(self, monkeypatch):
        before = _build()

        monkeypatch.setattr(
            builder, "_PROMPT_TEMPLATE", builder._PROMPT_TEMPLATE + "\nExtra rule."
        )
        after = _build()

        assert before.prompt is not None and after.prompt is not None
        assert after.prompt.prompt_hash != before.prompt.prompt_hash

    def test_hash_changes_when_a_horizon_definition_changes(self):
        before = _build()
        after = _build(horizons=_horizons(short=("day", 0, 5)))

        assert before.prompt is not None and after.prompt is not None
        assert after.prompt.prompt_hash != before.prompt.prompt_hash

    def test_frame_holds_no_row_data(self):
        """Bằng chứng máy đọc: khuôn (thứ được hash) không chứa dữ liệu tin."""
        frame = builder._skeleton(_horizons())

        assert "Fed signals patience" not in frame
        assert "FOMC Meeting" not in frame
        assert "2026-09-20T14:30:00Z" not in frame
        assert "EUR/USD" not in frame
        # ... but the frame itself is in there, with its horizon framing.
        assert builder._PROMPT_TEMPLATE in frame
        assert "short|day|0|3" in frame

    def test_prompt_hash_is_a_stable_hex_digest(self):
        prompt = _build().prompt

        assert prompt is not None
        assert len(prompt.prompt_hash) == 64
        assert set(prompt.prompt_hash) <= set("0123456789abcdef")


# ---- 2. ngưỡng ai_min_items (fail-closed, §9.1 bước 2) -------------------------


class TestInsufficientData:
    def test_below_the_floor_no_prompt_is_built(self):
        outcome = _build(events=[_event()], items=[], min_items=2)

        assert outcome.insufficient_data is True
        assert outcome.prompt is None
        assert (outcome.event_count, outcome.item_count, outcome.min_items) == (1, 0, 2)

    def test_exactly_at_the_floor_a_prompt_is_built(self):
        outcome = _build(events=[_event()], items=[_item()], min_items=2)

        assert outcome.insufficient_data is False
        assert outcome.prompt is not None

    def test_empty_data_set_is_insufficient(self):
        outcome = _build(events=[], items=[], min_items=1)

        assert outcome.insufficient_data is True
        assert outcome.prompt is None


# ---- 3. nội dung bắt buộc của prompt -------------------------------------------


class TestPromptContent:
    def _text(self) -> str:
        prompt = _build(
            events=[_event(row_id=11, actual="5.50%", forecast="5.50%", previous="5.25%")],
            items=[_item(row_id=22, content="Powell: patience")],
            min_items=2,
        ).prompt
        assert prompt is not None
        return prompt.text

    def test_prompt_carries_the_scope_and_the_window(self):
        text = self._text()

        assert "pair EUR/USD" in text
        assert "the last 7 day(s)" in text
        assert "2026-09-15T10:00:00Z to 2026-09-22T10:00:00Z" in text

    def test_prompt_declares_the_three_horizons_with_their_policy_units(self):
        text = self._text()

        assert "- short: day 0-3" in text
        assert "- mid: week 1-4" in text
        assert "- long: month 1-6" in text

    def test_prompt_carries_every_row_with_its_id_and_fields(self):
        text = self._text()

        assert "[event #11] 2026-09-20T14:30:00Z | USD | FOMC Meeting | impact=high" in text
        assert "actual=5.50% | forecast=5.50% | previous=5.25%" in text
        assert "[news #22] 2026-09-21T08:00:00Z | USD | headline | Fed signals patience" in text
        assert "content=Powell: patience | source=google_news_rss" in text

    def test_prompt_forbids_inventing_data_and_citation_ids(self):
        text = self._text()

        assert 'Never invent events, numbers, dates, currency' in text
        assert "must be a row id printed in this prompt" in text

    def test_prompt_asks_for_vietnamese_rationale_and_bare_json(self):
        text = self._text()

        assert "Write every rationale in Vietnamese." in text
        assert "no markdown fence" in text
        assert "direction: bullish | bearish | neutral | insufficient_data" in text
        assert "confidence: high | medium | low | none" in text

    def test_prompt_schema_holds_exactly_the_horizon_keys(self):
        text = self._text()

        for key in ("short", "mid", "long"):
            assert f'  "{key}": {{"direction"' in text
        assert '"evidence_item_ids"' in text

    def test_empty_optional_fields_are_rendered_as_a_dash(self):
        prompt = _build(
            events=[_event(actual=None, forecast=None, previous=None)],
            items=[],
            min_items=1,
        ).prompt

        assert prompt is not None
        assert "actual=- | forecast=- | previous=-" in prompt.text


# ---- 4. id dẫn chứng + snapshot ------------------------------------------------


class TestEvidenceAndSnapshot:
    def test_evidence_ids_are_the_printed_rows_in_order(self):
        prompt = _build(
            events=[_event(row_id=11), _event(row_id=12, dedupe_key="e12")],
            items=[_item(row_id=22)],
            min_items=3,
        ).prompt

        assert prompt is not None
        assert prompt.evidence_item_ids == (11, 12, 22)

    def test_row_without_an_id_is_shown_but_not_citable(self):
        prompt = _build(
            events=[_event(row_id=None)],
            items=[_item(row_id=22)],
            min_items=2,
        ).prompt

        assert prompt is not None
        assert prompt.evidence_item_ids == (22,)
        assert "[event #no-id]" in prompt.text

    def test_snapshot_holds_the_window_and_the_counts_only(self):
        prompt = _build(
            events=[_event(), _event(row_id=12, dedupe_key="e12")],
            items=[_item()],
            min_items=1,
        ).prompt

        assert prompt is not None
        assert prompt.snapshot == {
            "window_days": 7,
            "from_utc": "2026-09-15T10:00:00Z",
            "to_utc": "2026-09-22T10:00:00Z",
            "event_count": 2,
            "item_count": 1,
        }

    def test_outcome_reports_counts_even_when_a_prompt_was_built(self):
        outcome = _build(min_items=1)

        assert outcome.insufficient_data is False
        assert (outcome.event_count, outcome.item_count, outcome.min_items) == (1, 1, 1)

    def test_naive_now_is_read_as_utc(self):
        outcome = _build(now=datetime(2026, 9, 22, 10, 0), window_days=1)

        assert outcome.prompt is not None
        assert outcome.prompt.snapshot["to_utc"] == "2026-09-22T10:00:00Z"
        assert outcome.prompt.snapshot["from_utc"] == "2026-09-21T10:00:00Z"

    def test_window_is_not_converted_from_the_horizon_units(self):
        """Cửa sổ tính bằng ngày theo đúng tham số; đơn vị chân trời giữ nguyên."""
        outcome = _build(
            now=datetime(2026, 9, 22, 0, 0, tzinfo=timezone.utc),
            window_days=14,
            horizons=_horizons(mid=("week", 2, 4)),
        )

        assert outcome.prompt is not None
        assert outcome.prompt.snapshot["from_utc"] == "2026-09-08T00:00:00Z"
        assert "- mid: week 2-4" in outcome.prompt.text


# ---- 5. ranh giới lớp + hàm thuần (L1/L2/L3) -----------------------------------


class TestPurityAndLayerBoundary:
    @classmethod
    def _source(cls) -> str:
        return BUILDER_PY.read_text(encoding="utf-8")

    def test_module_imports_nothing_from_services_ui_controllers_or_qt(self):
        source = self._source()
        for forbidden in (
            "import services",
            "from services",
            "import ui",
            "from ui",
            "import controllers",
            "from controllers",
            "import workers",
            "from workers",
            "PyQt6",
            "requests",
            "sqlite3",
        ):
            assert forbidden not in source, f"{forbidden!r} must not appear"

    def test_module_imports_only_stdlib_and_core(self):
        tree = ast.parse(self._source())
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
            elif isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
        modules.discard("__future__")

        assert modules == {
            "hashlib",
            "collections.abc",
            "dataclasses",
            "datetime",
            "core.news_models",
            "core.news_policy",
        }

    def test_module_source_is_ascii_no_vietnamese_display_strings(self):
        assert self._source().isascii(), (
            "core/trend_prompt_builder.py must stay pure ASCII - the prompt is "
            "machine input; Vietnamese labels belong to the presentation tier"
        )

    def test_module_reads_no_policy_and_hard_codes_no_policy_number(self):
        """R4: 3 khóa ai_* là tham số — module không tự nạp chính sách."""
        source = self._source()
        assert "load_news_policy" not in source
        assert "CONFIG_DIR" not in source
        assert "news_policy.json" not in source
        # Số vận hành duy nhất được phép xuất hiện là hằng đơn vị thời gian 0.
        numbers = {
            node.value
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Constant)
            and isinstance(node.value, int)
            and not isinstance(node.value, bool)
            and node.value not in (0, 1)
        }
        assert numbers == set()

    def test_builder_is_a_pure_function_with_no_state(self):
        assert list(inspect.signature(build_trend_prompt).parameters) == [
            "scope_type",
            "scope_value",
            "events",
            "items",
            "now",
            "window_days",
            "horizons",
            "min_items",
        ]
        assert getattr(build_trend_prompt, "__self__", None) is None

    def test_two_calls_do_not_share_mutable_state(self):
        first = _build()
        second = _build()

        assert first.prompt is not None and second.prompt is not None
        assert first.prompt.snapshot is not second.prompt.snapshot
        assert first.prompt.evidence_item_ids == second.prompt.evidence_item_ids


@pytest.mark.parametrize("scope_type", ["pair", "currency"])
def test_scope_label_is_rendered_for_both_scope_types(scope_type):
    value = "EUR/USD" if scope_type == "pair" else "JPY"
    outcome = _build(scope_type=scope_type, scope_value=value, min_items=1)

    assert outcome.prompt is not None
    assert f"Scope: {scope_type} {value}" in outcome.prompt.text
