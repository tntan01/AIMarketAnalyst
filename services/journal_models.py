"""Journal data models — pure data classes without service logic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.safe_types import optional_float

SQLITE_TIMEOUT_SECONDS = 15
SQLITE_BUSY_TIMEOUT_MS = SQLITE_TIMEOUT_SECONDS * 1000


@dataclass(frozen=True, slots=True)
class JournalEntry:
    id: int | None
    timestamp_utc: str
    saved_at_utc: str
    symbol: str
    broker_symbol: str
    mode: str
    data_source: str
    market_regime: str
    decision: str
    direction_bias: str
    trade_permission: str
    buy_score: int
    sell_score: int
    selected_scenario: str
    entry_zone: str
    stop_loss: str
    take_profit: str
    risk_reward: str
    suggested_lot: float | None
    ai_commentary: str
    analysis_json: str
    user_action: str = ""
    result: str = ""
    note: str = ""
    # Phase 7 — account guard fields (đợt 1)
    result_r: float | None = None
    result_pct: float | None = None
    closed_at: str | None = None
    exit_reason: str | None = None
    actual_lot: float | None = None
    planned_lot: float | None = None
    # Phase 17 — journal execution fields (đợt 2)
    planned_entry: float | None = None
    actual_entry: float | None = None
    planned_sl: float | None = None
    actual_sl: float | None = None
    planned_tp: float | None = None
    actual_tp: float | None = None
    actual_exit: float | None = None
    setup_type: str | None = None
    regime: str | None = None
    session: str | None = None
    m15_quality: str | None = None
    spread_at_entry: float | None = None
    expected_effective_rr: float | None = None
    realized_effective_rr: float | None = None
    manual_mistake_tags: str | None = None
    auto_mistake_tags: str | None = None
    execution_quality_score: int | None = None
    # Trade lifecycle fields
    trade_status: str | None = "planned"
    opened_at: str | None = None
    result_amount: float | None = None
    mt5_deal_id: int | None = None
    mt5_order_id: int | None = None
    mt5_position_id: int | None = None
    synced_from: str | None = None
    synced_at_utc: str | None = None


@dataclass(frozen=True, slots=True)
class JournalFilter:
    date_from: str | None = None
    date_to: str | None = None
    symbol: str | None = None
    decision: str | None = None
    permission: str | None = None
    min_score: int = 0
