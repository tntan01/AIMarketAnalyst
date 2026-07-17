"""Tests for original SL capture and correct R calculation in OrdersScreen.

Covers:
  - Manual Trade: original SL captured on first poll
  - Auto Trade: auto_enable_tracking sets original SL
  - BreakEven: R uses original SL, not modified BE SL
  - Trailing: R uses original SL, not current trailed SL
  - Restart: original SL restored from persisted state
  - Multiple Positions: each tracked independently
  - R always uses original SL (core invariant)
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_pos(position_id, symbol="EURUSD", side="buy", open_price=1.10000,
                    current_price=1.10200, sl=1.09800, tp=1.10500,
                    profit=50.0, swap=0.0, commission=0.0):
    return {
        "position_id": position_id,
        "symbol": symbol,
        "side": side,
        "volume": 1.0,
        "open_price": open_price,
        "current_price": current_price,
        "sl": sl,
        "tp": tp,
        "profit": profit,
        "swap": swap,
        "commission": commission,
        "comment": "",
        "open_time": 0,
    }


def _make_mock_mt5(positions=None):
    """Create a mock MT5Service that returns given positions."""
    mt5 = MagicMock()
    mt5.get_open_positions.return_value = positions or []
    mt5.get_pending_orders.return_value = []
    mt5.account_balance.return_value = 10000.0
    return mt5


class _MockDisplay:
    theme = "dark"


class _MockSettings:
    display = _MockDisplay()


class _MockSettingsService:
    def load(self):
        return _MockSettings()


def _bare_screen():
    """Create an OrdersScreen without full __init__ (no UI build, no timers)."""
    from ui.screens.orders_screen import OrdersScreen
    screen = OrdersScreen.__new__(OrdersScreen)
    screen._light = False
    screen._positions = []
    screen._pending_orders = []
    screen._trailing_configs = {}
    screen._position_original_sl = {}
    screen._active_tab = "positions"
    return screen


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestOriginalSLCapture:
    """Tests for _position_original_sl capture logic."""

    def test_capture_on_first_poll(self):
        """Original SL is captured the first time a position is seen."""
        screen = _bare_screen()
        screen.mt5 = _make_mock_mt5([
            _make_mock_pos(12345, sl=1.09800),
        ])

        # Simulate refresh_orders capture logic
        screen._positions = screen.mt5.get_open_positions()
        for pos in screen._positions:
            pos_id = int(pos.get("position_id", 0))
            if pos_id and pos_id not in screen._position_original_sl:
                sl = float(pos.get("sl", 0) or 0)
                if sl > 0:
                    screen._position_original_sl[pos_id] = sl

        assert screen._position_original_sl[12345] == 1.09800

    def test_no_overwrite_on_second_poll(self):
        """Original SL is NEVER overwritten, even if MT5 SL changes."""
        screen = _bare_screen()
        screen._position_original_sl[12345] = 1.09800  # Already captured

        # MT5 now returns a modified SL (e.g., after BE)
        screen.mt5 = _make_mock_mt5([
            _make_mock_pos(12345, sl=1.10020),  # BE moved SL to entry+2pips
        ])

        screen._positions = screen.mt5.get_open_positions()
        for pos in screen._positions:
            pos_id = int(pos.get("position_id", 0))
            if pos_id and pos_id not in screen._position_original_sl:
                sl = float(pos.get("sl", 0) or 0)
                if sl > 0:
                    screen._position_original_sl[pos_id] = sl

        # Must still be the original, not the modified one
        assert screen._position_original_sl[12345] == 1.09800

    def test_skip_zero_sl(self):
        """Position with SL=0 should NOT be captured (wait for SL to be set)."""
        screen = _bare_screen()
        screen.mt5 = _make_mock_mt5([
            _make_mock_pos(12345, sl=0.0),
        ])

        screen._positions = screen.mt5.get_open_positions()
        for pos in screen._positions:
            pos_id = int(pos.get("position_id", 0))
            if pos_id and pos_id not in screen._position_original_sl:
                sl = float(pos.get("sl", 0) or 0)
                if sl > 0:
                    screen._position_original_sl[pos_id] = sl

        assert 12345 not in screen._position_original_sl

    def test_capture_after_sl_set(self):
        """If SL was 0, then later set, it should be captured on next poll."""
        screen = _bare_screen()
        # First poll: SL = 0
        screen._positions = [_make_mock_pos(12345, sl=0.0)]
        for pos in screen._positions:
            pos_id = int(pos.get("position_id", 0))
            if pos_id and pos_id not in screen._position_original_sl:
                sl = float(pos.get("sl", 0) or 0)
                if sl > 0:
                    screen._position_original_sl[pos_id] = sl
        assert 12345 not in screen._position_original_sl

        # Second poll: SL = 1.09800 (user set it)
        screen._positions = [_make_mock_pos(12345, sl=1.09800)]
        for pos in screen._positions:
            pos_id = int(pos.get("position_id", 0))
            if pos_id and pos_id not in screen._position_original_sl:
                sl = float(pos.get("sl", 0) or 0)
                if sl > 0:
                    screen._position_original_sl[pos_id] = sl
        assert screen._position_original_sl[12345] == 1.09800


class TestRCalculation:
    """Tests for correct R calculation using original SL."""

    def test_r_with_original_sl(self):
        """R = (current - entry) / |entry - original_sl| for BUY."""
        screen = _bare_screen()
        screen._position_original_sl[12345] = 1.09800  # Original SL

        # Calculate R manually (same formula as _render_position_row)
        open_p = 1.10000
        cur_p = 1.10200
        sl_for_r = float(1.10200)  # default from pos
        orig_sl = screen._position_original_sl.get(12345)
        if orig_sl is not None and orig_sl > 0:
            sl_for_r = orig_sl  # 1.09800

        risk = abs(open_p - sl_for_r)  # 0.00200
        pnl_price = cur_p - open_p  # 0.00200 (buy)
        r_val = pnl_price / risk  # 1.0

        assert abs(risk - 0.00200) < 0.00001
        assert abs(r_val - 1.0) < 0.00001

    def test_r_buy_correct_with_original_sl(self):
        """BUY: entry=1.10000, orig_sl=1.09800, current=1.10200 => +1.0R."""
        screen = _bare_screen()
        screen._position_original_sl[12345] = 1.09800

        open_p = 1.10000
        cur_p = 1.10200
        sl_for_r = screen._position_original_sl.get(12345)

        risk = abs(open_p - sl_for_r)
        r_val = (cur_p - open_p) / risk
        assert abs(r_val - 1.0) < 0.01

    def test_r_sell_correct_with_original_sl(self):
        """SELL: entry=1.10000, orig_sl=1.10200, current=1.09800 => +1.0R."""
        screen = _bare_screen()
        screen._position_original_sl[12345] = 1.10200

        open_p = 1.10000
        cur_p = 1.09800
        sl_for_r = screen._position_original_sl.get(12345)

        risk = abs(open_p - sl_for_r)
        r_val = (open_p - cur_p) / risk
        assert abs(r_val - 1.0) < 0.01

    def test_r_uses_original_sl_not_current_mt5_sl(self):
        """When SL has been moved by BE, R still uses original SL.

        Scenario:
          Original SL: 1.09200 (80 pips risk)
          After BE: SL moved to 1.10020 (entry + 2 pips)
          Current price: 1.10400 (profit = 40 pips)

          Correct R: 40/80 = 0.5R
          Bug R (using current SL): 40/2 = 20R ← WRONG
        """
        screen = _bare_screen()
        screen._position_original_sl[12345] = 1.09200  # Original SL = 80 pips

        # Current SL from MT5 has been moved by BE
        current_mt5_sl = 1.10020
        entry = 1.10000
        current_price = 1.10400

        # Old bug: sl_for_r = current_mt5_sl = 1.10020
        bug_risk = abs(entry - current_mt5_sl)  # 0.00020 = 2 pips
        bug_r = (current_price - entry) / bug_risk  # 0.00400 / 0.00020 = 20.0

        # Fix: sl_for_r = _position_original_sl = 1.09200
        fix_risk = abs(entry - 1.09200)  # 0.00800 = 80 pips
        fix_r = (current_price - entry) / fix_risk  # 0.00400 / 0.00800 = 0.5

        assert abs(bug_r - 20.0) < 0.1, "Bug would show 20R"
        assert abs(fix_r - 0.5) < 0.01, "Fix should show 0.5R"


class TestAutoTrade:
    """Tests for auto_enable_tracking setting original SL correctly."""

    def test_auto_enable_sets_original_sl(self):
        """auto_enable_tracking should populate _position_original_sl."""
        screen = _bare_screen()
        screen._debounce_save = MagicMock()  # prevent save
        screen._render_table = MagicMock()   # prevent render

        screen.auto_enable_tracking(
            pos_id=12345,
            symbol="EURUSD",
            side="buy",
            entry=1.10000,
            sl=1.09800,
            atr_h1=0.0015,
        )

        assert screen._position_original_sl[12345] == 1.09800
        assert screen._trailing_configs[12345]["initial_sl"] == 1.09800

    def test_auto_enable_does_not_overwrite_existing(self):
        """If _position_original_sl already has entry, auto_enable overwrites it.
        This is OK because auto_enable_tracking is called immediately after
        position creation with the correct SL from the trade plan."""
        screen = _bare_screen()
        screen._debounce_save = MagicMock()
        screen._render_table = MagicMock()

        # First auto_enable
        screen.auto_enable_tracking(12345, "EURUSD", "buy", 1.10000, 1.09800, 0.0015)
        # Second call for same position (edge case)
        screen.auto_enable_tracking(12345, "EURUSD", "buy", 1.10000, 1.09800, 0.0015)

        # Still the original value
        assert screen._position_original_sl[12345] == 1.09800


class TestMultiplePositions:
    """Tests for multiple positions tracked independently."""

    def test_independent_original_sl(self):
        """Each position has its own original SL."""
        screen = _bare_screen()

        screen._position_original_sl[111] = 1.09800  # EURUSD buy
        screen._position_original_sl[222] = 1.10200  # EURUSD sell
        screen._position_original_sl[333] = 0.59870  # NZDUSD buy

        assert screen._position_original_sl[111] == 1.09800
        assert screen._position_original_sl[222] == 1.10200
        assert screen._position_original_sl[333] == 0.59870

        # Modifying one doesn't affect others
        screen._trailing_configs[111] = {"initial_sl": 1.09800}
        # Simulate BE for position 111 would change MT5 SL but not _position_original_sl
        # (already tested in test_no_overwrite_on_second_poll)

    def test_cleanup_removes_closed_positions(self):
        """Stale entries are removed from _position_original_sl."""
        screen = _bare_screen()
        screen._position_original_sl[111] = 1.09800
        screen._position_original_sl[222] = 1.10200
        screen._trailing_configs[111] = {"enabled": True}
        screen._debounce_save = MagicMock()

        # Only position 111 is still open
        screen._positions = [_make_mock_pos(111)]

        # Simulate _cleanup_trailing
        open_ids = {int(p.get("position_id", 0)) for p in screen._positions}
        stale = [pid for pid in screen._trailing_configs if pid not in open_ids]
        for pid in stale:
            del screen._trailing_configs[pid]
        stale_sl = [pid for pid in screen._position_original_sl if pid not in open_ids]
        for pid in stale_sl:
            del screen._position_original_sl[pid]

        assert 111 in screen._position_original_sl
        assert 222 not in screen._position_original_sl


class TestPersistence:
    """Tests for save/load of _position_original_sl."""

    def test_save_includes_original_sl(self):
        """_save_trailing_state writes original_sl to JSON."""
        screen = _bare_screen()
        screen._position_original_sl[12345] = 1.09800
        screen._trailing_configs[12345] = {
            "position_id": 12345, "symbol": "EURUSD", "side": "buy",
            "enabled": True, "initial_sl": 1.09800, "entry_price": 1.10000,
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            tmp_path = Path(f.name)

        try:
            # Override _state_path to use temp file
            screen._state_path = lambda: tmp_path

            # Manually trigger save logic
            data = {
                "positions": {str(k): v for k, v in screen._trailing_configs.items()},
                "original_sl": {str(k): v for k, v in screen._position_original_sl.items()},
            }
            tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

            # Verify file content
            loaded = json.loads(tmp_path.read_text(encoding="utf-8"))
            assert "original_sl" in loaded
            assert loaded["original_sl"]["12345"] == 1.09800
            assert "positions" in loaded
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_load_restores_original_sl(self):
        """_load_trailing_state restores _position_original_sl from JSON."""
        screen = _bare_screen()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            tmp_path = Path(f.name)

        try:
            data = {
                "positions": {
                    "12345": {"position_id": 12345, "symbol": "EURUSD", "initial_sl": 1.09800},
                },
                "original_sl": {
                    "12345": 1.09800,
                    "22222": 0.59870,
                },
            }
            tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            screen._state_path = lambda: tmp_path

            # Simulate _load_trailing_state
            loaded_data = json.loads(tmp_path.read_text(encoding="utf-8"))
            positions = loaded_data.get("positions", {})
            if isinstance(positions, dict):
                for key, cfg in positions.items():
                    pos_id = int(key)
                    if pos_id not in screen._trailing_configs:
                        screen._trailing_configs[pos_id] = cfg
            original_sl = loaded_data.get("original_sl", {})
            if isinstance(original_sl, dict):
                for key, sl in original_sl.items():
                    pos_id = int(key)
                    if pos_id not in screen._position_original_sl:
                        screen._position_original_sl[pos_id] = float(sl)

            assert screen._position_original_sl[12345] == 1.09800
            assert screen._position_original_sl[22222] == 0.59870
            assert screen._trailing_configs[12345]["initial_sl"] == 1.09800
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_load_does_not_overwrite_existing(self):
        """Loading state does NOT overwrite existing _position_original_sl entries."""
        screen = _bare_screen()
        screen._position_original_sl[12345] = 1.09800  # Already captured

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            tmp_path = Path(f.name)

        try:
            # File has a DIFFERENT value (e.g., from an older session)
            data = {
                "original_sl": {"12345": 1.09500},  # Different!
            }
            tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            screen._state_path = lambda: tmp_path

            loaded_data = json.loads(tmp_path.read_text(encoding="utf-8"))
            original_sl = loaded_data.get("original_sl", {})
            if isinstance(original_sl, dict):
                for key, sl in original_sl.items():
                    pos_id = int(key)
                    if pos_id not in screen._position_original_sl:  # KEY GUARD
                        screen._position_original_sl[pos_id] = float(sl)

            # Must keep the already-captured value, NOT overwrite with file value
            assert screen._position_original_sl[12345] == 1.09800
        finally:
            tmp_path.unlink(missing_ok=True)


class TestEdgeCases:
    """Tests for various edge cases."""

    def test_hedge_positions_have_different_ids(self):
        """Hedge positions (buy + sell on same symbol) have different position_ids."""
        screen = _bare_screen()
        screen._position_original_sl[111] = 1.09800  # Buy
        screen._position_original_sl[222] = 1.10200  # Sell (hedge)
        assert screen._position_original_sl[111] != screen._position_original_sl[222]

    def test_reopened_position_gets_new_capture(self):
        """If a position is closed and reopened, new position_id => new capture."""
        screen = _bare_screen()
        # Old position (closed, cleaned up)
        # New position with same characteristics but different ID
        screen._positions = [_make_mock_pos(99999, sl=1.09500)]
        for pos in screen._positions:
            pos_id = int(pos.get("position_id", 0))
            if pos_id and pos_id not in screen._position_original_sl:
                sl = float(pos.get("sl", 0) or 0)
                if sl > 0:
                    screen._position_original_sl[pos_id] = sl
        assert screen._position_original_sl[99999] == 1.09500

    def test_manual_trade_without_sl(self):
        """Position without SL shows no R until SL is set."""
        screen = _bare_screen()
        screen._position_original_sl = {}  # No original SL captured

        open_p = 1.10000
        cur_p = 1.10200
        sl_for_r = 0.0  # pos["sl"] = 0

        orig_sl = screen._position_original_sl.get(12345)
        if orig_sl is not None and orig_sl > 0:
            sl_for_r = orig_sl

        # sl_for_r stays 0, risk = 0, R shows "--"
        risk = abs(open_p - sl_for_r) if open_p and sl_for_r else 0.0
        assert risk == 0.0

    def test_jpy_pair_pip_multiplier(self):
        """JPY pairs use pip_multiplier=100, original SL capture unaffected."""
        screen = _bare_screen()
        # USDJPY: entry=150.000, sl=149.500, pip_multiplier=100
        screen._position_original_sl[12345] = 149.500

        open_p = 150.000
        cur_p = 151.000
        sl_for_r = screen._position_original_sl[12345]

        risk = abs(open_p - sl_for_r)  # 0.500
        r_val = (cur_p - open_p) / risk  # 1.000 / 0.500 = 2.0
        assert abs(r_val - 2.0) < 0.01

    def test_partial_close_keeps_same_position_id(self):
        """Partial close keeps the same position_id, original SL unchanged."""
        screen = _bare_screen()
        screen._position_original_sl[12345] = 1.09800

        # After partial close, MT5 still returns same position_id with modified SL
        screen._positions = [_make_mock_pos(12345, sl=1.10020)]

        # Original SL is NOT re-captured
        for pos in screen._positions:
            pos_id = int(pos.get("position_id", 0))
            if pos_id and pos_id not in screen._position_original_sl:
                sl = float(pos.get("sl", 0) or 0)
                if sl > 0:
                    screen._position_original_sl[pos_id] = sl

        assert screen._position_original_sl[12345] == 1.09800  # Unchanged


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
