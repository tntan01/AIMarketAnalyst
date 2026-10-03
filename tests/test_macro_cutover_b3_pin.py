"""B3 pin (WI-1) — ghim hành vi TIÊU THỤ vĩ mô của Scanner (Pin A).

Đây là pin sống sau cutover: `docs/macro/macro_score_architecture.md` mục 0.4.
Test gọi `ScannerController._analyze_one_symbol` với packet fixture +
`macro_context` cố định 3 kịch bản (aligned / conflict / low-confidence) và
ghim lại `macro_status`, `macro_reason_codes`, `candidate_status`,
`decision_cap`, `row["macro"]["macro_confidence"]`, `row["economic_events"]`.

WI-7: cụm **Pin B** (công thức 3-tier trên path cũ `NewsService`) đã hoàn thành
sứ mệnh oracle trước cutover và được gỡ cùng `services/news_service.py`; các
hằng số Pin B + test ghim giá trị nay nằm ở `tests/test_macro_tiers.py` (chạy
trên `core.macro_tiers` thuần).

Phạm vi thay đổi được phép sau cutover (đã ghi ở contract §0.2, KHÔNG tính là
lệch pin): AI stance bị bỏ khỏi Tier 1, chuỗi đường cong 10y-5y → 2y-10y,
semantics freshness theo `store_state` thay cho tuổi lần fetch.
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

