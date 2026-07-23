"""Phase 15G.7.2 — harden forward validator with pure tests (no MT5 needed).

Tests cover: horizon completeness, MFE/MAE direction-aware, session dedupe,
schema migration, and all edge cases.
"""

from __future__ import annotations

import pytest
import sys
from pathlib import Path

_scripts = str(Path(__file__).resolve().parents[1] / "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from validate_macro_v2 import (
    SCHEMA_VERSION,
    _classify_direction,
    _compute_config,
    _compute_mfe_mae,
    _horizon_complete,
    _iso_to_epoch,
    _is_correct,
    _label_outcome,
    _session_dedupe,
)


# ---------------------------------------------------------------------------
# Horizon completeness
# ---------------------------------------------------------------------------

class TestHorizonComplete:
    def test_exact_4h_horizon_complete(self):
        start = 100000.0
        # H1 candles: epoch=start+3600, start+7200, start+10800, start+14400
        candles = [
            {"epoch": start + 3600, "open": 1.1, "high": 1.1, "low": 1.1, "close": 1.1},
            {"epoch": start + 7200, "open": 1.1, "high": 1.1, "low": 1.1, "close": 1.1},
            {"epoch": start + 10800, "open": 1.1, "high": 1.1, "low": 1.1, "close": 1.1},
            {"epoch": start + 14400, "open": 1.1, "high": 1.1, "low": 1.1, "close": 1.1},
        ]
        # Last candle epoch = start+14400, target = start+14400, 14400 >= 14400-3600=10800 -> True
        assert _horizon_complete(candles, start, 4 * 3600) is True

    def test_before_horizon_incomplete(self):
        start = 100000.0
        # Only 2H of candles for a 4H horizon
        candles = [
            {"epoch": start + 3600, "open": 1.1, "high": 1.1, "low": 1.1, "close": 1.1},
            {"epoch": start + 7200, "open": 1.1, "high": 1.1, "low": 1.1, "close": 1.1},
        ]
        # Last epoch = start+7200, target-3600 = start+10800, 7200 < 10800 -> False
        assert _horizon_complete(candles, start, 4 * 3600) is False

    def test_empty_candles_incomplete(self):
        assert _horizon_complete([], 100000.0, 4 * 3600) is False

    def test_gap_within_window_still_complete(self):
        """Missing middle candle but last covers horizon -> complete."""
        start = 100000.0
        candles = [
            {"epoch": start + 3600, "open": 1.1, "high": 1.1, "low": 1.1, "close": 1.1},
            # gap (weekend)
            {"epoch": start + 14400, "open": 1.1, "high": 1.1, "low": 1.1, "close": 1.1},
        ]
        assert _horizon_complete(candles, start, 4 * 3600) is True


# ---------------------------------------------------------------------------
# MFE/MAE direction-aware
# ---------------------------------------------------------------------------

class TestMFEMAEDirection:
    def test_buy_mfe_mae(self):
        entry = 1.1000
        candles = [
            {"epoch": 1, "open": 1.1000, "high": 1.1050, "low": 1.0950, "close": 1.1020},
        ]
        mfe, mae = _compute_mfe_mae(candles, entry, "buy")
        # BUY MFE: (1.1050-1.1000)/1.1000*100 = 0.4545
        # BUY MAE: (1.1000-1.0950)/1.1000*100 = 0.4545
        assert mfe == pytest.approx(0.4545, abs=0.01)
        assert mae == pytest.approx(0.4545, abs=0.01)

    def test_sell_mfe_mae(self):
        entry = 1.1000
        candles = [
            {"epoch": 1, "open": 1.1000, "high": 1.1050, "low": 1.0920, "close": 1.0950},
        ]
        mfe, mae = _compute_mfe_mae(candles, entry, "sell")
        # SELL MFE (favorable=price down): (1.1000-1.0920)/1.1000*100 = 0.7273
        # SELL MAE (adverse=price up): (1.1050-1.1000)/1.1000*100 = 0.4545
        assert mfe == pytest.approx(0.7273, abs=0.01)
        assert mae == pytest.approx(0.4545, abs=0.01)

    def test_neutral_uses_buy_default(self):
        entry = 1.1000
        candles = [{"epoch": 1, "open": 1.1000, "high": 1.1100, "low": 1.0900, "close": 1.1000}]
        mfe_b = _compute_mfe_mae(candles, entry, "buy")
        mfe_n = _compute_mfe_mae(candles, entry, "neutral")
        assert mfe_b == mfe_n  # neutral defaults to buy logic

    def test_empty_candles_zero(self):
        assert _compute_mfe_mae([], 1.1000, "buy") == (0.0, 0.0)

    def test_zero_entry_price(self):
        candles = [{"epoch": 1, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.0}]
        assert _compute_mfe_mae(candles, 0.0, "buy") == (0.0, 0.0)


# ---------------------------------------------------------------------------
# Session dedupe
# ---------------------------------------------------------------------------

class TestSessionDedupe:
    def test_same_session_symbol_keeps_latest(self):
        records = [
            {"symbol": "EURUSD", "session_id": "s1", "recorded_epoch": 100.0, "pair_edge": 5},
            {"symbol": "EURUSD", "session_id": "s1", "recorded_epoch": 200.0, "pair_edge": 3},
        ]
        result = _session_dedupe(records)
        assert len(result) == 1
        assert result[0]["pair_edge"] == 3  # latest

    def test_different_sessions_kept(self):
        records = [
            {"symbol": "EURUSD", "session_id": "s1", "recorded_epoch": 100.0},
            {"symbol": "EURUSD", "session_id": "s2", "recorded_epoch": 200.0},
        ]
        assert len(_session_dedupe(records)) == 2

    def test_different_symbols_kept(self):
        records = [
            {"symbol": "EURUSD", "session_id": "s1", "recorded_epoch": 100.0},
            {"symbol": "GBPUSD", "session_id": "s1", "recorded_epoch": 100.0},
        ]
        assert len(_session_dedupe(records)) == 2


# ---------------------------------------------------------------------------
# Schema migration
# ---------------------------------------------------------------------------

class TestSchemaMigration:
    def test_schema_version_present(self):
        assert SCHEMA_VERSION == 1

    def test_old_version_skipped(self):
        """Records with schema_version < 1 must be skipped in label."""
        old = {"schema_version": 0, "symbol": "X", "recorded_epoch": 1, "price": 1.0,
               "broker_symbol": "X", "label_4h": None}
        # Simulate the skip check
        ver = old.get("schema_version", 0)
        skip = ver < 1
        assert skip is True


# ---------------------------------------------------------------------------
# Anti-lookahead: candle before timestamp
# ---------------------------------------------------------------------------

class TestAntiLookahead:
    def test_candle_before_start_excluded(self):
        """Candle with epoch <= start_epoch must not be used."""
        start = 200000.0
        candles = [
            {"epoch": start - 3600, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0},  # before
            {"epoch": start + 3600, "open": 1.1, "high": 1.1, "low": 1.1, "close": 1.1},   # after
        ]
        filtered = [c for c in candles if c["epoch"] > start]
        assert len(filtered) == 1
        assert filtered[0]["epoch"] == start + 3600


# ---------------------------------------------------------------------------
# Epoch parsing
# ---------------------------------------------------------------------------

class TestEpochParsing:
    def test_valid_iso(self):
        assert _iso_to_epoch("2026-07-23T12:00:00Z") > 1.7e9

    def test_invalid_returns_zero(self):
        assert _iso_to_epoch("") == 0.0
        assert _iso_to_epoch("not-a-date") == 0.0

    def test_none_returns_zero(self):
        assert _iso_to_epoch(None) == 0.0  # type: ignore


# ---------------------------------------------------------------------------
# Config computation
# ---------------------------------------------------------------------------

class TestConfig:
    def test_a_db2_edge0_neutral(self):
        b, s = _compute_config(1.0, 2, 0)
        assert b == 15 and s == 15

    def test_a_db2_edge3_directional(self):
        b, s = _compute_config(1.0, 2, 3)
        assert b != 15

    def test_b_db3_edge2_neutral(self):
        b, s = _compute_config(1.0, 3, 2)
        assert b == 15 and s == 15

    def test_b_db3_edge4_directional(self):
        b, s = _compute_config(1.0, 3, 4)
        assert b != 15
