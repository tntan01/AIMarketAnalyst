"""B3 pin (WI-1) — ghim đặc tính đường vĩ mô HIỆN HÀNH trước ca đấu nối (b).

Đây là **oracle tương đương** cho ca đấu nối (b): `docs/macro/macro_score_architecture.md`
mục 0.4 bước 1. Test chạy trên **path cũ** (`services/news_service.py` +
`ScannerController._analyze_one_symbol`) và ghim lại đúng những giá trị mà
cutover sang `NewsMacroProvider`/`core.macro_tiers` **phải tái lập**.

Hai cụm:

* **Pin A — tiêu thụ:** `_analyze_one_symbol` với packet fixture + `macro_context`
  cố định 3 kịch bản (aligned / conflict / low-confidence) → `macro_status`,
  `macro_reason_codes`, `candidate_status`, `decision_cap`,
  `row["macro"]["macro_confidence"]`, `row["economic_events"]`.
* **Pin B — công thức:** `NewsService._compute_macro_tiers(..., ai_service=None)`
  (đường "AI off" — chính là hành vi đích) → `tier1/tier2/tier3/raw_total` ghim
  bằng hằng số.

Phạm vi thay đổi được phép sau cutover (đã ghi ở contract §0.2, KHÔNG tính là
lệch pin): AI stance bị bỏ khỏi Tier 1 (ở đây đã chạy AI-off), chuỗi đường cong
10y-5y → 2y-10y, semantics freshness theo `store_state` thay cho tuổi lần fetch.
Ngoài ba điểm đó, Pin A và Pin B phải khớp tuyệt đối.

Chỉ là test characterization: KHÔNG sửa code nguồn, KHÔNG ghim hành vi mong
muốn — ghim hành vi đang có.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.reason_codes import (
    MACRO_ALIGNED,
    MACRO_CONFLICT,
    MACRO_LOW_CONFIDENCE,
)
from core.scanner_composition import (
    AccountState,
    JournalState,
    PortfolioState,
)
from core.scanner_live_producers import build_live_market_safety_context
from core.scanner_order_policy import load_runtime_order_policy
from services.news_service import MacroGlobalSnapshot, NewsService

# Fixture nến/H4-H1 dùng chung với test_scanner_release: H4 có swing thật nên
# technical kết luận được cả hai phía (ngược với `_live_candles` — bộ đó fail
# closed ở SMC nên `selected_side=None`, không quan sát được gate vĩ mô).
from tests.test_scanner_composition import NOW as FIXTURE_NOW
from tests.test_scanner_release import _zoned_candles


# ===========================================================================
# Pin A — tiêu thụ: `_analyze_one_symbol` (packet fixture + macro_context cố định)
# ===========================================================================

# Sự kiện cố định tuyệt đối: `_analyze_one_symbol` chỉ copy nguyên
# `macro_context["events"]` sang `row["economic_events"]` — không đọc đồng hồ.
_PIN_A_EVENTS = [
    {
        "currency": "USD",
        "event": "Non-Farm Payrolls",
        "impact": "high",
        "time_utc": "2026-08-13T17:00:00+00:00",
    }
]

# Ba kịch bản của contract §4. Deadband đã khóa = 3 (config/scanner_order_policy.json),
# confidence_threshold = 0.6, conflict_cap = WATCH_ZONE, unknown_cap = DATA_UNAVAILABLE.
_PIN_A_ALIGNED = {
    "macro_alignment_scores": {"buy": 18, "sell": 8},  # lệch 10 > deadband 3
    "macro_data_quality": 0.9,
    "events": _PIN_A_EVENTS,
}
_PIN_A_CONFLICT = {
    "macro_alignment_scores": {"buy": 8, "sell": 18},  # lệch 10 về phía SELL
    "macro_data_quality": 0.9,
    "events": _PIN_A_EVENTS,
}
_PIN_A_LOW_CONFIDENCE = {
    "macro_alignment_scores": {"buy": 18, "sell": 8},
    "macro_data_quality": 0.4,  # 0.4 × freshness 1.0 = 0.4 < 0.6
    "events": _PIN_A_EVENTS,
}


def _scanner_safety(observed_at: datetime):
    """Safety context của packet: mọi nguồn có dữ liệu tại `observed_at` (PASS)."""
    return build_live_market_safety_context(
        "XAUUSD",
        observed_at,
        terminal_connected=True,
        broker_logged_in=True,
        connectivity_checked_at=observed_at,
        last_candle_time_utc=observed_at,
        data_checked_at=observed_at,
        spread_points=20.0,
        spread_checked_at=observed_at,
        news_source_verified=True,
        news_checked_at=observed_at,
        volatility_ratio=1.0,
        volatility_checked_at=observed_at,
    )


def _packet(macro_context: dict) -> dict:
    """Packet theo khuôn `test_scanner_h02_integration.py` (đồng hồ = đồng hồ fixture)."""
    d1, h4, h1 = _zoned_candles()
    return {
        "symbol": "XAUUSD",
        "broker_symbol": "XAUUSDc",
        "candles": {"D1": d1, "H4": h4, "H1": h1},
        "macro_context": macro_context,
        "input_timestamps": {},
        # SMC cần tick_size có provenance hợp lệ, nếu không technical fail closed
        # (`_fetch_one_symbol_mt5` lấy hai khóa này từ `mt5.symbol_data_quality`).
        "data_quality": {"tick_size": 0.01, "tick_size_source": "trade_tick_size"},
        "v4_safety": _scanner_safety(FIXTURE_NOW),
        "v4_captured_at": FIXTURE_NOW,
        "location_cutoff": FIXTURE_NOW,
        "v4_observed_at": FIXTURE_NOW,
        # Ba gate phụ được cấp dữ liệu TỐI THIỂU đạt PASS (cùng giá trị
        # `tests/test_scanner_composition._snapshot`) để trong pin này **macro là
        # gate duy nhất** quyết định `candidate_status`.
        "account": AccountState(free_margin=10000.0, required_margin=500.0),
        "portfolio": PortfolioState(open_positions=0, exposure_ratio=0.1),
        "journal": JournalState(consecutive_losses=1, recent_drawdown_ratio=0.05),
    }


def _run_pin_a(macro_context: dict, *, freshness_multiplier: float = 1.0) -> dict:
    from controllers import scanner_controller

    return scanner_controller._analyze_one_symbol(
        _packet(macro_context),
        correlation_context={},
        freshness_multiplier=freshness_multiplier,
        contract_size_overrides={},
        analysis_input_kwargs={},
        closed_trades=[],
        account_guard_settings={},
        order_policy=load_runtime_order_policy(),
        now=FIXTURE_NOW,
    )


class TestPinAConsumption:
    """Pin A: hợp đồng tiêu thụ của Scanner với `macro_context` không đổi sau cutover."""

    def test_aligned_context_passes_macro_gate(self):
        row = _run_pin_a(_PIN_A_ALIGNED)

        # Harness: phía được chọn là buy (technical của fixture kết luận được).
        assert row["selected_side"] == "buy"
        assert row["macro_status"] == "PASS"
        assert MACRO_ALIGNED in row["macro_reason_codes"]
        assert row["decision_cap"] is None
        # Mọi gate PASS + điểm trên sàn (technical 55 / setup 53 so với 40/35).
        assert row["candidate_status"] == "WAITING_CONFIRMATION"
        assert row["reason_codes"] == ["GATES_ALL_PASS"]

        assert row["macro"]["macro_confidence"] == pytest.approx(0.9)
        assert row["macro"]["macro_data_quality"] == pytest.approx(0.9)
        assert row["economic_events"] == _PIN_A_EVENTS

    def test_conflicting_context_caps_candidate_to_watch_zone(self):
        row = _run_pin_a(_PIN_A_CONFLICT)

        assert row["selected_side"] == "buy"
        assert row["macro_status"] == "CAUTION"
        assert MACRO_CONFLICT in row["macro_reason_codes"]
        # Cap WATCH_ZONE của MacroPolicy được mang nguyên vào quyết định.
        assert row["decision_cap"] == "WATCH_ZONE"
        assert row["candidate_status"] == "WATCH_ZONE"

        assert row["macro"]["macro_confidence"] == pytest.approx(0.9)
        assert row["economic_events"] == _PIN_A_EVENTS

    def test_low_confidence_blocks_through_unknown_macro_gate(self):
        row = _run_pin_a(_PIN_A_LOW_CONFIDENCE)

        assert row["selected_side"] == "buy"
        # Macro là critical gate: UNKNOWN (do confidence < ngưỡng) → BLOCKED.
        assert row["macro_status"] == "UNKNOWN"
        assert MACRO_LOW_CONFIDENCE in row["macro_reason_codes"]
        assert MACRO_LOW_CONFIDENCE in row["reason_codes"]
        assert row["decision_cap"] == "DATA_UNAVAILABLE"
        assert row["candidate_status"] == "BLOCKED"

        # Confidence = macro_data_quality × freshness_multiplier (1.0 ở đây).
        assert row["macro"]["macro_confidence"] == pytest.approx(0.4)
        assert row["macro"]["macro_data_quality"] == pytest.approx(0.4)
        assert row["economic_events"] == _PIN_A_EVENTS

    def test_confidence_multiplier_scales_the_same_context(self):
        """Freshness multiplier là hệ số DUY NHẤT giữa quality thô và confidence."""
        row = _run_pin_a(_PIN_A_LOW_CONFIDENCE, freshness_multiplier=0.5)

        assert row["macro"]["macro_confidence"] == pytest.approx(0.2)
        assert row["macro_status"] == "UNKNOWN"
        assert row["candidate_status"] == "BLOCKED"


# ===========================================================================
# Pin B — công thức: `NewsService._compute_macro_tiers` (AI-off)
# ===========================================================================

_PIN_B_CURRENCIES = ["EUR", "USD"]

# Rate cố định: EUR hike 3.5% / USD hold 5.0%.
# rate_diff = -1.5 → diff 0/1; trend hike(4) - hold(2) = 2 → 3/1;
# stance hawkish(1) - dovish(-1) = 2 → 4/0; yield spread -0.35 < 0 và cặp có USD,
# base không phải USD → ±2. Tier 1 = 9 / 0.
_PIN_B_RATES = {
    "EUR": {"rate": 3.5, "trend": "hike", "rate_label": "3.50%"},
    "USD": {"rate": 5.0, "trend": "hold", "rate_label": "5.00%"},
}

# Headline cố định: EUR hawkish, USD dovish (keyword stance — đường AI-off).
# Lexicon Tier 3 trên toàn bộ title: "rate cut" +2, "optimism" +2, "slowdown" -1,
# "hawkish" -2, "rally" +1 → raw_sentiment +2 → sentiment 5/8 → risk_on.
_PIN_B_HEADLINES = [
    {
        "title": "ECB signals hawkish stance as inflation above target",
        "published_utc": "2026-08-13T10:00:00+00:00",
        "currencies": ["EUR"],
    },
    {
        "title": "Fed officials signal rate cut as slowdown deepens",
        "published_utc": "2026-08-13T09:00:00+00:00",
        "currencies": ["USD"],
    },
    {
        "title": "Global markets rally as optimism returns",
        "published_utc": "2026-08-13T11:00:00+00:00",
        "currencies": [],
    },
]

# Event đặt lệch hẳn khỏi biên bucket time_weight (6/24/48h) để pin không phụ
# thuộc thời điểm chạy: +20h → weight 2.0; +50h → weight 1.0 (và < cutoff 72h).
_PIN_B_EVENT_OFFSETS_HOURS = (20, 50)

# Giá trị ghim (chạy trên path cũ tại HEAD 02/10/2026).
_PIN_B_TIER1 = {"buy": 9, "sell": 0}
_PIN_B_TIER2 = {"buy": 5, "sell": 5}  # Phase 15C: calendar luôn trung lập
_PIN_B_TIER3 = {"buy": 6, "sell": 4}
_PIN_B_RAW_TOTAL = {"buy": 20, "sell": 9}


def _pin_b_snapshot(now: datetime) -> MacroGlobalSnapshot:
    """Snapshot toàn cục cố định (thay cho fetch ^TNX/^FVX/^VIX qua mạng)."""
    return MacroGlobalSnapshot(
        fetched_at_utc=now,
        expires_at_utc=now + timedelta(hours=1),
        tnx=4.25,
        fvx=4.60,
        yield_spread_10y_5y=-0.35,
        yield_steepening=False,
        vix=18.0,
        global_headlines=(),
        official_statements=(),
        calendar_payload={},
        source_status={},
        stale_fields=(),
    )


def _pin_b_events(now: datetime) -> list[dict]:
    return [
        {
            "currency": "EUR",
            "event": "ECB Interest Rate Decision",
            "impact": "high",
            "time_utc": (
                now + timedelta(hours=_PIN_B_EVENT_OFFSETS_HOURS[0])
            ).isoformat(),
        },
        {
            "currency": "USD",
            "event": "US CPI",
            "impact": "high",
            "time_utc": (
                now + timedelta(hours=_PIN_B_EVENT_OFFSETS_HOURS[1])
            ).isoformat(),
        },
    ]


def _run_pin_b(monkeypatch) -> tuple[dict, NewsService]:
    # Rate cố định: chặn hẳn FRED/FF/config (không I/O mạng trên đường vĩ mô).
    monkeypatch.setattr(
        NewsService,
        "_load_interest_rates",
        classmethod(lambda cls: _PIN_B_RATES),
    )
    service = NewsService()
    now = datetime.now(timezone.utc)
    result = service._compute_macro_tiers(
        "EURUSD",
        _PIN_B_CURRENCIES,
        _PIN_B_HEADLINES,
        _pin_b_events(now),
        [],  # themes — không dùng trong công thức 3-tier
        [],  # hotspots — giữ trung lập địa chính trị (geo 2/2)
        ai_service=None,  # AI-off = hành vi đích của cutover
        global_snapshot=_pin_b_snapshot(now),
    )
    return result, service


class TestPinBFormula:
    """Pin B: công thức 3-tier phải khớp tuyệt đối sau khi port sang `core/macro_tiers`."""

    def test_tiers_and_raw_total_are_pinned(self, monkeypatch):
        result, _ = _run_pin_b(monkeypatch)

        for tier_name, expected in (
            ("tier1", _PIN_B_TIER1),
            ("tier2", _PIN_B_TIER2),
            ("tier3", _PIN_B_TIER3),
        ):
            tier = result[tier_name]
            assert tier["buy"] == expected["buy"], tier_name
            assert tier["sell"] == expected["sell"], tier_name

        assert dict(result["raw_total"]) == _PIN_B_RAW_TOTAL
        # `alignment` là bản sao raw (shape cũ giữ nguyên cho Scanner).
        assert dict(result["alignment"]) == _PIN_B_RAW_TOTAL

    def test_tier_details_pin_the_intended_paths(self, monkeypatch):
        """Chi tiết đủ để chứng minh fixture chạm đúng các nhánh công thức."""
        result, _ = _run_pin_b(monkeypatch)

        tier1 = result["tier1"]["detail"]
        assert tier1["rate_differential"] == pytest.approx(-1.5)
        assert tier1["base_stance"] == "hawkish"
        assert tier1["quote_stance"] == "dovish"
        assert tier1["yield_spread_adj"] == {"buy": 2, "sell": -2}
        assert tier1["components"]["rate_diff"] == {"buy": 0, "sell": 1}
        assert tier1["components"]["rate_trend"] == {"buy": 3, "sell": 1}
        assert tier1["components"]["stance"] == {"buy": 4, "sell": 0}

        tier2 = result["tier2"]["detail"]
        assert tier2["base_event_count"] == 1
        assert tier2["quote_event_count"] == 1
        assert tier2["event_risk_score"] == 9
        assert tier2["event_risk_level"] == "high"
        assert [event["time_weight"] for event in tier2["base_events"]] == [2.0]
        assert [event["time_weight"] for event in tier2["quote_events"]] == [1.0]

        tier3 = result["tier3"]["detail"]
        assert tier3["raw_sentiment"] == 2
        assert tier3["sentiment_score_0_8"] == 5
        assert tier3["risk_sentiment"] == "risk_on"
        assert tier3["components"]["risk_sentiment"] == {"buy": 4, "sell": 2}
        assert tier3["components"]["geopolitical"] == {"buy": 2, "sell": 2}

    def test_ai_off_is_the_pinned_behaviour(self, monkeypatch):
        """Đường AI-off: stance lấy từ keyword và KHÔNG có verdict AI nào vào điểm."""
        result, _ = _run_pin_b(monkeypatch)

        assert result["tier3"]["detail"]["ai_sentiment_used"] is False
        assert result["tier3"]["detail"]["ai_applied_to_score"] is False
        assert result["tier3"]["detail"]["ai_sentiment_score"] is None
        for side in ("base", "quote"):
            assert result["stance_journal"][side]["source"] == "fallback"
            assert result["stance_journal"][side]["strength"] is None

    def test_repeated_call_is_stable(self, monkeypatch):
        """Cache stance trong instance không được làm đổi điểm giữa hai lần gọi."""
        result, service = _run_pin_b(monkeypatch)
        now = datetime.now(timezone.utc)
        again = service._compute_macro_tiers(
            "EURUSD",
            _PIN_B_CURRENCIES,
            _PIN_B_HEADLINES,
            _pin_b_events(now),
            [],
            [],
            ai_service=None,
            global_snapshot=_pin_b_snapshot(now),
        )

        assert dict(again["raw_total"]) == dict(result["raw_total"]) == _PIN_B_RAW_TOTAL
        assert again["tier1"]["buy"] == result["tier1"]["buy"]
        assert again["tier3"]["sell"] == result["tier3"]["sell"]
