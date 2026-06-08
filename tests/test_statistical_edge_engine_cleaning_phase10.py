"""Phase 10.3: verify data-cleaning helpers for result_r extraction."""

from __future__ import annotations

from math import nan

from core.statistical_edge_engine import coerce_result_r, extract_closed_trade_results


class TestCoerceResultR:

    def test_int_returns_float(self):
        assert coerce_result_r(1) == 1.0

    def test_float_returns_float(self):
        assert coerce_result_r(1.5) == 1.5
        assert coerce_result_r(-0.8) == -0.8
        assert coerce_result_r(0.0) == 0.0

    def test_none_returns_none(self):
        assert coerce_result_r(None) is None

    def test_valid_string_returns_float(self):
        assert coerce_result_r("1.2") == 1.2
        assert coerce_result_r("-0.8") == -0.8
        assert coerce_result_r(" 0.5 ") == 0.5

    def test_empty_string_returns_none(self):
        assert coerce_result_r("") is None

    def test_na_strings_return_none(self):
        for val in ("N/A", "nan", "NaN", "None", "null", "NA"):
            assert coerce_result_r(val) is None, f"{val!r} should be None"

    def test_garbage_string_returns_none(self):
        assert coerce_result_r("abc") is None

    def test_nan_float_returns_none(self):
        assert coerce_result_r(float("nan")) is None

    def test_inf_returns_none(self):
        assert coerce_result_r(float("inf")) is None
        assert coerce_result_r(float("-inf")) is None

    def test_non_numeric_object_returns_none(self):
        assert coerce_result_r([]) is None
        assert coerce_result_r({}) is None
        assert coerce_result_r(object()) is None


class TestExtractClosedTradeResults:

    def test_none_returns_empty(self):
        assert extract_closed_trade_results(None) == []

    def test_empty_list_returns_empty(self):
        assert extract_closed_trade_results([]) == []

    def test_realistic_mixed_trades(self):
        trades = [
            {"symbol": "EURUSD", "direction": "buy", "result_r": 1.5, "closed_at": "2026-06-01T10:00:00"},
            {"symbol": "EURUSD", "direction": "buy", "result_r": "-1.0", "closed_at": "2026-06-01T11:00:00"},
            {"symbol": "EURUSD", "direction": "sell", "result_r": 0, "closed_at": "2026-06-01T12:00:00"},
        ]
        assert extract_closed_trade_results(trades) == [1.5, -1.0, 0.0]

    def test_skips_open_trade(self):
        trades = [
            {"symbol": "EURUSD", "result_r": 1.5, "closed_at": "2026-06-01T10:00:00"},
            {"symbol": "EURUSD", "status": "open", "result_r": None},
        ]
        assert extract_closed_trade_results(trades) == [1.5]

    def test_skips_pending_trade(self):
        trades = [
            {"symbol": "EURUSD", "status": "pending", "result_r": 0.5},
            {"symbol": "EURUSD", "result_r": -0.3, "closed_at": "2026-06-01T10:00:00"},
        ]
        assert extract_closed_trade_results(trades) == [-0.3]

    def test_skips_missing_closed_at_when_no_status(self):
        trades = [
            {"symbol": "EURUSD", "result_r": 1.0, "closed_at": "2026-06-01T10:00:00"},
            {"symbol": "EURUSD", "result_r": 2.0},  # no closed_at, no status
        ]
        assert extract_closed_trade_results(trades) == [1.0]

    def test_keeps_closed_status_without_closed_at(self):
        """Trade with status='closed' but no closed_at is still kept."""
        trades = [
            {"symbol": "EURUSD", "status": "closed", "result_r": 1.2},
        ]
        assert extract_closed_trade_results(trades) == [1.2]

    def test_skips_garbage_result_r(self):
        trades = [
            {"symbol": "EURUSD", "result_r": "abc", "closed_at": "2026-06-01T10:00:00"},
            {"symbol": "EURUSD", "result_r": 1.5, "closed_at": "2026-06-01T11:00:00"},
        ]
        assert extract_closed_trade_results(trades) == [1.5]

    def test_skips_nan_result_r(self):
        trades = [
            {"symbol": "EURUSD", "result_r": float("nan"), "closed_at": "2026-06-01T10:00:00"},
            {"symbol": "EURUSD", "result_r": -1.0, "closed_at": "2026-06-01T11:00:00"},
        ]
        assert extract_closed_trade_results(trades) == [-1.0]

    def test_skips_non_dict_items(self):
        trades: list = [
            {"symbol": "EURUSD", "result_r": 1.0, "closed_at": "2026-06-01T10:00:00"},
            None,  # type: ignore
            "not_a_dict",  # type: ignore
        ]
        assert extract_closed_trade_results(trades) == [1.0]  # type: ignore[arg-type]

    def test_string_result_r_valid(self):
        trades = [
            {"symbol": "EURUSD", "result_r": "1.5", "closed_at": "2026-06-01T10:00:00"},
            {"symbol": "EURUSD", "result_r": "-0.8", "closed_at": "2026-06-01T11:00:00"},
        ]
        assert extract_closed_trade_results(trades) == [1.5, -0.8]
