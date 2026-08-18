from __future__ import annotations

import pytest
from services.mt5_service import MT5Service
from services.journal_service import JournalService, JournalEntry

class MockDeal:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

class MockMT5Module:
    DEAL_ENTRY_IN = 0
    DEAL_ENTRY_OUT = 1
    DEAL_ENTRY_INOUT = 2
    DEAL_TYPE_BUY = 0
    DEAL_TYPE_SELL = 1

def test_closed_trades_from_deals_parsing():
    service = MT5Service()
    # Mock profiles config
    service.symbol_profiles = {
        "EUR/USD": {"mt5_aliases": ["EURUSD", "EURUSDm", "EURUSDc"]},
        "GBP/USD": {"mt5_aliases": ["GBPUSD", "GBPUSDm", "GBPUSDc"]}
    }
    
    # Create mock deals for one position
    # Position ID 123: Buy 0.1 lot EUR/USD, entry at 1.0850, exit at 1.0900.
    deals = [
        MockDeal(
            symbol="EURUSDm",
            type=0, # BUY
            position_id=123,
            entry=0, # IN
            time=1770000000,
            volume=0.1,
            price=1.0850,
            profit=0.0,
            commission=-1.5,
            swap=-0.5,
            ticket=1001,
            order=2001,
            comment="AMA-FWD:abc123",
        ),
        MockDeal(
            symbol="EURUSDm",
            type=1, # SELL to close
            position_id=123,
            entry=1, # OUT
            time=1770003600,
            volume=0.1,
            price=1.0900,
            profit=50.0,
            commission=-1.5,
            swap=-0.5,
            ticket=1002,
            order=2002,
            comment="",
        )
    ]
    
    parsed = service._closed_trades_from_deals(MockMT5Module(), deals)
    assert len(parsed) == 1
    trade = parsed[0]
    
    assert trade["symbol"] == "EUR/USD" # Resolved through app_symbol_for_broker_symbol
    assert trade["broker_symbol"] == "EURUSDm"
    assert trade["side"] == "buy"
    assert trade["opened_at"] == "2026-02-02T02:40:00Z"
    assert trade["closed_at"] == "2026-02-02T03:40:00Z"
    assert trade["actual_entry"] == 1.0850
    assert trade["actual_exit"] == 1.0900
    assert trade["actual_lot"] == 0.1
    # profit (50) + commission (-3.0) + swap (-1.0) = 46.0
    assert trade["result_amount"] == 46.0
    assert trade["mt5_deal_id"] == 1002
    assert trade["mt5_position_id"] == 123
    assert trade["candidate_id"] == "abc123"

def test_closed_trades_from_deals_includes_sl_from_position_map():
    service = MT5Service()
    service.symbol_profiles = {
        "EUR/USD": {"mt5_aliases": ["EURUSDm", "EURUSDc"]},
    }
    deals = [
        MockDeal(
            symbol="EURUSDm", type=0, position_id=123, entry=0, time=1770000000,
            volume=0.1, price=1.0850, profit=0.0, commission=-1.5, swap=-0.5,
            ticket=1001, order=2001, comment="AMA-FWD:abc123",
        ),
        MockDeal(
            symbol="EURUSDm", type=1, position_id=123, entry=1, time=1770003600,
            volume=0.1, price=1.0900, profit=50.0, commission=-1.5, swap=-0.5,
            ticket=1002, order=2002, comment="",
        ),
    ]
    parsed = service._closed_trades_from_deals(
        MockMT5Module(), deals, position_sl_map={123: 1.0800}
    )
    assert len(parsed) == 1
    assert parsed[0]["actual_sl"] == 1.0800


def test_closed_trades_from_deals_no_sl_map_emits_none():
    service = MT5Service()
    service.symbol_profiles = {"EUR/USD": {"mt5_aliases": ["EURUSDm"]}}
    deals = [
        MockDeal(symbol="EURUSDm", type=0, position_id=5, entry=0, time=1770000000,
                 volume=0.1, price=1.0850, profit=0.0, commission=0.0, swap=0.0,
                 ticket=1, order=1, comment=""),
        MockDeal(symbol="EURUSDm", type=1, position_id=5, entry=1, time=1770003600,
                 volume=0.1, price=1.0900, profit=50.0, commission=0.0, swap=0.0,
                 ticket=2, order=2, comment=""),
    ]
    parsed = service._closed_trades_from_deals(MockMT5Module(), deals)
    assert parsed[0]["actual_sl"] is None


def test_scale_in_and_partial_close_prices_are_volume_weighted():
    service = MT5Service()
    service.symbol_profiles = {
        "EUR/USD": {"mt5_aliases": ["EURUSDm"]},
    }

    # Scale-in: 0.1 @ 1.0850 then 0.2 @ 1.0860.
    # Partial close: 0.1 @ 1.0900 then 0.2 @ 1.0910.
    deals = [
        MockDeal(symbol="EURUSDm", type=0, position_id=7, entry=0, time=1770000000,
                 volume=0.1, price=1.0850, profit=0.0, commission=0.0, swap=0.0,
                 ticket=1, order=1, comment="AMA-FWD:x"),
        MockDeal(symbol="EURUSDm", type=0, position_id=7, entry=0, time=1770000001,
                 volume=0.2, price=1.0860, profit=0.0, commission=0.0, swap=0.0,
                 ticket=2, order=2, comment=""),
        MockDeal(symbol="EURUSDm", type=1, position_id=7, entry=1, time=1770003600,
                 volume=0.1, price=1.0900, profit=10.0, commission=0.0, swap=0.0,
                 ticket=3, order=3, comment=""),
        MockDeal(symbol="EURUSDm", type=1, position_id=7, entry=1, time=1770003601,
                 volume=0.2, price=1.0910, profit=20.0, commission=0.0, swap=0.0,
                 ticket=4, order=4, comment=""),
    ]

    parsed = service._closed_trades_from_deals(MockMT5Module(), deals)
    assert len(parsed) == 1
    trade = parsed[0]
    assert trade["actual_lot"] == 0.3
    # entry=(1.0850*0.1+1.0860*0.2)/0.3 ; exit=(1.0900*0.1+1.0910*0.2)/0.3
    import pytest
    assert abs(trade["actual_entry"] - (1.0850 * 0.1 + 1.0860 * 0.2) / 0.3) < 1e-9
    assert abs(trade["actual_exit"] - (1.0900 * 0.1 + 1.0910 * 0.2) / 0.3) < 1e-9
    assert trade["result_amount"] == pytest.approx(30.0)


def test_mt5_sync_does_not_wipe_existing_result_r_when_payload_has_no_sl(temp_db_path):
    # A closed journal row already has a computed result_r (no SL was ever set).
    # An MT5 sync payload carries actual_entry/actual_exit but no stop-loss, so
    # outcome is empty here — this must NOT null out the existing result
    # metrics (the bug wiped result_r/result_pct on every sync without SL).
    service = JournalService(db_path=temp_db_path)
    entry = JournalEntry(
        id=None,
        timestamp_utc="2026-01-24T18:00:00Z",
        saved_at_utc="2026-01-24T18:00:01Z",
        symbol="EUR/USD",
        broker_symbol="EURUSDm",
        mode="scanner_detail",
        data_source="MT5",
        market_regime="trending_up",
        decision="ready",
        direction_bias="buy",
        trade_permission="allowed",
        buy_score=85,
        sell_score=20,
        selected_scenario="buy",
        entry_zone="",
        stop_loss="",
        take_profit="",
        risk_reward="",
        suggested_lot=0.1,
        ai_commentary="",
        analysis_json="{}",
        trade_status="closed",
        closed_at="2026-01-24T19:40:00Z",
        result_r=1.0,
        result_pct=0.5,
        realized_effective_rr=1.0,
        result="win",
    )
    entry_id = service.create(entry)

    service.update_lifecycle(
        entry_id,
        {
            "trade_status": "closed",
            "closed_at": "2026-01-24T19:40:00Z",
            "actual_entry": 1.0850,
            "actual_exit": 1.0900,
            "mt5_deal_id": 1002,
            "synced_from": "mt5_history",
        },
    )

    updated = service.get_entry(entry_id)
    assert updated.result_r == 1.0
    assert updated.result_pct == 0.5
    assert updated.realized_effective_rr == 1.0


def test_sync_mt5_closed_trades_crud(temp_db_path):
    service = JournalService(db_path=temp_db_path)
    
    # 1. Create a planned journal entry that will match
    planned = JournalEntry(
        id=None,
        timestamp_utc="2026-01-24T18:00:00Z",
        saved_at_utc="2026-01-24T18:00:01Z",
        symbol="EUR/USD",
        broker_symbol="EURUSDm",
        mode="scanner_detail",
        data_source="MT5",
        market_regime="trending_up",
        decision="ready",
        direction_bias="buy",
        trade_permission="allowed",
        buy_score=85,
        sell_score=20,
        selected_scenario="buy",
        entry_zone="[1.0845, 1.0855]",
        stop_loss="1.0800",
        take_profit="1.0950",
        risk_reward="3.0",
        suggested_lot=0.1,
        ai_commentary="",
        analysis_json="{}",
        trade_status="planned",
        planned_entry=1.0850,
        planned_sl=1.0800,
        planned_tp=1.0950,
    )
    planned_id = service.create(planned)
    
    # 2. Simulate importing a matching MT5 trade
    mt5_trade = {
        "symbol": "EUR/USD",
        "broker_symbol": "EURUSDm",
        "side": "buy",
        "opened_at": "2026-01-24T18:40:00Z",
        "closed_at": "2026-01-24T19:40:00Z",
        "actual_entry": 1.0850,
        "actual_exit": 1.0900,
        "actual_lot": 0.1,
        "result_amount": 46.0,
        "exit_reason": "TP hit",
        "mt5_deal_id": 1002,
        "mt5_order_id": 2002,
        "mt5_position_id": 123,
    }
    
    sync_result = service.sync_mt5_closed_trades([mt5_trade])
    assert sync_result["received"] == 1
    assert sync_result["created"] == 0
    assert sync_result["updated"] == 1
    assert sync_result["skipped"] == 0
    
    # Verify the matching entry was updated
    synced_entry = service.get_entry(planned_id)
    assert synced_entry.trade_status == "closed"
    assert synced_entry.mt5_deal_id == 1002
    assert synced_entry.result == "win"
    assert synced_entry.result_r == 1.0 # (1.0900 - 1.0850) / (1.0850 - 1.0800) = 0.0050 / 0.0050 = 1.0R
    
    # 3. Simulate importing a non-matching trade (should auto-create a new entry)
    new_mt5_trade = {
        "symbol": "GBP/USD",
        "broker_symbol": "GBPUSDm",
        "side": "sell",
        "opened_at": "2026-01-24T20:00:00Z",
        "closed_at": "2026-01-24T21:00:00Z",
        "actual_entry": 1.2500,
        "actual_exit": 1.2550, # loss for sell
        "actual_lot": 0.2,
        "result_amount": -100.0,
        "exit_reason": "SL hit",
        "mt5_deal_id": 1004,
        "mt5_order_id": 2004,
        "mt5_position_id": 124,
    }
    
    sync_result_new = service.sync_mt5_closed_trades([new_mt5_trade])
    assert sync_result_new["received"] == 1
    assert sync_result_new["created"] == 1
    assert sync_result_new["updated"] == 0
    
    created_id = sync_result_new["synced_entry_ids"][0]
    created_entry = service.get_entry(created_id)
    assert created_entry.symbol == "GBP/USD"
    assert created_entry.trade_status == "closed"
    assert created_entry.result == "loss"


def test_sync_mt5_closed_trade_computes_result_r_from_synced_sl(temp_db_path):
    # F1: once an MT5 sync payload carries `actual_sl` (from order history), the
    # journal must compute+persist `result_r` for a then-created entry.
    service = JournalService(db_path=temp_db_path)
    mt5_trade = {
        "symbol": "EUR/USD",
        "broker_symbol": "EURUSDm",
        "side": "buy",
        "opened_at": "2026-02-10T10:00:00Z",
        "closed_at": "2026-02-10T11:00:00Z",
        "actual_entry": 1.1000,
        "actual_exit": 1.1050,
        "actual_sl": 1.0900,
        "actual_lot": 0.1,
        "result_amount": 50.0,
        "exit_reason": "TP hit",
        "mt5_deal_id": 9001,
        "mt5_order_id": 9002,
        "mt5_position_id": 900,
    }
    sync_result = service.sync_mt5_closed_trades([mt5_trade])
    assert sync_result["received"] == 1
    assert sync_result["created"] == 1
    created_id = sync_result["synced_entry_ids"][0]
    entry = service.get_entry(created_id)
    assert entry.actual_sl == 1.0900
    # (1.1050 - 1.1000) / (1.1000 - 1.0900) = 0.0050 / 0.0100 = 0.5R
    assert entry.result_r == 0.5
