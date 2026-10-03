"""WI-4 — đấu nối runtime Scanner ↔ `NewsMacroProvider` + vá 2 gap.

Phủ:

* `ScannerController.__init__` mặc định dùng `NewsMacroProvider` (tên thuộc tính
  `news_service` giữ nguyên để không phá fixture duck-type).
* **Gap 2 (`news_in_3h`)**: event high-impact cách +2h → `data_quality_flags` bật
  cờ → packet mang cờ → `_analyze_one_symbol` chuyển vào `derive_live_analysis`
  → `detect_market_regime` nhận cờ (dấu vết: secondary `news_sensitive`).
* **Gap 1 (`news_events`)**: `_fetch_one_symbol_mt5` truyền events thật của cặp
  vào safety context → sub-gate News của `MarketSafetyGate` BLOCK [0,30'] và
  CAUTION (30,180']; nguồn chưa xác nhận → UNKNOWN (fail-closed).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from controllers import scanner_controller as scanner_module
from core.market_safety_gate import MarketSafetyGate
from core.reason_codes import (
    MACRO_CALENDAR_STALE,
    SAFETY_NEWS_HIGH_IMPACT_BLOCK,
    SAFETY_NEWS_HIGH_IMPACT_CAUTION,
    SAFETY_NEWS_SOURCE_UNAVAILABLE,
)
from core.scanner_composition import (
    AccountState,
    JournalState,
    PortfolioState,
)
from core.scanner_live_producers import build_live_market_safety_context
from core.scanner_order_policy import load_runtime_order_policy
from services.news_macro_provider import NewsMacroProvider

# Fixture dùng chung (nến/technical + harness MT5 giả).
from tests.test_news_macro_provider import (
    _event,
    _FakeRepository,
    _item,
    _rate,
    _provider,
)
from tests.test_scanner_live_gates import _FetchMT5
from tests.test_scanner_composition import NOW as FIXTURE_NOW
from tests.test_scanner_release import _zoned_candles


# ===========================================================================
# Đấu nối nguồn (WI-4, phần 1)
# ===========================================================================


def _bare_controller(**overrides):
    """ScannerController với mọi service nặng được thay bằng fake (không chạm đĩa)."""
    kwargs = {
        "settings_service": SimpleNamespace(),
        "mt5": SimpleNamespace(),
        "telegram_service": SimpleNamespace(),
        "journal_service": SimpleNamespace(),
        "retention_service": SimpleNamespace(),
        "job_state": SimpleNamespace(),
    }
    kwargs.update(overrides)
    return scanner_module.ScannerController(**kwargs)


class TestWiringSource:
    def test_controller_defaults_to_the_news_macro_provider(self):
        controller = _bare_controller()

        assert isinstance(controller.news_service, NewsMacroProvider)

    def test_attribute_name_stays_news_service(self):
        """Fixture/test cũ duck-type theo TÊN method trên `news_service`."""
        stub = SimpleNamespace()
        controller = _bare_controller(news_service=stub)

        assert controller.news_service is stub
        for method in (
            "preload_macro_contexts",
            "latest_macro_context",
            "data_quality_flags",
            "macro_freshness_status",
            "execution_news_status",
        ):
            assert callable(getattr(NewsMacroProvider, method))

    def test_module_no_longer_imports_the_legacy_news_service(self):
        import ast
        from pathlib import Path

        source = Path(scanner_module.__file__).read_text(encoding="utf-8")
        imported: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)

        assert "services.news_service" not in imported
        assert "services.news_macro_provider" in imported


# ===========================================================================
# Gap 2 — news_in_3h chảy tới regime
# ===========================================================================


def _pin_packet(
    *,
    news_in_3h: bool | None = None,
    macro_context: dict | None = None,
    macro_freshness: dict | None = None,
) -> dict:
    d1, h4, h1 = _zoned_candles()
    data_quality = {"tick_size": 0.01, "tick_size_source": "trade_tick_size"}
    if macro_freshness is not None:
        data_quality["macro_freshness"] = macro_freshness
    packet = {
        "symbol": "XAUUSD",
        "broker_symbol": "XAUUSDc",
        "candles": {"D1": d1, "H4": h4, "H1": h1},
        "macro_context": macro_context if macro_context is not None else {},
        "input_timestamps": {},
        "data_quality": data_quality,
        "v4_safety": build_live_market_safety_context(
            "XAUUSD",
            FIXTURE_NOW,
            terminal_connected=True,
            broker_logged_in=True,
            connectivity_checked_at=FIXTURE_NOW,
            last_candle_time_utc=FIXTURE_NOW,
            data_checked_at=FIXTURE_NOW,
            spread_points=20.0,
            spread_checked_at=FIXTURE_NOW,
            news_source_verified=True,
            news_checked_at=FIXTURE_NOW,
            volatility_ratio=1.0,
            volatility_checked_at=FIXTURE_NOW,
        ),
        "v4_captured_at": FIXTURE_NOW,
        "location_cutoff": FIXTURE_NOW,
        "v4_observed_at": FIXTURE_NOW,
        "account": AccountState(free_margin=10000.0, required_margin=500.0),
        "portfolio": PortfolioState(open_positions=0, exposure_ratio=0.1),
        "journal": JournalState(consecutive_losses=1, recent_drawdown_ratio=0.05),
    }
    if news_in_3h is not None:
        packet["news_in_3h"] = news_in_3h
    return packet


def _run_analysis(packet: dict, monkeypatch) -> dict:
    seen: dict[str, object] = {}
    real = scanner_module.derive_live_analysis

    def _spy(*args, **kwargs):
        seen["news_in_3h"] = kwargs.get("news_in_3h")
        return real(*args, **kwargs)

    monkeypatch.setattr(scanner_module, "derive_live_analysis", _spy)
    scanner_module._analyze_one_symbol(
        packet,
        correlation_context={},
        freshness_multiplier=1.0,
        contract_size_overrides={},
        analysis_input_kwargs={},
        closed_trades=[],
        account_guard_settings={},
        order_policy=load_runtime_order_policy(),
        now=FIXTURE_NOW,
    )
    return seen


class TestNewsIn3hGap:
    def test_flag_from_the_packet_reaches_the_analysis(self, monkeypatch):
        seen = _run_analysis(_pin_packet(news_in_3h=True), monkeypatch)

        assert seen["news_in_3h"] is True

    def test_packet_without_the_flag_keeps_the_old_behaviour(self, monkeypatch):
        """Pin A ghim hành vi cũ: packet không có key → False (không đổi kết quả)."""
        seen = _run_analysis(_pin_packet(), monkeypatch)

        assert seen["news_in_3h"] is False

    def test_provider_flag_for_an_event_two_hours_ahead_is_true(self):
        """Event high-impact cách +2h → `data_quality_flags` bật `news_in_3h`."""
        provider = _provider(
            _FakeRepository(
                events=[_event("EUR", hours=2.0)],
                items=[_item("ECB holds")],
                rates=[_rate("EUR", 3.5, "hold")],
            )
        )

        flags = provider.data_quality_flags("EUR/USD")

        assert flags["news_in_3h"] is True
        assert flags["high_impact_event_within_30m"] is False
        assert flags["next_high_impact_event"]["currency"] == "EUR"

    def test_end_to_end_flag_flows_from_provider_to_the_regime_detector(self, monkeypatch):
        """Chuỗi đầy đủ: provider → packet → `_analyze_one_symbol` → regime."""
        provider = _provider(
            _FakeRepository(
                events=[_event("EUR", hours=2.0)],
                items=[_item("ECB holds")],
                rates=[_rate("EUR", 3.5, "hold")],
            )
        )
        flags = provider.data_quality_flags("EUR/USD")
        packet = _pin_packet(news_in_3h=flags["news_in_3h"], macro_context=flags["macro_context"])
        seen: dict[str, object] = {}
        real_analysis = scanner_module.derive_live_analysis

        def _analysis_spy(*args, **kwargs):
            seen["analysis_flag"] = kwargs.get("news_in_3h")
            return real_analysis(*args, **kwargs)

        import core.scanner_live_producers as producers

        real_regime = producers.detect_market_regime

        def _regime_spy(technical, news_in_3h):
            seen["regime_flag"] = news_in_3h
            return real_regime(technical, news_in_3h)

        monkeypatch.setattr(scanner_module, "derive_live_analysis", _analysis_spy)
        monkeypatch.setattr(producers, "detect_market_regime", _regime_spy)
        scanner_module._analyze_one_symbol(
            packet,
            correlation_context={},
            freshness_multiplier=1.0,
            contract_size_overrides={},
            analysis_input_kwargs={},
            closed_trades=[],
            account_guard_settings={},
            order_policy=load_runtime_order_policy(),
            now=FIXTURE_NOW,
        )

        assert seen["analysis_flag"] is True
        assert seen["regime_flag"] is True

    def test_news_in_3h_tags_the_regime_news_sensitive(self):
        """Dấu vết THẬT của cờ trong bộ dò regime hiện hành.

        `detect_market_regime` thêm secondary `news_sensitive` khi news_in_3h;
        secondary này KHÔNG tự biến regime thành `volatile` (chỉ ATR spike mới
        thêm `volatile`) — xem báo cáo WI-4 về chênh lệch với mô tả plan.
        """
        from core.scanner_live_producers import resolve_technical_regime
        from core.technical_context import detect_market_regime

        technical = {
            "atr_h4": 1.0, "atr_avg_14d": 1.0, "price": 100.0,
            "ema50_d1": 100.0, "ema200_d1": 100.0, "structure_h4": "mixed",
            "range_info": None,
        }

        detection = detect_market_regime(technical, True)

        assert "news_sensitive" in detection["secondary"]
        assert "volatile" not in detection["secondary"]
        # Với technical này cờ không đổi regime cuối — pin lại đúng hành vi hiện có.
        assert resolve_technical_regime(technical, True) == resolve_technical_regime(
            technical, False
        )


# ===========================================================================
# Gap 1 — news_events vào safety context
# ===========================================================================


class _NewsStub:
    """Duck-type `data_quality_flags` của provider cho `_fetch_one_symbol_mt5`."""

    def __init__(self, events, *, news_in_3h: bool = False) -> None:
        self._events = list(events)
        self._news_in_3h = news_in_3h

    def data_quality_flags(self, symbol, ai_service=None, performance_tracker=None):
        return {
            "macro_context": {"events": list(self._events)},
            "news_in_3h": self._news_in_3h,
            "high_impact_event_within_30m": False,
            "next_high_impact_event": None,
            "resume_after": None,
            "vix_pair_aware_enabled": False,
        }


def _high_impact_event(minutes_ahead: float, *, impact: str = "high") -> dict:
    return {
        "currency": "EUR",
        "event": "ECB Rate Decision",
        "impact": impact,
        "forecast": None,
        "previous": None,
        "actual": None,
        "time_utc": (
            datetime.now(UTC) + timedelta(minutes=minutes_ahead)
        ).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }


def _fetch_packet(stub: _NewsStub, *, freshness: dict) -> dict:
    return scanner_module._fetch_one_symbol_mt5(
        "EUR/USD",
        mt5=_FetchMT5(),
        available_symbols=["EURUSDc"],
        bars_by_timeframe={"D1": 300, "H4": 300, "H1": 300},
        news_service=stub,
        freshness=freshness,
        v4_account=AccountState(free_margin=500.0, required_margin=None),
    )


def _news_check_status(packet: dict) -> tuple[str, tuple[str, ...]]:
    result = MarketSafetyGate().evaluate(
        packet["v4_safety"],
        load_runtime_order_policy().safety,
        now=datetime.now(UTC),
    )
    check = next(item for item in result.checks if item.name == "news")
    return check.status, tuple(check.reason_codes)


_FRESH = {
    "status": "fresh",
    "age_minutes": 1,
    "confidence_multiplier": 1.0,
    "events_scope": "fresh",
}


class TestNewsEventsGap:
    def test_events_are_carried_into_the_safety_context(self):
        packet = _fetch_packet(_NewsStub([_high_impact_event(15.0)]), freshness=_FRESH)

        events = packet["v4_safety"].news.events
        assert len(events) == 1
        assert events[0]["event"] == "ECB Rate Decision"

    def test_high_impact_event_within_thirty_minutes_blocks(self):
        packet = _fetch_packet(_NewsStub([_high_impact_event(15.0)]), freshness=_FRESH)

        status, codes = _news_check_status(packet)

        assert status == "BLOCK"
        assert SAFETY_NEWS_HIGH_IMPACT_BLOCK in codes

    def test_high_impact_event_in_the_caution_window_cautions(self):
        packet = _fetch_packet(_NewsStub([_high_impact_event(60.0)]), freshness=_FRESH)

        status, codes = _news_check_status(packet)

        assert status == "CAUTION"
        assert SAFETY_NEWS_HIGH_IMPACT_CAUTION in codes

    def test_event_beyond_the_caution_window_passes(self):
        packet = _fetch_packet(_NewsStub([_high_impact_event(200.0)]), freshness=_FRESH)

        status, _ = _news_check_status(packet)

        assert status == "PASS"

    def test_low_impact_event_does_not_trip_the_gate(self):
        packet = _fetch_packet(
            _NewsStub([_high_impact_event(15.0, impact="low")]), freshness=_FRESH
        )

        status, _ = _news_check_status(packet)

        assert status == "PASS"

    def test_no_event_with_a_verified_source_is_a_genuine_pass(self):
        packet = _fetch_packet(_NewsStub([]), freshness=_FRESH)

        status, _ = _news_check_status(packet)

        assert status == "PASS"

    def test_unverified_source_stays_unknown_even_with_events(self):
        """Fail-closed: nguồn không khai được scope events thì event KHÔNG tự chặn/PASS."""
        packet = _fetch_packet(
            _NewsStub([_high_impact_event(15.0)]),
            freshness={"confidence_multiplier": 1.0},  # thiếu events_scope
        )

        status, codes = _news_check_status(packet)

        assert status == "UNKNOWN"
        assert SAFETY_NEWS_SOURCE_UNAVAILABLE in codes

    def test_unavailable_events_scope_leaves_the_source_unverified(self):
        packet = _fetch_packet(
            _NewsStub([_high_impact_event(15.0)]),
            freshness={"events_scope": "unavailable", "confidence_multiplier": 0.6},
        )

        status, codes = _news_check_status(packet)

        assert status == "UNKNOWN"
        assert SAFETY_NEWS_SOURCE_UNAVAILABLE in codes

    def test_expired_worst_of_four_does_not_block_when_events_are_fresh(self):
        """WI-4b: multiplier vẫn worst-of-4, nhưng 'nguồn đã xác nhận' theo scope EVENTS.

        scope rates/yields/items chưa từng ingest → `status=expired` (confidence
        tụt đúng thiết kế) nhưng KHÔNG được khóa News sub-gate khi events tươi.
        """
        packet = _fetch_packet(
            _NewsStub([_high_impact_event(15.0)]),
            freshness={
                "status": "expired",
                "age_minutes": 9999,
                "confidence_multiplier": 0.6,
                "events_scope": "fresh",
            },
        )

        status, codes = _news_check_status(packet)

        assert status == "BLOCK"
        assert SAFETY_NEWS_HIGH_IMPACT_BLOCK in codes

    def test_events_fresh_with_non_events_scopes_unavailable_still_blocks(self):
        """(a) yields+rates unavailable + events fresh → sub-gate chặn theo event thật."""
        stub = _NewsStub([_high_impact_event(15.0)])
        stub.news_events_scope = lambda: "fresh"  # type: ignore[attr-defined]

        packet = _fetch_packet(
            stub,
            freshness={
                "status": "expired",  # worst-of-4: yields chưa từng ingest
                "age_minutes": 9999,
                "confidence_multiplier": 0.6,
                "events_scope": scanner_module._news_events_scope(stub),
            },
        )

        status, codes = _news_check_status(packet)

        assert status == "BLOCK"
        assert SAFETY_NEWS_HIGH_IMPACT_BLOCK in codes

    def test_degraded_events_scope_still_counts_as_verified(self):
        """(c) degraded = dữ liệu CÓ thật (cũ) → vẫn verified, chặn theo event."""
        packet = _fetch_packet(
            _NewsStub([_high_impact_event(15.0)]),
            freshness={"events_scope": "degraded", "confidence_multiplier": 0.85},
        )

        status, codes = _news_check_status(packet)

        assert status == "BLOCK"
        assert SAFETY_NEWS_HIGH_IMPACT_BLOCK in codes

    def test_stale_freshness_still_counts_as_verified(self):
        """`degraded` = dữ liệu CÓ thật (chỉ cũ) → sub-gate vẫn đọc được event."""
        packet = _fetch_packet(
            _NewsStub([_high_impact_event(15.0)]),
            freshness={"status": "stale", "age_minutes": 600, "confidence_multiplier": 0.85,
                       "events_scope": "fresh"},
        )

        status, codes = _news_check_status(packet)

        assert status == "BLOCK"
        assert SAFETY_NEWS_HIGH_IMPACT_BLOCK in codes

    def test_packet_carries_news_in_3h_from_the_flags(self):
        with_flag = _fetch_packet(
            _NewsStub([_high_impact_event(120.0)], news_in_3h=True), freshness=_FRESH
        )
        without_flag = _fetch_packet(_NewsStub([]), freshness=_FRESH)

        assert with_flag["news_in_3h"] is True
        assert without_flag["news_in_3h"] is False


def _run_analysis_row(packet: dict) -> dict:
    """Chạy `_analyze_one_symbol` trên packet đã dựng và trả ROW."""
    return scanner_module._analyze_one_symbol(
        packet,
        correlation_context={},
        freshness_multiplier=1.0,
        contract_size_overrides={},
        analysis_input_kwargs={},
        closed_trades=[],
        account_guard_settings={},
        order_policy=load_runtime_order_policy(),
        now=FIXTURE_NOW,
    )


class TestCalendarStaleRowFlag:
    """WI-6: `MACRO_CALENDAR_STALE` là DISPLAY-ONLY, đi từ packet sang bucket row."""

    def test_row_copies_the_flag_from_macro_freshness(self):
        packet = _pin_packet(
            macro_freshness={
                "status": "stale",
                "age_minutes": 600,
                "confidence_multiplier": 0.85,
                "reason_codes": [MACRO_CALENDAR_STALE],
            }
        )

        row = _run_analysis_row(packet)

        assert row["macro"]["freshness_reason_codes"] == [MACRO_CALENDAR_STALE]
        # Không rò vào decision/gate codes.
        assert MACRO_CALENDAR_STALE not in (row.get("reason_codes") or [])
        assert MACRO_CALENDAR_STALE not in (row.get("macro_reason_codes") or [])
        assert MACRO_CALENDAR_STALE not in (row.get("gate_codes") or [])
        assert MACRO_CALENDAR_STALE not in (row.get("block_codes") or [])

    def test_row_flag_is_empty_when_the_calendar_is_fresh(self):
        packet = _pin_packet(
            macro_freshness={
                "status": "fresh",
                "age_minutes": 1,
                "confidence_multiplier": 1.0,
                "reason_codes": [],
            }
        )

        row = _run_analysis_row(packet)

        assert row["macro"]["freshness_reason_codes"] == []

    def test_missing_key_on_old_fixtures_yields_empty_list(self):
        """(d) packet cũ/fake thiếu `reason_codes` → [], không lỗi."""
        without_freshness = _pin_packet()
        without_codes = _pin_packet(macro_freshness={"status": "stale"})

        assert (
            _run_analysis_row(without_freshness)["macro"][
                "freshness_reason_codes"
            ]
            == []
        )
        assert (
            _run_analysis_row(without_codes)["macro"][
                "freshness_reason_codes"
            ]
            == []
        )

    def test_malformed_reason_codes_do_not_crash(self):
        packet = _pin_packet(macro_freshness={"reason_codes": "MACRO_CALENDAR_STALE"})

        row = _run_analysis_row(packet)

        assert row["macro"]["freshness_reason_codes"] == []


class TestEventsScopeProbe:
    """WI-4b: seam đọc RIÊNG scope sự kiện, fail-closed khi không khai được."""

    def test_probe_reads_the_provider_scope(self):
        stub = SimpleNamespace(news_events_scope=lambda: "degraded")

        assert scanner_module._news_events_scope(stub) == "degraded"

    def test_probe_normalises_and_fails_closed_on_empty(self):
        assert (
            scanner_module._news_events_scope(
                SimpleNamespace(news_events_scope=lambda: "  FRESH ")
            )
            == "fresh"
        )
        assert (
            scanner_module._news_events_scope(SimpleNamespace(news_events_scope=lambda: ""))
            == "unavailable"
        )

    def test_probe_fails_closed_without_the_method(self):
        """Bản cũ `NewsService` không khai được scope events → không suy đoán."""
        assert scanner_module._news_events_scope(SimpleNamespace()) == "unavailable"
        assert scanner_module._news_events_scope(None) == "unavailable"

    def test_probe_fails_closed_when_the_probe_raises(self):
        def _boom():
            raise RuntimeError("db down")

        stub = SimpleNamespace(news_events_scope=_boom)

        assert scanner_module._news_events_scope(stub) == "unavailable"


# ===========================================================================
# Hợp đồng dữ liệu: ISO có tz (ràng buộc WI-2)
# ===========================================================================


class TestProviderValuesAreIsoAware:
    def test_event_time_and_published_are_timezone_aware(self):
        """`macro_context` cấp cho Scanner phải là ISO có tz (bản cũ TypeError nếu naive)."""
        provider = _provider(
            _FakeRepository(
                events=[_event("EUR", hours=2.0)],
                items=[_item("ECB holds")],
                rates=[_rate("EUR", 3.5, "hold")],
            )
        )

        context = provider.latest_macro_context("EUR/USD")

        for event in context["events"]:
            parsed = datetime.fromisoformat(event["time_utc"].replace("Z", "+00:00"))
            assert parsed.tzinfo is not None
        for headline in context["latest_headlines"]:
            parsed = datetime.fromisoformat(headline["published_utc"].replace("Z", "+00:00"))
            assert parsed.tzinfo is not None
