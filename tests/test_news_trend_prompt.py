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
    RateObservation,
    RateSource,
)
from core.news_policy import HorizonDefinition
from core.rate_trend import RatePath, RateTrend
from core.trend_prompt_builder import (
    HorizonWindowSet,
    MarketContext,
    TrendPromptOutcome,
    WindowRows,
    build_trend_prompt,
    select_rows_for_windows,
)
from core.yield_context import YieldContext, YieldDeltaSet
from services.news_repository import CurrencyRateTrend

BUILDER_PY = Path(builder.__file__)
NOW = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)


def _rows_from(
    events: list[CalendarEvent], items: list[NewsItem]
) -> WindowRows:
    """A WindowRows with the same rows in every window (test convenience)."""
    return WindowRows(
        short_events=tuple(events),
        short_items=tuple(items),
        mid_events=tuple(events),
        mid_items=tuple(items),
        long_events=tuple(events),
        long_items=tuple(items),
    )


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


def _rate_context(
    currency: str = "USD",
    rate: float = 5.5,
    observed_at: str = "2026-09-18",
    trend: RateTrend = RateTrend.HOLD,
) -> CurrencyRateTrend:
    return CurrencyRateTrend(
        currency=currency,
        latest=RateObservation(
            currency=currency,
            rate=rate,
            observed_at=observed_at,
            source=RateSource.FRED,
            fetched_at="2026-09-19T00:00:00Z",
            id=1,
        ),
        previous=None,
        trend=trend,
    )


def _yield_context(**overrides: object) -> YieldContext:
    data: dict[str, object] = {
        "yield_2y": 3.72,
        "observed_at_2y": "2026-09-18",
        "yield_10y": 3.91,
        "observed_at_10y": "2026-09-18",
        "be10y": 2.36,
        "observed_at_be10y": "2026-09-18",
        "delta_2y": -0.08,
        "delta_10y": 0.02,
        "spread_2y10y": 0.19,
        "real_yield_10y": 1.55,
    }
    data.update(overrides)
    return YieldContext(**data)  # type: ignore[arg-type]


def _rate_path(
    rate_now: float | None = 5.50,
    rate_then: float | None = 5.00,
    change: float | None = 0.50,
) -> RatePath:
    return RatePath(rate_now=rate_now, rate_then=rate_then, change=change)


def _build(
    events: list[CalendarEvent] | None = None,
    items: list[NewsItem] | None = None,
    *,
    rows: WindowRows | None = None,
    scope_type: str = "pair",
    scope_value: str = "EUR/USD",
    context: MarketContext | None = None,
    now: datetime = NOW,
    window_days: int = 7,
    horizon_windows: HorizonWindowSet | None = None,
    long_max_rows: int = 50,
    horizons: dict[str, HorizonDefinition] | None = None,
    min_items: int = 2,
) -> TrendPromptOutcome:
    if rows is None:
        rows = _rows_from(
            events if events is not None else [_event()],
            items if items is not None else [_item()],
        )
    return build_trend_prompt(
        scope_type=scope_type,
        scope_value=scope_value,
        rows=rows,
        context=context if context is not None else MarketContext(),
        now=now,
        window_days=window_days,
        horizon_windows=(
            horizon_windows if horizon_windows is not None else _windows()
        ),
        long_max_rows=long_max_rows,
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

    def test_the_frame_hash_is_pinned(self):
        # The frame re-hashed once per sanctioned amendment: C5 (đợt 5) added the
        # market-context block, C3 (đợt 6) the wave-6 frame (3 window sections +
        # status + coverage rule + rate path/deltas), and lô A of the ca "Nhận
        # định AI — độ bền kết quả" (đợt 7) removed the "#" from the row-id label
        # and spelled out that evidence ids are plain integers (a stray "#" inside
        # the JSON array made the model's answer unparseable).  This pins the
        # value so any later accidental frame edit is red.
        prompt = _build().prompt

        assert prompt is not None
        assert (
            prompt.prompt_hash
            == "766db7e27126393cc4ebd78a1578cb54a2930e630a86bb586bd665e921053e68"
        )

    def test_hash_is_independent_of_the_market_context(self):
        # The hash covers the frame, never the data: different contexts (even
        # none) keep the same hash while the rendered prompt differs.
        empty = _build(context=MarketContext()).prompt
        full = _build(
            context=MarketContext(
                rates=(_rate_context(),),
                yields=_yield_context(),
                rate_path=_rate_path(),
            )
        ).prompt

        assert empty is not None and full is not None
        assert empty.prompt_hash == full.prompt_hash
        assert "market context: none" in empty.text
        assert "policy rate USD" in full.text


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

        assert "[event 11] 2026-09-20T14:30:00Z | USD | FOMC Meeting | impact=high" in text
        assert "| status=scheduled |" in text
        assert "actual=5.50% | forecast=5.50% | previous=5.25%" in text
        assert "[news 22] 2026-09-21T08:00:00Z | USD | headline | Fed signals patience" in text
        assert "content=Powell: patience | source=google_news_rss" in text

    def test_prompt_carries_the_three_window_sections(self):
        text = self._text()

        assert "Data - short window, 7 days (1 event(s), 1 news item(s)):" in text
        assert "Data - mid window, 42 days (1 event(s), 1 news item(s)):" in text
        assert (
            "Data - long window, 180 days, top 50 rows (1 event(s), 1 news item(s)):"
            in text
        )

    def test_empty_window_keeps_its_header_with_zero_count(self):
        rows = WindowRows(
            short_events=(_event(row_id=11),),
            short_items=(),
            mid_events=(),
            mid_items=(),
            long_events=(),
            long_items=(),
        )
        prompt = _build(rows=rows, min_items=1).prompt

        assert prompt is not None
        assert "Data - short window, 7 days (1 event(s), 0 news item(s)):" in prompt.text
        assert "Data - mid window, 42 days (0 event(s), 0 news item(s)):" in prompt.text
        assert (
            "Data - long window, 180 days, top 50 rows (0 event(s), 0 news item(s)):"
            in prompt.text
        )

    def test_event_status_comes_from_the_domain_row(self):
        rows = WindowRows(
            short_events=(
                _event(row_id=11, status=EventStatus.RELEASED, actual="5.50%"),
                _event(row_id=12, dedupe_key="e12", status=EventStatus.STALE),
            ),
            short_items=(),
            mid_events=(),
            mid_items=(),
            long_events=(),
            long_items=(),
        )
        prompt = _build(rows=rows, min_items=1).prompt

        assert prompt is not None
        assert "| status=released |" in prompt.text
        assert "| status=stale |" in prompt.text

    def test_news_lines_carry_no_status(self):
        prompt = _build(items=[_item(row_id=22)], events=[], min_items=1).prompt

        assert prompt is not None
        news_line = next(
            line for line in prompt.text.splitlines() if line.startswith("- [news 22]")
        )
        assert "status=" not in news_line

    def test_prompt_carries_the_coverage_and_stale_rules(self):
        text = self._text()

        assert "Judge each horizon against the coverage of its data window" in text
        assert 'lower the confidence or answer' in text
        assert 'An event with status "stale" has no released actual' in text

    def test_prompt_forbids_inventing_data_and_citation_ids(self):
        text = self._text()

        assert 'Never invent events, numbers, dates, currency' in text
        assert "must be a row id printed in this prompt" in text

    def test_row_ids_are_bare_numbers_and_the_rule_says_so(self):
        # Lô A (ca "Nhận định AI — độ bền kết quả"): nhãn dòng bỏ "#" và prompt
        # nói rõ id là SỐ NGUYÊN TRẦN — model từng bắt chước "#" của nhãn prompt
        # vào mảng "evidence_item_ids" (vd [378, #3289]) làm JSON không parse được
        # ⇒ mất cả phạm vi.  Khung prompt phải sạch ký tự "#" (dữ liệu thì không
        # kiểm được: tiêu đề tin có thể chứa "#" hợp lệ).
        assert "#" not in builder._EVENT_LINE_TEMPLATE
        assert "#" not in builder._NEWS_LINE_TEMPLATE

        prompt = _build(events=[_event(row_id=11)], items=[_item(row_id=22)]).prompt

        assert prompt is not None
        assert "[event 11]" in prompt.text and "[news 22]" in prompt.text
        assert 'as PLAIN INTEGERS in the JSON array' in prompt.text
        assert 'no "#"\n  prefix' in prompt.text
        # Mẫu schema dẫn ví dụ bằng SỐ (trước đây là chuỗi "ids printed above"
        # — cũng là một nguồn gây hiểu sai).
        assert '"evidence_item_ids": [12, 34]' in prompt.text

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
        rows = WindowRows(
            short_events=(_event(row_id=11),),
            short_items=(_item(row_id=12, kind=NewsItemKind.STATEMENT),),
            mid_events=(_event(row_id=21, dedupe_key="e21"),),
            mid_items=(_item(row_id=22, dedupe_key="i22", kind=NewsItemKind.STATEMENT),),
            long_events=(_event(row_id=31, dedupe_key="e31"),),
            long_items=(_item(row_id=32, dedupe_key="i32", kind=NewsItemKind.STATEMENT),),
        )
        prompt = _build(rows=rows, min_items=1).prompt

        assert prompt is not None
        assert prompt.evidence_item_ids == (11, 12, 21, 22, 31, 32)

    def test_row_without_an_id_is_shown_but_not_citable(self):
        prompt = _build(
            events=[_event(row_id=None)],
            items=[_item(row_id=22)],
            min_items=2,
        ).prompt

        assert prompt is not None
        # the same row prints in all three windows; only ids are citable
        assert prompt.evidence_item_ids == (22, 22, 22)
        assert "[event no-id]" in prompt.text

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
            "windows": {
                "short": {"days": 7, "event_count": 2, "item_count": 1},
                "mid": {"days": 42, "event_count": 2, "item_count": 1},
                "long": {"days": 180, "event_count": 2, "item_count": 1},
            },
        }

    def test_snapshot_holds_no_key_besides_window_and_counts(self):
        # Invariant §4.5: no market-context value ever enters the snapshot.
        rows = WindowRows(
            short_events=(_event(row_id=11),),
            short_items=(),
            mid_events=(_event(row_id=21, dedupe_key="e21"),),
            mid_items=(),
            long_events=(),
            long_items=(),
        )
        prompt = _build(rows=rows, min_items=1).prompt

        assert prompt is not None
        assert set(prompt.snapshot) == {
            "window_days",
            "from_utc",
            "to_utc",
            "event_count",
            "item_count",
            "windows",
        }
        assert set(prompt.snapshot["windows"]) == {"short", "mid", "long"}
        for window in prompt.snapshot["windows"].values():
            assert set(window) == {"days", "event_count", "item_count"}

    def test_snapshot_windows_counts_track_each_window(self):
        rows = WindowRows(
            short_events=(_event(row_id=11),),
            short_items=(),
            mid_events=(_event(row_id=21, dedupe_key="e21"),) * 3,
            mid_items=(),
            long_events=(_event(row_id=31, dedupe_key="e31"),) * 5,
            long_items=(_item(row_id=32, kind=NewsItemKind.STATEMENT),),
        )
        prompt = _build(rows=rows, min_items=1).prompt

        assert prompt is not None
        windows = prompt.snapshot["windows"]
        assert windows["short"] == {"days": 7, "event_count": 1, "item_count": 0}
        assert windows["mid"] == {"days": 42, "event_count": 3, "item_count": 0}
        assert windows["long"] == {"days": 180, "event_count": 5, "item_count": 1}
        # top-level counts are the short window (§4.5)
        assert prompt.snapshot["event_count"] == 1
        assert prompt.snapshot["item_count"] == 0

    def test_floor_counts_the_short_window_only(self):
        # Invariant C4: a full mid/long window never lifts the short-window floor.
        rows = WindowRows(
            short_events=(),
            short_items=(_item(row_id=12),),  # 1 short row < min_items
            mid_events=tuple(
                _event(row_id=100 + index, dedupe_key=f"m{index}")
                for index in range(10)
            ),
            mid_items=tuple(
                _item(row_id=200 + index, dedupe_key=f"mi{index}")
                for index in range(10)
            ),
            long_events=tuple(
                _event(row_id=300 + index, dedupe_key=f"l{index}")
                for index in range(10)
            ),
            long_items=tuple(
                _item(row_id=400 + index, dedupe_key=f"li{index}")
                for index in range(10)
            ),
        )
        outcome = _build(rows=rows, min_items=2)

        assert outcome.insufficient_data is True
        assert outcome.prompt is None
        assert (outcome.event_count, outcome.item_count) == (0, 1)

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


# ---- 4b. khối "Market context" (§9.1 bước 3, C1-C4) -----------------------------


class TestMarketContextBlock:
    def test_full_context_renders_each_line(self):
        outcome = _build(
            context=MarketContext(
                rates=(
                    _rate_context("USD", 5.5, "2026-09-18", RateTrend.HOLD),
                    _rate_context("EUR", 2.0, "2026-09-18", RateTrend.CUT),
                ),
                yields=_yield_context(),
            )
        )

        assert outcome.prompt is not None
        text = outcome.prompt.text
        assert "Market context (for reasoning only - do NOT cite as evidence):" in text
        assert "- policy rate USD: 5.50 (hold), observed 2026-09-18" in text
        assert "- policy rate EUR: 2.00 (cut), observed 2026-09-18" in text
        assert (
            "- treasury 2y: 3.72 (delta -0.08 in window), 10y: 3.91 (delta 0.02)"
            in text
        )
        assert "- spread 2y10y: 0.19; real yield 10y: 1.55" in text

    def test_empty_context_renders_the_none_line(self):
        outcome = _build(context=MarketContext())

        assert outcome.prompt is not None
        assert "market context: none" in outcome.prompt.text
        assert "Market context (for reasoning only" not in outcome.prompt.text

    def test_missing_rate_omits_only_its_line(self):
        outcome = _build(context=MarketContext(rates=(_rate_context("USD"),)))

        assert outcome.prompt is not None
        assert "- policy rate USD:" in outcome.prompt.text
        assert "policy rate EUR:" not in outcome.prompt.text

    def test_missing_yields_omits_the_treasury_block(self):
        outcome = _build(context=MarketContext(rates=(_rate_context(),)))

        assert outcome.prompt is not None
        assert "- policy rate USD:" in outcome.prompt.text
        assert "treasury 2y:" not in outcome.prompt.text
        assert "spread 2y10y:" not in outcome.prompt.text

    def test_missing_subfields_render_as_dash(self):
        outcome = _build(
            context=MarketContext(
                rates=(_rate_context(),),
                yields=_yield_context(
                    be10y=None,
                    observed_at_be10y=None,
                    real_yield_10y=None,
                    delta_2y=None,
                ),
            )
        )

        assert outcome.prompt is not None
        text = outcome.prompt.text
        assert "treasury 2y: 3.72 (delta - in window)" in text
        assert "real yield 10y: -" in text

    def test_context_never_counts_toward_the_floor(self):
        # C4: below ai_min_items the prompt stays None even with a full context.
        outcome = _build(
            events=[_event()],
            items=[],
            context=MarketContext(
                rates=(_rate_context(),), yields=_yield_context()
            ),
            min_items=2,
        )

        assert outcome.insufficient_data is True
        assert outcome.prompt is None

    def test_context_is_never_citable_and_not_in_the_snapshot(self):
        prompt = _build(
            context=MarketContext(
                rates=(
                    _rate_context("USD", rate=5.5),
                    _rate_context("EUR", rate=2.0),
                ),
                yields=_yield_context(),
                rate_path=_rate_path(),
            )
        ).prompt

        assert prompt is not None
        # evidence ids are the printed rows (the default single row, in all three
        # windows), never context data
        assert prompt.evidence_item_ids == (11, 22, 11, 22, 11, 22)
        # §4.5 snapshot = window + counts only - no context field
        assert prompt.snapshot == {
            "window_days": 7,
            "from_utc": "2026-09-15T10:00:00Z",
            "to_utc": "2026-09-22T10:00:00Z",
            "event_count": 1,
            "item_count": 1,
            "windows": {
                "short": {"days": 7, "event_count": 1, "item_count": 1},
                "mid": {"days": 42, "event_count": 1, "item_count": 1},
                "long": {"days": 180, "event_count": 1, "item_count": 1},
            },
        }
        assert "5.50" not in str(prompt.snapshot)

    def test_rate_path_line_is_rendered(self):
        outcome = _build(
            context=MarketContext(rate_path=_rate_path(5.50, 5.00, 0.50))
        )

        assert outcome.prompt is not None
        assert "- policy rate path: now 5.50, 6m ago 5.00, change 0.50" in outcome.prompt.text

    def test_rate_path_missing_subfields_render_as_dash(self):
        outcome = _build(
            context=MarketContext(rate_path=_rate_path(None, None, None))
        )

        assert outcome.prompt is not None
        assert "- policy rate path: now -, 6m ago -, change -" in outcome.prompt.text

    def test_missing_rate_path_omits_the_line(self):
        outcome = _build(context=MarketContext(rates=(_rate_context(),)))

        assert outcome.prompt is not None
        assert "policy rate path:" not in outcome.prompt.text

    def test_yield_delta_lines_render_the_three_and_six_month_sets(self):
        yields = _yield_context(
            delta_3m=YieldDeltaSet(0.10, 0.20, -0.10, 0.05),
            delta_6m=YieldDeltaSet(0.30, 0.40, -0.20, 0.15),
        )
        outcome = _build(context=MarketContext(yields=yields))

        assert outcome.prompt is not None
        text = outcome.prompt.text
        assert "- yield delta 3m: 2y 0.10, 10y 0.20, spread -0.10, real 0.05" in text
        assert "- yield delta 6m: 2y 0.30, 10y 0.40, spread -0.20, real 0.15" in text

    def test_yield_delta_missing_values_render_as_dash(self):
        outcome = _build(context=MarketContext(yields=_yield_context()))

        assert outcome.prompt is not None
        assert "- yield delta 3m: 2y -, 10y -, spread -, real -" in outcome.prompt.text
        assert "- yield delta 6m: 2y -, 10y -, spread -, real -" in outcome.prompt.text


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
            "typing",
            "core.news_models",
            "core.news_policy",
            "core.rate_trend",
            "core.yield_context",
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
            "rows",
            "context",
            "now",
            "window_days",
            "horizon_windows",
            "long_max_rows",
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


# ---- 5b. độ dài prompt (rủi ro #4 — chỉ báo, không tự cắt) -----------------------


def _full_context() -> MarketContext:
    return MarketContext(
        rates=(_rate_context("USD"), _rate_context("EUR", 2.0, trend=RateTrend.CUT)),
        yields=_yield_context(
            delta_3m=YieldDeltaSet(0.10, 0.20, -0.10, 0.05),
            delta_6m=YieldDeltaSet(0.30, 0.40, -0.20, 0.15),
        ),
        rate_path=_rate_path(),
    )


class TestPromptLength:
    def test_realistic_prompt_stays_below_the_upper_bound(self):
        # A realistic worst case: short 10 rows, mid 30, long the full cap 50,
        # plus the full market context.  The bound is a guard, not a cut: if the
        # wave-6 prompt ever exceeds it the techlead decides how to trim.
        short_events = [
            _event(
                row_id=100 + index,
                dedupe_key=f"se{index}",
                title=f"Short event {index}",
                status=EventStatus.RELEASED,
                actual="1.00%",
            )
            for index in range(6)
        ]
        short_items = [
            _item(
                row_id=200 + index,
                dedupe_key=f"si{index}",
                kind=NewsItemKind.STATEMENT,
                content="x" * 200,
            )
            for index in range(4)
        ]
        mid_events = [
            _event(
                row_id=300 + index,
                dedupe_key=f"me{index}",
                title=f"Mid event {index}",
                impact=EventImpact.MEDIUM,
            )
            for index in range(20)
        ]
        mid_items = [
            _item(
                row_id=400 + index,
                dedupe_key=f"mi{index}",
                kind=NewsItemKind.STATEMENT,
                content="y" * 200,
            )
            for index in range(10)
        ]
        long_events = [
            _event(
                row_id=500 + index,
                dedupe_key=f"le{index}",
                title=f"Long event {index}",
                status=EventStatus.RELEASED,
                actual="2.00%",
            )
            for index in range(30)
        ]
        long_items = [
            _item(
                row_id=600 + index,
                dedupe_key=f"li{index}",
                kind=NewsItemKind.STATEMENT,
                content="z" * 200,
            )
            for index in range(20)
        ]
        rows = WindowRows(
            short_events=tuple(short_events),
            short_items=tuple(short_items),
            mid_events=tuple(mid_events),
            mid_items=tuple(mid_items),
            long_events=tuple(long_events),
            long_items=tuple(long_items),
        )

        prompt = _build(rows=rows, context=_full_context(), min_items=1).prompt

        assert prompt is not None
        assert len(prompt.text) < 30_000
        # the three sections are all present in the realistic prompt
        assert "Data - short window, 7 days (6 event(s), 4 news item(s)):" in prompt.text
        assert "Data - mid window, 42 days (20 event(s), 10 news item(s)):" in prompt.text
        assert (
            "Data - long window, 180 days, top 50 rows (30 event(s), 20 news item(s)):"
            in prompt.text
        )


# ---- 6. chọn dòng theo cửa sổ chân trời (§9.1 bước 2, đợt 6) --------------------


def _windows(short: int = 7, mid: int = 42, long: int = 180) -> HorizonWindowSet:
    return HorizonWindowSet(short_days=short, mid_days=mid, long_days=long)


def _select(
    *,
    short_events: list[CalendarEvent] | None = None,
    short_items: list[NewsItem] | None = None,
    mid_events: list[CalendarEvent] | None = None,
    mid_items: list[NewsItem] | None = None,
    long_events: list[CalendarEvent] | None = None,
    long_items: list[NewsItem] | None = None,
    windows: HorizonWindowSet | None = None,
    long_max_rows: int = 50,
) -> WindowRows:
    return select_rows_for_windows(
        {
            "short": short_events if short_events is not None else [],
            "mid": mid_events if mid_events is not None else [],
            "long": long_events if long_events is not None else [],
        },
        {
            "short": short_items if short_items is not None else [],
            "mid": mid_items if mid_items is not None else [],
            "long": long_items if long_items is not None else [],
        },
        windows if windows is not None else _windows(),
        long_max_rows,
    )


def _high_actual_event(index: int) -> CalendarEvent:
    """A high-impact event with an actual, at a distinct, index-ordered time."""
    moment = datetime(2026, 9, 1, tzinfo=UTC) + timedelta(minutes=index)
    stamp = moment.isoformat(timespec="seconds").replace("+00:00", "Z")
    return _event(
        row_id=index,
        event_time_utc=stamp,
        dedupe_key=f"event-{index}",
        impact=EventImpact.HIGH,
        actual="1.0%",
    )


def _statement_item(index: int) -> NewsItem:
    moment = datetime(2026, 9, 1, tzinfo=UTC) + timedelta(minutes=index)
    stamp = moment.isoformat(timespec="seconds").replace("+00:00", "Z")
    return _item(
        row_id=1000 + index,
        published_utc=stamp,
        dedupe_key=f"item-{index}",
        kind=NewsItemKind.STATEMENT,
    )


class TestSelectRowsForWindows:
    """The pure row selector of §9.1 bước 2 — filtering, cap and determinism."""

    def test_short_keeps_every_event_and_item(self):
        result = _select(
            short_events=[
                _event(row_id=1, impact=EventImpact.HIGH),
                _event(row_id=2, impact=EventImpact.LOW, dedupe_key="e2"),
                _event(row_id=3, impact=EventImpact.NON, dedupe_key="e3"),
            ],
            short_items=[
                _item(row_id=4, kind=NewsItemKind.HEADLINE),
                _item(row_id=5, kind=NewsItemKind.STATEMENT, dedupe_key="i5"),
                _item(row_id=6, kind=NewsItemKind.USER_NOTE, dedupe_key="i6"),
            ],
        )

        assert {event.id for event in result.short_events} == {1, 2, 3}
        assert {item.id for item in result.short_items} == {4, 5, 6}

    def test_mid_drops_low_and_non_impact_events(self):
        result = _select(
            mid_events=[
                _event(row_id=1, impact=EventImpact.HIGH),
                _event(row_id=2, impact=EventImpact.MEDIUM, dedupe_key="e2"),
                _event(row_id=3, impact=EventImpact.LOW, dedupe_key="e3"),
                _event(row_id=4, impact=EventImpact.NON, dedupe_key="e4"),
            ]
        )

        assert {event.id for event in result.mid_events} == {1, 2}

    def test_mid_keeps_only_statement_items(self):
        result = _select(
            mid_items=[
                _item(row_id=1, kind=NewsItemKind.HEADLINE),
                _item(row_id=2, kind=NewsItemKind.STATEMENT, dedupe_key="i2"),
                _item(row_id=3, kind=NewsItemKind.USER_NOTE, dedupe_key="i3"),
            ]
        )

        assert [item.id for item in result.mid_items] == [2]

    def test_long_drops_medium_and_high_without_actual(self):
        result = _select(
            long_events=[
                _event(row_id=1, impact=EventImpact.HIGH, actual="1.0%"),
                _event(row_id=2, impact=EventImpact.HIGH, dedupe_key="e2"),
                _event(row_id=3, impact=EventImpact.HIGH, dedupe_key="e3", actual=""),
                _event(row_id=4, impact=EventImpact.HIGH, dedupe_key="e4", actual="   "),
                _event(row_id=5, impact=EventImpact.MEDIUM, dedupe_key="e5", actual="1.0%"),
            ]
        )

        assert [event.id for event in result.long_events] == [1]

    def test_long_keeps_only_statement_items(self):
        result = _select(
            long_items=[
                _item(row_id=1, kind=NewsItemKind.HEADLINE),
                _item(row_id=2, kind=NewsItemKind.STATEMENT, dedupe_key="i2"),
            ]
        )

        assert [item.id for item in result.long_items] == [2]

    def test_long_cap_keeps_the_fifty_most_recent_high_events(self):
        events = [_high_actual_event(index) for index in range(60)]

        result = _select(long_events=events)

        assert len(result.long_events) == 50
        assert [event.id for event in result.long_events] == list(range(59, 9, -1))

    def test_long_cap_prefers_events_over_statements(self):
        events = [_high_actual_event(0), _high_actual_event(1)]
        items = [_statement_item(index) for index in range(3)]

        result = _select(long_events=events, long_items=items, long_max_rows=3)

        assert [event.id for event in result.long_events] == [1, 0]
        assert [item.id for item in result.long_items] == [1002]

    def test_selection_is_deterministic_under_input_shuffle(self):
        events = [_high_actual_event(index) for index in range(60)]
        items = [_statement_item(index) for index in range(20)]
        canonical = _select(long_events=events, long_items=items, long_max_rows=30)

        shuffled_events = list(reversed(events))
        shuffled_items = items[7:] + items[:7]
        again = _select(
            long_events=shuffled_events, long_items=shuffled_items, long_max_rows=30
        )

        assert again == canonical

    def test_selector_is_pure_and_returns_immutable_tuples(self):
        events = [_high_actual_event(0), _high_actual_event(1)]
        first = _select(long_events=events)
        second = _select(long_events=list(events))

        assert first == second
        assert isinstance(first.long_events, tuple)

    def test_missing_window_key_raises(self):
        with pytest.raises(ValueError):
            select_rows_for_windows(
                {"short": [], "mid": []},
                {"short": [], "mid": [], "long": []},
                _windows(),
                50,
            )
