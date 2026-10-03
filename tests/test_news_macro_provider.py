"""Test `services/news_macro_provider.py` với repository GIẢ (không DB thật).

Phủ: shape 5 method (parity `NewsService`), mapping model → dict, cửa sổ đọc,
cache TTL 5 phút, fail-closed khi lỗi đọc DB, `vix_pair_aware_enabled` (cache 60s,
lỗi → False), blackout `execution_news_status`, và tính thuần-đọc (không mạng).
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from core.news_models import StoreState, StoreStatus
from core.reason_codes import MACRO_CALENDAR_STALE
from services.news_macro_provider import NEWS_STATUS_UNAVAILABLE, NewsMacroProvider

NOW = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Repository giả
# ---------------------------------------------------------------------------


class _FakeRepository:
    """Duck-type đúng 5 method đọc của `NewsRepository`; có ghi lại lượt gọi."""

    def __init__(
        self,
        *,
        events=(),
        items=(),
        rates=(),
        yields=(),
        state: StoreState | None = None,
        fail: tuple[str, ...] = (),
    ) -> None:
        self.events = list(events)
        self.items = list(items)
        self.rates = list(rates)
        self.yields = list(yields)
        self.state = state or _store_state()
        self.fail = set(fail)
        self.calls: list[tuple[str, tuple, dict]] = []

    def _record(self, name: str, args: tuple, kwargs: dict) -> None:
        self.calls.append((name, args, kwargs))
        if name in self.fail:
            raise sqlite3.OperationalError(f"boom: {name}")

    def events_in_range(self, from_utc, to_utc, currencies=None, include_non_impact=True):
        self._record("events_in_range", (from_utc, to_utc, currencies), {})
        rows = [
            event
            for event in self.events
            if from_utc <= event.event_time_utc <= to_utc
            and (not currencies or event.currency in currencies)
        ]
        return sorted(rows, key=lambda event: event.event_time_utc)

    def items_in_range(self, from_utc, to_utc=None, kinds=None, currencies=None, exclude_flagged=True):
        self._record("items_in_range", (from_utc, to_utc, kinds), {})
        rows = []
        for item in self.items:
            if item.published_utc < from_utc:
                continue
            if to_utc is not None and item.published_utc > to_utc:
                continue
            if kinds and str(item.kind) not in kinds:
                continue
            if currencies and not (set(item.currencies) & set(currencies)):
                continue
            rows.append(item)
        return sorted(rows, key=lambda item: item.published_utc)

    def latest_rates(self, currencies):
        self._record("latest_rates", (list(currencies),), {})
        return [trend for trend in self.rates if trend.currency in set(currencies)]

    def latest_bond_yields(self, currencies):
        self._record("latest_bond_yields", (list(currencies),), {})
        return [snap for snap in self.yields if snap.currency in set(currencies)]

    def store_state(self):
        self._record("store_state", (), {})
        return self.state


def _store_state(
    *,
    events: str = "fresh",
    items: str = "fresh",
    rates: str = "fresh",
    yields: str = "fresh",
    events_at: str | None = None,
) -> StoreState:
    return StoreState(
        events_state=StoreStatus(events),
        items_state=StoreStatus(items),
        rates_state=StoreStatus(rates),
        yields_state=StoreStatus(yields),
        events_last_success_at=events_at or _iso(NOW - timedelta(minutes=10)),
        items_last_success_at=_iso(NOW - timedelta(minutes=30)),
        rates_last_success_at=_iso(NOW - timedelta(minutes=20)),
        yields_last_success_at=_iso(NOW - timedelta(minutes=40)),
    )


# ---------------------------------------------------------------------------
# Model giả (chỉ thuộc tính mà provider đọc — đúng hợp đồng model ở §5)
# ---------------------------------------------------------------------------


def _event(
    currency: str,
    *,
    hours: float,
    title: str = "US CPI",
    impact: str = "high",
    actual: str | None = None,
    forecast: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        currency=currency,
        title=title,
        impact=impact,
        forecast=forecast,
        previous=None,
        actual=actual,
        event_time_utc=_iso(NOW + timedelta(hours=hours)),
    )


def _item(title: str, *, hours: float = 1.0, kind: str = "headline", currencies=()) -> SimpleNamespace:
    return SimpleNamespace(
        title=title,
        published_utc=_iso(NOW - timedelta(hours=hours)),
        kind=kind,
        currencies=list(currencies),
    )


def _rate(currency: str, value: float, trend: str) -> SimpleNamespace:
    return SimpleNamespace(currency=currency, latest=SimpleNamespace(rate=value), trend=trend)


def _yield_snapshot(spread: float, *, ten_year: float = 4.3, two_year: float = 4.6,
                    delta_spread: float | None = 0.2) -> SimpleNamespace:
    return SimpleNamespace(
        currency="USD",
        context=SimpleNamespace(
            yield_2y=two_year,
            yield_10y=ten_year,
            spread_2y10y=spread,
            delta_6m=SimpleNamespace(delta_spread=delta_spread),
        ),
    )


def _provider(repo: _FakeRepository, *, clock=None, settings=None) -> NewsMacroProvider:
    return NewsMacroProvider(
        repo,
        settings_service=settings,
        observability=SimpleNamespace(emit=lambda *a, **k: None),
        clock=clock or (lambda: NOW),
    )


# ===========================================================================
# 1. Shape của 5 method
# ===========================================================================


class TestMethodShapes:
    def test_latest_macro_context_keeps_the_old_keys(self):
        repo = _FakeRepository(
            events=[_event("EUR", hours=5.0)],
            items=[_item("ECB signals hawkish stance")],
            rates=[_rate("EUR", 3.5, "hike"), _rate("USD", 5.0, "hold")],
            yields=[_yield_snapshot(-0.3)],
        )

        context = _provider(repo).latest_macro_context("EUR/USD")

        assert set(context) == {
            "symbol", "source", "events", "latest_headlines", "latest_statements",
            "macro_themes", "geopolitical_hotspots", "macro_alignment_scores",
            "macro_alignment_reasons", "macro_tier_detail", "macro_data_quality",
            "macro_data_quality_detail", "stance_detail", "macro_cache", "warning",
        }
        assert context["symbol"] == "EUR/USD"
        assert context["source"] == "news_repository"
        assert set(context["macro_alignment_scores"]) == {"buy", "sell"}
        assert set(context["macro_tier_detail"]) == {
            "tier1_interest_rate", "tier2_calendar", "tier3_sentiment",
            "data_confidence", "macro_score_raw",
        }
        assert context["stance_detail"]["base"]["source"] == "keyword"
        assert 0.0 <= context["macro_data_quality"] <= 1.0

    def test_data_quality_flags_shape(self):
        repo = _FakeRepository(
            events=[_event("EUR", hours=2.0)],
            items=[_item("ECB holds")],
            rates=[_rate("EUR", 3.5, "hold")],
        )

        flags = _provider(repo).data_quality_flags("EUR/USD")

        assert set(flags) == {
            "macro_context", "news_in_3h", "high_impact_event_within_30m",
            "next_high_impact_event", "resume_after", "vix_pair_aware_enabled",
        }
        assert flags["news_in_3h"] is True
        assert flags["high_impact_event_within_30m"] is False
        assert flags["next_high_impact_event"]["currency"] == "EUR"
        assert flags["resume_after"].endswith("+00:00")
        assert flags["vix_pair_aware_enabled"] is False

    def test_macro_freshness_status_shape(self):
        status = _provider(_FakeRepository()).macro_freshness_status()

        assert set(status) == {"status", "age_minutes", "confidence_multiplier", "reason_codes"}
        assert status == {
            "status": "fresh",
            "age_minutes": 10,
            "confidence_multiplier": 1.0,
            "reason_codes": [],
        }

    def test_execution_news_status_shape(self):
        result = _provider(_FakeRepository()).execution_news_status("EUR/USD", now=NOW)

        assert set(result) == {
            "available", "blackout", "checked_at", "event", "source", "reason_codes",
        }
        assert result["available"] is True and result["blackout"] is False

    def test_preload_signature_returns_none_and_reports_progress(self):
        repo = _FakeRepository(items=[_item("ECB holds")], rates=[_rate("EUR", 3.5, "hold")])
        seen: list[tuple[int, str]] = []

        assert _provider(repo).preload_macro_contexts(
            ["EUR/USD", "USD/JPY"], lambda step, message: seen.append((step, message))
        ) is None

        assert seen[0] == (15, "Đang tải snapshot vĩ mô toàn cầu...")
        assert seen[1][1] == "Đang phân tích vĩ mô EUR/USD (1/2)..."
        assert seen[2][1] == "Đang phân tích vĩ mô USD/JPY (2/2)..."

    def test_preload_reads_the_repository_once_per_scan(self):
        repo = _FakeRepository(items=[_item("ECB holds")], rates=[_rate("EUR", 3.5, "hold")])

        _provider(repo).preload_macro_contexts(["EUR/USD", "USD/JPY", "EUR/JPY"])

        reads = [name for name, _, _ in repo.calls]
        assert reads.count("events_in_range") == 1
        assert reads.count("latest_rates") == 1
        assert reads.count("latest_bond_yields") == 1
        # items_in_range gọi 2 lần: headlines + statements (cùng một cửa sổ).
        assert reads.count("items_in_range") == 2
        # currencies của CẢ 3 symbol trong một lượt đọc rates duy nhất.
        rates_call = next(call for call in repo.calls if call[0] == "latest_rates")
        assert set(rates_call[1][0]) == {"EUR", "USD", "JPY"}

    def test_preload_warms_the_per_symbol_cache(self):
        """Parity bản cũ: sau preload, lượt hỏi context từng symbol không đọc lại DB."""
        repo = _FakeRepository(items=[_item("ECB holds")], rates=[_rate("EUR", 3.5, "hold")])
        provider = _provider(repo)

        provider.preload_macro_contexts(["EUR/USD", "USD/JPY"])
        repo.calls.clear()
        provider.latest_macro_context("EUR/USD")

        assert [name for name, _, _ in repo.calls] == []

    def test_data_quality_flags_after_preload_reads_nothing(self):
        repo = _FakeRepository(items=[_item("ECB holds")], rates=[_rate("EUR", 3.5, "hold")])
        provider = _provider(repo)

        provider.preload_macro_contexts(["EUR/USD"])
        repo.calls.clear()
        flags = provider.data_quality_flags("EUR/USD")

        assert flags["macro_context"]["symbol"] == "EUR/USD"
        assert [name for name, _, _ in repo.calls] == []


# ===========================================================================
# 2. Mapping dữ liệu
# ===========================================================================


class TestMapping:
    def test_event_mapping(self):
        repo = _FakeRepository(events=[_event("EUR", hours=5.0, actual="3.1%", forecast="3.0%")])

        event = _provider(repo).latest_macro_context("EUR/USD")["events"][0]

        assert event == {
            "currency": "EUR",
            "event": "US CPI",
            "impact": "high",
            "forecast": "3.0%",
            "previous": None,
            "actual": "3.1%",
            "time_utc": _iso(NOW + timedelta(hours=5)),
        }

    def test_headline_mapping(self):
        repo = _FakeRepository(items=[_item("ECB signals hike", currencies=["EUR"])])

        headline = _provider(repo).latest_macro_context("EUR/USD")["latest_headlines"][0]

        assert headline == {
            "title": "ECB signals hike",
            "published_utc": _iso(NOW - timedelta(hours=1)),
            "currencies": ["EUR"],
        }

    def test_rate_mapping_prefers_news_db(self):
        repo = _FakeRepository(rates=[_rate("EUR", 3.5, "hike"), _rate("USD", 5.0, "hold")])

        detail = _provider(repo).latest_macro_context("EUR/USD")["macro_tier_detail"]

        tier1 = detail["tier1_interest_rate"]["detail"]
        assert tier1["base_rate"] == "3.50%" and tier1["quote_rate"] == "5.00%"
        assert tier1["base_trend"] == "hike" and tier1["quote_trend"] == "hold"

    def test_rate_mapping_falls_back_to_config_file(self, tmp_path, monkeypatch):
        config = tmp_path / "interest_rates.json"
        config.write_text(
            '{"currencies": {"JPY": {"rate": -0.1, "trend": "hold", "rate_label": "-0.10%"}}}',
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "services.news_macro_provider._RATE_FALLBACK_PATH", config
        )
        repo = _FakeRepository(rates=[_rate("USD", 5.0, "hold")])

        tier1 = _provider(repo).latest_macro_context("USD/JPY")["macro_tier_detail"][
            "tier1_interest_rate"
        ]["detail"]

        assert tier1["quote_rate"] == "-0.10%"
        assert tier1["quote_trend"] == "hold"

    def test_yield_mapping_uses_2y10y_series(self):
        repo = _FakeRepository(yields=[_yield_snapshot(-0.35, ten_year=4.2, two_year=4.55)])

        tier1 = _provider(repo).latest_macro_context("EUR/USD")["macro_tier_detail"][
            "tier1_interest_rate"
        ]["detail"]

        assert tier1["yield_spread_10y_5y"] == -0.35  # spread = 2y10y
        assert tier1["ten_year_yield"] == 4.2
        assert tier1["five_year_yield"] is None
        assert tier1["yield_spread_adj"] == {"buy": 2, "sell": -2}

    def test_yield_mapping_absent_data_yields_empty_payload(self):
        tier1 = _provider(_FakeRepository()).latest_macro_context("EUR/USD")[
            "macro_tier_detail"
        ]["tier1_interest_rate"]["detail"]

        assert tier1["yield_spread_10y_5y"] is None
        assert tier1["yield_spread_adj"] == {"buy": 0, "sell": 0}

    def test_statements_only_when_requested(self):
        repo = _FakeRepository(
            items=[
                _item("ECB signals hike", kind="headline"),
                _item("ECB statement text", kind="statement"),
            ]
        )
        provider = _provider(repo)

        with_statements = provider.latest_macro_context("EUR/USD")
        without = provider.latest_macro_context("EUR/USD", include_latest_statements=False)

        assert [item["title"] for item in with_statements["latest_statements"]] == ["ECB statement text"]
        assert without["latest_statements"] == []

    def test_headlines_exclude_statements_and_user_notes(self):
        """Headlines chỉ lấy kind headline (parity scope cũ: tin RSS tách statement).

        Statements đến đúng 1 lần (qua `latest_statements`) — không bị đếm hai lần
        trong hotspots; `user_note` (tin nhập tay) không thuộc dữ liệu thị trường.
        """
        repo = _FakeRepository(
            items=[
                _item("ECB signals hike", kind="headline"),
                _item("ECB statement text", kind="statement"),
                _item("Ghi chú tay của người dùng", kind="user_note"),
            ]
        )
        provider = _provider(repo)

        context = provider.latest_macro_context("EUR/USD")

        assert [item["title"] for item in context["latest_headlines"]] == ["ECB signals hike"]
        assert [item["title"] for item in context["latest_statements"]] == [
            "ECB statement text"
        ]

    def test_mapping_from_real_models(self):
        """Xác nhận tên thuộc tính trên model THẬT (fake không được nói dối)."""
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
        from core.rate_trend import RateTrend
        from core.yield_context import YieldContext
        from services.news_repository import CurrencyRateTrend

        event = CalendarEvent(
            day_key="2026-08-13",
            event_time_utc=_iso(NOW + timedelta(hours=4)),
            currency="EUR",
            title="ECB Interest Rate Decision",
            impact=EventImpact.HIGH,
            status=EventStatus.SCHEDULED,
            source=EventSource.FF_JSON,
            dedupe_key="d1",
            fetched_at=_iso(NOW),
            forecast="3.5%",
        )
        item = NewsItem(
            kind=NewsItemKind.HEADLINE,
            source=NewsItemSource.GOOGLE_NEWS_RSS,
            title="ECB signals hike",
            published_utc=_iso(NOW - timedelta(hours=2)),
            currencies=["EUR"],
            dedupe_key="k1",
            fetched_at=_iso(NOW),
        )
        trend = CurrencyRateTrend(
            currency="EUR",
            latest=RateObservation(
                currency="EUR", rate=3.5, observed_at=_iso(NOW), source=RateSource.FRED,
                fetched_at=_iso(NOW),
            ),
            previous=None,
            trend=RateTrend.HIKE,
        )
        yields = SimpleNamespace(
            currency="USD",
            context=YieldContext(
                yield_2y=4.5, observed_at_2y=_iso(NOW), yield_10y=4.2,
                observed_at_10y=_iso(NOW), be10y=None, observed_at_be10y=None,
                delta_2y=None, delta_10y=None, spread_2y10y=-0.3, real_yield_10y=None,
            ),
        )
        repo = _FakeRepository(events=[event], items=[item], rates=[trend], yields=[yields])

        context = _provider(repo).latest_macro_context("EUR/USD")

        assert context["events"][0]["impact"] == "high"
        assert context["events"][0]["time_utc"] == event.event_time_utc
        assert context["latest_headlines"][0]["title"] == "ECB signals hike"
        assert context["macro_tier_detail"]["tier1_interest_rate"]["detail"][
            "base_rate"
        ] == "3.50%"
        assert context["macro_tier_detail"]["tier1_interest_rate"]["detail"][
            "yield_spread_10y_5y"
        ] == -0.3


# ===========================================================================
# 3. Cửa sổ đọc
# ===========================================================================


class TestReadWindows:
    def test_events_window_is_minus_24h_plus_72h_filtered_and_capped(self):
        repo = _FakeRepository(events=[_event("EUR", hours=h) for h in (-30, -12, 5, 40, 80)])
        repo.events.append(_event("JPY", hours=5.0))

        _provider(repo).latest_macro_context("EUR/USD")

        _, (from_utc, to_utc, currencies), _ = next(
            call for call in repo.calls if call[0] == "events_in_range"
        )
        assert from_utc == _iso(NOW - timedelta(hours=24))
        assert to_utc == _iso(NOW + timedelta(hours=72))
        assert currencies == ["EUR", "USD"]

    def test_events_capped_at_eight_and_currency_filtered(self):
        events = [_event("EUR", hours=1.0 + index) for index in range(10)]
        events.append(_event("JPY", hours=2.0))
        repo = _FakeRepository(events=events)

        context = _provider(repo).latest_macro_context("EUR/USD")

        assert len(context["events"]) == 8
        assert {event["currency"] for event in context["events"]} == {"EUR"}

    def test_headlines_window_is_minus_24h_to_now(self):
        repo = _FakeRepository(items=[_item("ECB holds", hours=1.0)])

        _provider(repo).latest_macro_context("EUR/USD")

        items_calls = [call for call in repo.calls if call[0] == "items_in_range"]
        windows = {call[1][:2] for call in items_calls}
        assert windows == {(_iso(NOW - timedelta(hours=24)), _iso(NOW))}

    def test_headlines_are_not_filtered_by_currency(self):
        """Nhánh "keep global headline" của bản cũ: mọi headline trong cửa sổ đều giữ."""
        repo = _FakeRepository(
            items=[_item("Bank of Canada keeps rates"), _item("ECB hikes")]
        )

        context = _provider(repo).latest_macro_context("EUR/USD")

        assert [item["title"] for item in context["latest_headlines"]] == [
            "Bank of Canada keeps rates",
            "ECB hikes",
        ]


# ===========================================================================
# 4. Cache TTL
# ===========================================================================


class TestCache:
    def test_second_call_within_ttl_is_served_from_cache(self):
        repo = _FakeRepository(items=[_item("ECB holds")], rates=[_rate("EUR", 3.5, "hold")])
        provider = _provider(repo)

        first = provider.latest_macro_context("EUR/USD")
        repo.calls.clear()
        second = provider.latest_macro_context("EUR/USD")

        assert second == first
        assert [name for name, _, _ in repo.calls] == []  # không đọc lại repository

    def test_cache_expires_after_five_minutes(self):
        repo = _FakeRepository(items=[_item("ECB holds")], rates=[_rate("EUR", 3.5, "hold")])
        clock = _MutableClock(NOW)
        provider = NewsMacroProvider(
            repo,
            settings_service=None,
            observability=SimpleNamespace(emit=lambda *a, **k: None),
            clock=clock,
        )

        provider.latest_macro_context("EUR/USD")
        repo.calls.clear()
        clock.advance(minutes=4, seconds=59)
        provider.latest_macro_context("EUR/USD")
        assert [name for name, _, _ in repo.calls] == []

        clock.advance(seconds=2)
        provider.latest_macro_context("EUR/USD")
        assert "events_in_range" in [name for name, _, _ in repo.calls]

    def test_cache_is_per_symbol_and_statement_flag(self):
        repo = _FakeRepository(items=[_item("ECB holds")], rates=[_rate("EUR", 3.5, "hold")])
        provider = _provider(repo)

        provider.latest_macro_context("EUR/USD")
        repo.calls.clear()
        provider.latest_macro_context("USD/JPY")
        provider.latest_macro_context("EUR/USD", include_latest_statements=False)

        assert "events_in_range" in [name for name, _, _ in repo.calls]

    def test_cached_context_is_isolated_from_caller_mutation(self):
        repo = _FakeRepository(items=[_item("ECB holds")], rates=[_rate("EUR", 3.5, "hold")])
        provider = _provider(repo)

        first = provider.latest_macro_context("EUR/USD")
        first["events"].append({"currency": "XXX"})
        second = provider.latest_macro_context("EUR/USD")

        assert second["events"] == []


class _MutableClock:
    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def advance(self, **kwargs) -> None:
        self._moment += timedelta(**kwargs)

    def __call__(self) -> datetime:
        return self._moment


# ===========================================================================
# 5. Fail-closed khi lỗi đọc DB
# ===========================================================================


class TestFailClosed:
    @pytest.mark.parametrize(
        "read", ["events_in_range", "items_in_range", "latest_rates", "latest_bond_yields"]
    )
    def test_read_failure_yields_empty_context_without_crashing(self, read):
        repo = _FakeRepository(
            events=[_event("EUR", hours=3.0)],
            items=[_item("ECB holds")],
            rates=[_rate("EUR", 3.5, "hold")],
            yields=[_yield_snapshot(-0.3)],
            fail=(read,),
        )

        context = _provider(repo).latest_macro_context("EUR/USD")

        # Không crash, shape nguyên, điểm vẫn trong thang 0-30 và quality hữu hạn.
        assert set(context) >= {"events", "macro_alignment_scores", "macro_data_quality"}
        assert 0.0 < context["macro_data_quality"] <= 1.0
        for side in ("buy", "sell"):
            assert 0 <= context["macro_alignment_scores"][side] <= 30

    def test_events_read_failure_empties_events_and_drops_quality(self):
        repo = _FakeRepository(items=[_item("ECB holds")], fail=("events_in_range",))

        context = _provider(repo).latest_macro_context("EUR/USD")

        assert context["events"] == []
        # 1.0 − 0.10 (<3 headline) − 0.10 (không event) = 0.80.
        assert context["macro_data_quality"] == pytest.approx(0.80)

    def test_items_read_failure_empties_headlines_and_drops_quality(self):
        repo = _FakeRepository(events=[_event("EUR", hours=3.0)], fail=("items_in_range",))

        context = _provider(repo).latest_macro_context("EUR/USD")

        assert context["latest_headlines"] == []
        assert context["latest_statements"] == []
        # 1.0 − 0.30 (không headline) − 0.10 − 0.10 = 0.50 (còn event).
        assert context["macro_data_quality"] == pytest.approx(0.50)

    def test_rates_read_failure_leaves_tier1_on_neutral_zeros(self):
        repo = _FakeRepository(
            events=[_event("EUR", hours=3.0)],
            items=[_item("ECB holds")],
            fail=("latest_rates", "latest_bond_yields"),
        )

        tier1 = _provider(repo).latest_macro_context("EUR/USD")["macro_tier_detail"][
            "tier1_interest_rate"
        ]

        assert tier1["detail"]["rate_differential"] == pytest.approx(0.0)
        assert tier1["detail"]["yield_spread_adj"] == {"buy": 0, "sell": 0}
        assert tier1["buy"] == tier1["sell"]

    def test_all_reads_failing_drops_data_quality_to_the_empty_formula(self):
        repo = _FakeRepository(
            fail=("events_in_range", "items_in_range", "latest_rates", "latest_bond_yields")
        )

        context = _provider(repo).latest_macro_context("EUR/USD")

        assert context["events"] == []
        assert context["latest_headlines"] == []
        # Công thức cũ cho "không headlines / không events": 1.0 −0.30 −0.10 −0.10 −0.10.
        assert context["macro_data_quality"] == pytest.approx(0.40)
        assert context["macro_tier_detail"]["tier2_calendar"]["buy"] == 5
        assert context["warning"]

    def test_store_state_failure_reports_expired(self):
        repo = _FakeRepository(fail=("store_state",))

        assert _provider(repo).macro_freshness_status() == {
            "status": "expired",
            "age_minutes": 9999,
            "confidence_multiplier": 0.6,
            "reason_codes": [MACRO_CALENDAR_STALE],
        }

    def test_execution_status_fails_closed_on_read_failure(self):
        repo = _FakeRepository(fail=("events_in_range",))

        result = _provider(repo).execution_news_status("EUR/USD", now=NOW)

        assert result["available"] is False
        assert result["blackout"] is None
        assert NEWS_STATUS_UNAVAILABLE in result["reason_codes"]


# ===========================================================================
# 6. macro_freshness_status
# ===========================================================================


class TestFreshnessStatus:
    def test_all_fresh(self):
        status = _provider(_FakeRepository(state=_store_state())).macro_freshness_status()

        assert status["status"] == "fresh" and status["confidence_multiplier"] == 1.0

    def test_three_original_keys_are_untouched(self):
        """WI-6 chỉ THÊM `reason_codes`; shape 3 key cũ giữ nguyên."""
        status = _provider(_FakeRepository(state=_store_state())).macro_freshness_status()

        assert set(status) == {"status", "age_minutes", "confidence_multiplier", "reason_codes"}

    def test_events_degraded_reports_calendar_stale(self):
        """(a) scope events degraded (các scope khác fresh) → cờ nhắc dán lịch FF."""
        state = _store_state(events="degraded")

        status = _provider(_FakeRepository(state=state)).macro_freshness_status()

        assert status["reason_codes"] == [MACRO_CALENDAR_STALE]
        assert status["status"] == "stale"  # worst-of-4 không đổi

    def test_events_unavailable_reports_calendar_stale(self):
        """(a) scope events chưa từng ingest → cùng cờ."""
        state = _store_state(events="unavailable")

        status = _provider(_FakeRepository(state=state)).macro_freshness_status()

        assert status["reason_codes"] == [MACRO_CALENDAR_STALE]
        assert status["status"] == "expired"

    def test_events_fresh_with_other_scopes_unavailable_reports_nothing(self):
        """(b) nguồn lịch tươi thì KHÔNG nhắc — dù scope khác chưa từng ingest."""
        state = _store_state(events="fresh", items="unavailable", rates="unavailable",
                             yields="unavailable")

        status = _provider(_FakeRepository(state=state)).macro_freshness_status()

        assert status["reason_codes"] == []
        assert status["status"] == "expired"  # multiplier vẫn worst-of-4

    def test_store_state_failure_also_reports_calendar_stale(self):
        repo = _FakeRepository(fail=("store_state",))

        status = _provider(repo).macro_freshness_status()

        assert status["reason_codes"] == [MACRO_CALENDAR_STALE]
        assert status["status"] == "expired"

    def test_any_degraded_is_stale(self):
        state = _store_state(items="degraded")

        status = _provider(_FakeRepository(state=state)).macro_freshness_status()

        assert status["status"] == "stale" and status["confidence_multiplier"] == 0.85

    def test_any_unavailable_is_expired_and_wins_over_degraded(self):
        state = _store_state(events="unavailable", items="degraded")

        status = _provider(_FakeRepository(state=state)).macro_freshness_status()

        assert status["status"] == "expired" and status["confidence_multiplier"] == 0.6

    def test_age_minutes_uses_the_most_recent_ingest_success(self):
        state = _store_state(events_at=_iso(NOW - timedelta(minutes=10)))

        status = _provider(_FakeRepository(state=state)).macro_freshness_status()

        assert status["age_minutes"] == 10  # 10' < 20' < 30' < 40'

    def test_age_is_unknown_when_no_scope_ever_succeeded(self):
        state = StoreState(
            events_state=StoreStatus.UNAVAILABLE,
            items_state=StoreStatus.UNAVAILABLE,
            rates_state=StoreStatus.UNAVAILABLE,
            yields_state=StoreStatus.UNAVAILABLE,
        )

        status = _provider(_FakeRepository(state=state)).macro_freshness_status()

        assert status["age_minutes"] == 9999


class TestNewsEventsScope:
    """WI-4b: trạng thái RIÊNG của scope sự kiện (News sub-gate đọc nguồn này)."""

    def test_returns_the_events_scope_status(self):
        for value in ("fresh", "degraded", "unavailable"):
            state = _store_state(events=value)

            assert _provider(_FakeRepository(state=state)).news_events_scope() == value

    def test_other_scopes_do_not_leak_into_the_events_scope(self):
        """rates/yields/items chưa từng ingest KHÔNG được kéo scope events xuống."""
        state = _store_state(events="fresh", items="unavailable", rates="unavailable",
                             yields="unavailable")

        assert _provider(_FakeRepository(state=state)).news_events_scope() == "fresh"

    def test_store_state_failure_fails_closed(self):
        repo = _FakeRepository(fail=("store_state",))

        assert _provider(repo).news_events_scope() == "unavailable"

    def test_method_does_not_change_the_five_duck_typed_methods(self):
        """Thêm method mới KHÔNG được đổi shape 5 method cũ."""
        provider = NewsMacroProvider(
            _FakeRepository(),
            observability=SimpleNamespace(emit=lambda *a, **k: None),
            clock=lambda: NOW,
        )

        assert callable(provider.news_events_scope)
        for name in (
            "preload_macro_contexts",
            "latest_macro_context",
            "data_quality_flags",
            "macro_freshness_status",
            "execution_news_status",
        ):
            assert callable(getattr(provider, name))


# ===========================================================================
# 7. execution_news_status — blackout
# ===========================================================================


class TestExecutionNewsStatus:
    def test_blackout_covers_before_and_after_the_event(self):
        provider_events = [_event("EUR", hours=0.33, title="ECB Rate Decision")]  # +20 phút
        before = _provider(_FakeRepository(events=provider_events)).execution_news_status(
            "EUR/USD", before_minutes=30, after_minutes=15, now=NOW
        )
        after = _provider(
            _FakeRepository(events=[_event("EUR", hours=-0.16)])
        ).execution_news_status("EUR/USD", before_minutes=30, after_minutes=15, now=NOW)

        assert before["available"] is True and before["blackout"] is True
        assert before["reason_codes"] == ["NEWS_BLACKOUT"]
        assert before["event"]["event"] == "ECB Rate Decision"
        assert after["available"] is True and after["blackout"] is True

    def test_event_outside_the_window_is_allowed(self):
        result = _provider(
            _FakeRepository(events=[_event("EUR", hours=1.0), _event("EUR", hours=-0.5)])
        ).execution_news_status("EUR/USD", before_minutes=30, after_minutes=15, now=NOW)

        assert result["available"] is True and result["blackout"] is False
        assert result["reason_codes"] == []

    def test_low_impact_event_never_blackouts(self):
        result = _provider(
            _FakeRepository(events=[_event("EUR", hours=0.1, impact="low")])
        ).execution_news_status("EUR/USD", now=NOW)

        assert result["blackout"] is False

    def test_nearest_event_wins_when_several_are_inside_the_window(self):
        result = _provider(
            _FakeRepository(
                events=[
                    _event("EUR", hours=0.4, title="Far"),
                    _event("EUR", hours=0.05, title="Near"),
                ]
            )
        ).execution_news_status("EUR/USD", before_minutes=30, after_minutes=30, now=NOW)

        assert result["event"]["event"] == "Near"

    def test_unavailable_events_scope_fails_closed(self):
        state = _store_state(events="unavailable")

        result = _provider(_FakeRepository(state=state)).execution_news_status(
            "EUR/USD", now=NOW
        )

        assert result["available"] is False
        assert result["blackout"] is None
        assert NEWS_STATUS_UNAVAILABLE in result["reason_codes"]

    def test_degraded_events_scope_stays_available(self):
        state = _store_state(events="degraded")

        result = _provider(
            _FakeRepository(state=state, events=[_event("EUR", hours=0.2)])
        ).execution_news_status("EUR/USD", now=NOW)

        assert result["available"] is True and result["blackout"] is True

    def test_window_is_filtered_to_the_pair_currencies(self):
        repo = _FakeRepository(events=[_event("JPY", hours=0.2)])

        _provider(repo).execution_news_status("EUR/USD", now=NOW)

        _, (from_utc, to_utc, currencies), _ = next(
            call for call in repo.calls if call[0] == "events_in_range"
        )
        assert currencies == ["EUR", "USD"]
        assert from_utc == _iso(NOW - timedelta(minutes=30))
        assert to_utc == _iso(NOW + timedelta(minutes=30))


# ===========================================================================
# 8. vix_pair_aware_enabled
# ===========================================================================


class _FakeSettings:
    def __init__(self, value: bool, *, raises: bool = False) -> None:
        self.value = value
        self.raises = raises
        self.loads = 0

    def load(self):
        self.loads += 1
        if self.raises:
            raise RuntimeError("settings unreadable")
        return SimpleNamespace(advanced=SimpleNamespace(vix_pair_aware_enabled=self.value))


class TestVixFlag:
    def test_flag_is_read_from_settings(self):
        settings = _FakeSettings(True)
        repo = _FakeRepository(items=[_item("ECB holds")])

        flags = _provider(repo, settings=settings).data_quality_flags("EUR/USD")

        assert flags["vix_pair_aware_enabled"] is True

    def test_flag_fails_closed_on_settings_error(self):
        settings = _FakeSettings(True, raises=True)
        repo = _FakeRepository(items=[_item("ECB holds")])

        flags = _provider(repo, settings=settings).data_quality_flags("EUR/USD")

        assert flags["vix_pair_aware_enabled"] is False

    def test_flag_is_cached_for_sixty_seconds(self):
        settings = _FakeSettings(True)
        clock = _MutableClock(NOW)
        provider = NewsMacroProvider(
            _FakeRepository(items=[_item("ECB holds")]),
            settings_service=settings,
            observability=SimpleNamespace(emit=lambda *a, **k: None),
            clock=clock,
        )

        provider.data_quality_flags("EUR/USD")
        assert settings.loads == 1

        clock.advance(seconds=30)
        provider.data_quality_flags("EUR/USD", include_latest_statements=False)
        assert settings.loads == 1  # còn trong TTL 60s

        clock.advance(seconds=40)
        provider.data_quality_flags("EUR/USD")
        assert settings.loads == 2


# ===========================================================================
# 9. Không I/O mạng / không đụng hệ cũ
# ===========================================================================


class TestIsolation:
    def test_no_network_on_the_macro_path(self, monkeypatch):
        import socket

        def _no_socket(*args, **kwargs):
            raise AssertionError("I/O mạng trên đường vĩ mô")

        monkeypatch.setattr(socket, "socket", _no_socket)
        monkeypatch.setattr(socket, "create_connection", _no_socket)
        repo = _FakeRepository(
            events=[_event("EUR", hours=3.0)],
            items=[_item("ECB holds")],
            rates=[_rate("EUR", 3.5, "hold")],
            yields=[_yield_snapshot(-0.3)],
        )

        context = _provider(repo).latest_macro_context("EUR/USD")

        assert context["macro_alignment_scores"]["buy"] >= 0

    def test_module_does_not_import_the_legacy_news_stack(self):
        import ast
        from pathlib import Path

        import services.news_macro_provider as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        roots: set[str] = set()
        imported: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    roots.add(alias.name.split(".")[0])
                    imported.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
                imported.add(node.module)

        legacy = {"news_service", "forex_factory_client", "interest_rate_service"}
        assert not {name for name in imported if name in legacy}
        assert not {root for root in roots if root in legacy}
        assert "yfinance" not in roots and "requests" not in roots
