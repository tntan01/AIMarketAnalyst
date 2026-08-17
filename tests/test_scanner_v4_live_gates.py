"""Scanner V4 live gate producers — controller-side unit tests.

Covers the REAL-data producers wired into the scan-level V4 states
(account / portfolio / journal gates).  Discipline: every value must come
from real data; anything unreadable fails closed to ``None`` (never invented).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import controllers.scanner_controller as scanner_module
from controllers.scanner_controller import (
    JOURNAL_DRAWDOWN_WINDOW_DAYS,
    _v4_consecutive_losses,
    _v4_exposure_ratio,
    _v4_open_positions,
    compute_recent_drawdown_ratio,
)

NOW = datetime(2026, 8, 16, 12, 0, 0, tzinfo=timezone.utc)


def _trade(days_ago: float, result_r: float | None, *, closed_at: str | None = None) -> dict:
    if closed_at is None:
        closed_at = (
            (NOW - timedelta(days=days_ago))
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
    row: dict = {"closed_at": closed_at}
    if result_r is not None:
        row["result_r"] = result_r
    return row


class TestRecentDrawdownRatio:
    def test_owner_window_is_ninety_days(self):
        # Owner decision 2026-08-15 — characterization lock.
        assert JOURNAL_DRAWDOWN_WINDOW_DAYS == 90

    def test_no_trades_is_zero(self):
        assert compute_recent_drawdown_ratio(
            [], now_utc=NOW, risk_percent=1.0
        ) == 0.0

    def test_trades_outside_window_are_ignored(self):
        trades = [_trade(100, -5.0), _trade(120, -3.0)]
        assert compute_recent_drawdown_ratio(
            trades, now_utc=NOW, risk_percent=1.0
        ) == 0.0

    def test_all_wins_is_zero(self):
        trades = [_trade(1, 2.0), _trade(2, 1.5), _trade(3, 0.5)]
        assert compute_recent_drawdown_ratio(
            trades, now_utc=NOW, risk_percent=1.0
        ) == 0.0

    def test_consecutive_losses_match_compounded_curve(self):
        # risk 1%, two -1R losses: E = 0.99 * 0.99 = 0.9801 -> dd = 0.0199.
        trades = [_trade(1, -1.0), _trade(2, -1.0)]
        result = compute_recent_drawdown_ratio(
            trades, now_utc=NOW, risk_percent=1.0
        )
        assert result == pytest.approx(0.0199)

    def test_drawdown_survives_recovery(self):
        # risk 1%: -1R (E=0.99, dd=0.01) then +2R (E=1.0098, new peak).
        trades = [_trade(1, 2.0), _trade(2, -1.0)]  # newest-first input
        result = compute_recent_drawdown_ratio(
            trades, now_utc=NOW, risk_percent=1.0
        )
        assert result == pytest.approx(0.01)

    def test_total_ruin_clamps_to_one(self):
        trades = [_trade(1, -1.0)]
        assert (
            compute_recent_drawdown_ratio(trades, now_utc=NOW, risk_percent=100.0)
            == 1.0
        )

    def test_window_days_parameter_respected(self):
        trades = [_trade(45, -2.0)]
        assert (
            compute_recent_drawdown_ratio(
                trades, now_utc=NOW, risk_percent=1.0, window_days=30
            )
            == 0.0
        )
        result = compute_recent_drawdown_ratio(
            trades, now_utc=NOW, risk_percent=1.0, window_days=60
        )
        assert result == pytest.approx(0.02)

    def test_not_a_list_fails_closed(self):
        assert compute_recent_drawdown_ratio(
            "nope", now_utc=NOW, risk_percent=1.0
        ) is None

    def test_non_dict_row_fails_closed(self):
        assert compute_recent_drawdown_ratio(
            [_trade(1, -1.0), 42], now_utc=NOW, risk_percent=1.0
        ) is None

    def test_missing_closed_at_fails_closed(self):
        assert compute_recent_drawdown_ratio(
            [{"result_r": -1.0}], now_utc=NOW, risk_percent=1.0
        ) is None

    def test_unparseable_closed_at_fails_closed(self):
        assert compute_recent_drawdown_ratio(
            [_trade(1, -1.0, closed_at="not-a-date")],
            now_utc=NOW,
            risk_percent=1.0,
        ) is None

    def test_rows_without_result_r_are_excluded_from_curve(self):
        # build_performance_summary convention: rows without R never enter the
        # R curve (MT5-history rows lacking entry/SL).
        trades = [_trade(1, -1.0), _trade(2, None)]
        result = compute_recent_drawdown_ratio(
            trades, now_utc=NOW, risk_percent=1.0
        )
        assert result == pytest.approx(0.01)

    def test_non_numeric_result_r_is_excluded(self):
        trades = [_trade(1, None), _trade(2, -1.0)]
        trades[0]["result_r"] = "oops"
        result = compute_recent_drawdown_ratio(
            trades, now_utc=NOW, risk_percent=1.0
        )
        assert result == pytest.approx(0.01)

    def test_window_with_only_unreadable_rows_is_zero(self):
        trades = [_trade(1, None), _trade(2, None)]
        assert compute_recent_drawdown_ratio(
            trades, now_utc=NOW, risk_percent=1.0
        ) == 0.0


class TestConsecutiveLosses:
    """V3 account-guard harmonization (core/account_guard.py convention)."""

    def test_counts_trailing_losses(self):
        trades = [_trade(0.2, -1.0), _trade(0.5, -0.5), _trade(1, 0.8)]
        assert _v4_consecutive_losses(trades) == 2

    def test_empty_history_is_zero(self):
        assert _v4_consecutive_losses([]) == 0

    def test_missing_result_breaks_streak_like_breakeven(self):
        trades = [_trade(0.2, -1.0), _trade(0.5, None), _trade(1, -1.0)]
        assert _v4_consecutive_losses(trades) == 1

    def test_explicit_none_result_breaks_streak(self):
        trades = [_trade(0.2, -1.0)]
        trades.append({"closed_at": _trade(0.5, 0)["closed_at"], "result_r": None})
        assert _v4_consecutive_losses(trades) == 1

    def test_non_numeric_result_breaks_streak(self):
        trades = [_trade(0.2, -1.0), _trade(0.5, None), _trade(1, -1.0)]
        trades[1]["result_r"] = "oops"
        assert _v4_consecutive_losses(trades) == 1

    def test_non_dict_rows_are_skipped(self):
        trades = [_trade(0.2, -1.0), 42, _trade(1, -1.0)]
        assert _v4_consecutive_losses(trades) == 2

    def test_result_pct_fallback(self):
        trades = [
            {"closed_at": _trade(0.2, 0)["closed_at"], "result_pct": -0.5},
            {"closed_at": _trade(0.5, 0)["closed_at"], "result_pct": 0.4},
        ]
        assert _v4_consecutive_losses(trades) == 1

    def test_not_a_list_fails_closed(self):
        assert _v4_consecutive_losses("nope") is None


class TestExposureRatio:
    def test_ratio_from_real_margin_and_balance(self):
        assert _v4_exposure_ratio(150.0, 1000.0) == pytest.approx(0.15)

    def test_zero_margin_is_zero_exposure(self):
        assert _v4_exposure_ratio(0.0, 1000.0) == 0.0

    def test_missing_margin_fails_closed(self):
        assert _v4_exposure_ratio(None, 1000.0) is None

    def test_missing_balance_fails_closed(self):
        assert _v4_exposure_ratio(150.0, None) is None

    def test_zero_balance_fails_closed(self):
        assert _v4_exposure_ratio(150.0, 0.0) is None

    def test_negative_balance_fails_closed(self):
        assert _v4_exposure_ratio(150.0, -5.0) is None

    def test_negative_margin_fails_closed(self):
        assert _v4_exposure_ratio(-1.0, 1000.0) is None

    def test_non_numeric_fails_closed(self):
        assert _v4_exposure_ratio("abc", 1000.0) is None
        assert _v4_exposure_ratio(150.0, object()) is None


class TestOpenPositions:
    def test_counts_positions_from_real_snapshot(self):
        snapshot = SimpleNamespace(available=True, positions=(1, 2, 3))
        assert _v4_open_positions(snapshot) == 3

    def test_empty_snapshot_is_zero_not_missing(self):
        snapshot = SimpleNamespace(available=True, positions=())
        assert _v4_open_positions(snapshot) == 0

    def test_unavailable_snapshot_fails_closed(self):
        snapshot = SimpleNamespace(available=False, positions=(1,))
        assert _v4_open_positions(snapshot) is None

    def test_none_snapshot_fails_closed(self):
        assert _v4_open_positions(None) is None

    def test_missing_positions_fails_closed(self):
        snapshot = SimpleNamespace(available=True, positions=None)
        assert _v4_open_positions(snapshot) is None


class _FakeNewsService:
    def data_quality_flags(self, symbol, ai_service=None, performance_tracker=None):
        return {"macro_context": {"events": []}}


class _FetchMT5:
    """Minimal MT5 surface for ``_fetch_one_symbol_mt5``."""

    def __init__(self) -> None:
        self.min_lot_calls: list[str] = []

    def resolve_symbol(self, symbol, available_symbols):
        return "EURUSDc" if symbol == "EUR/USD" else None

    def load_primary_timeframes(
        self, broker_symbol, requested_bars, performance_tracker=None
    ):
        candle = SimpleNamespace(
            time=datetime(2026, 8, 14, 21, 0, tzinfo=timezone.utc)
        )
        return {tf: [candle] for tf in ("D1", "H4", "H1", "M15")}

    def symbol_data_quality(self, symbol, broker_symbol):
        return {
            "spread_points": 12.0,
            "terminal_connected": True,
            "broker_logged_in": True,
        }

    def quote_to_usd_rate(self, quote_currency):
        return 1.0


class _MarginProbeMT5(_FetchMT5):
    def min_lot_order_margin(self, broker_symbol):
        self.min_lot_calls.append(broker_symbol)
        return 7.5


def _fetch_packet(mt5_service, scan_account):
    return scanner_module._fetch_one_symbol_mt5(
        "EUR/USD",
        mt5=mt5_service,
        available_symbols=["EURUSDc"],
        bars_by_timeframe={"D1": 300, "H4": 300, "H1": 300},
        news_service=_FakeNewsService(),
        freshness={"confidence_multiplier": 1.0},
        v4_account=scan_account,
    )


class TestFetchPacketAccountState:
    def test_packet_carries_per_symbol_account_state(self):
        from core.scanner_v4_composition import AccountState

        fake_mt5 = _MarginProbeMT5()
        scan_account = AccountState(free_margin=500.0, required_margin=None)

        packet = _fetch_packet(fake_mt5, scan_account)

        account = packet["account"]
        assert account is not scan_account
        assert account.free_margin == 500.0
        assert account.required_margin == 7.5
        # The broker margin probe runs against the RESOLVED cent symbol.
        assert fake_mt5.min_lot_calls == ["EURUSDc"]

    def test_packet_account_stays_fail_closed_without_margin_probe(self):
        from core.scanner_v4_composition import AccountState

        fake_mt5 = _FetchMT5()  # no min_lot_order_margin attribute
        scan_account = AccountState(free_margin=500.0, required_margin=None)

        packet = _fetch_packet(fake_mt5, scan_account)

        account = packet["account"]
        assert account.free_margin == 500.0
        assert account.required_margin is None  # gate -> GATE_ACCOUNT_DATA_MISSING

    def test_packet_account_none_without_scan_state(self):
        packet = _fetch_packet(_MarginProbeMT5(), None)
        assert packet["account"] is None
