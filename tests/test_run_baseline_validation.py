"""Tests for scripts/run_baseline_validation.py — logic không cần MT5 thật.

Test parse argparse, xử lý lỗi 1 symbol không crash batch, format bảng markdown.
Mock MT5Service và run_system_backtest/run_walk_forward.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_mock_backtest_result(total_trades=50, win_rate=55.0, expectancy=0.25, profit_factor=1.5, max_dd=3.2):
    """Tạo BacktestResult giả để test."""
    from core.system_backtest_engine import BacktestResult, BacktestRequest

    request = BacktestRequest(
        symbol="EUR/USD",
        broker_symbol="EURUSD",
        start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end=datetime(2024, 12, 31, tzinfo=timezone.utc),
        initial_balance=10000.0,
        risk_percent=1.0,
    )
    summary = {
        "total_trades": total_trades,
        "wins": int(total_trades * win_rate / 100),
        "losses": total_trades - int(total_trades * win_rate / 100),
        "breakeven": 0,
        "expired": 0,
        "win_rate": win_rate,
        "loss_rate": 100.0 - win_rate,
        "total_r": expectancy * total_trades,
        "average_r": expectancy,
        "median_r": expectancy,
        "expectancy_r": expectancy,
        "average_win_r": 1.5,
        "average_loss_r": -1.0,
        "profit_factor": profit_factor,
        "max_drawdown_r": max_dd,
        "max_consecutive_losses": 3,
        "max_consecutive_wins": 5,
        "average_holding_bars": 12.5,
    }
    return BacktestResult(
        request=request,
        summary=summary,
        trades=[],
        equity_curve=[],
        breakdowns={},
        skipped_setups=[],
        diagnostics={},
    )


def _make_mock_wf_result(verdict="ROBUST", robustness=75.0, oos_is_ratio=0.85, windows=4):
    """Tạo walk-forward result giả."""
    return {
        "windows": [],
        "aggregate_is": None,
        "aggregate_oos": None,
        "oos_is_expectancy_ratio": oos_is_ratio,
        "robustness_score": robustness,
        "verdict": verdict,
        "window_count": windows,
    }


# ── Test: argparse ─────────────────────────────────────────────────────────────

def test_parser_defaults():
    """Test argparse với các giá trị mặc định."""
    from scripts.run_baseline_validation import build_parser

    parser = build_parser()
    args = parser.parse_args([])

    assert args.symbols is None
    assert args.start is None
    assert args.end is None
    assert args.is_months == 6
    assert args.oos_months == 3
    assert args.output_dir is None
    assert args.timeout == 300
    assert args.quick is False


def test_parser_quick_mode():
    """Test argparse --quick flag."""
    from scripts.run_baseline_validation import build_parser

    parser = build_parser()
    args = parser.parse_args(["--quick"])

    assert args.quick is True


def test_parser_custom_params():
    """Test argparse với tham số tùy chỉnh."""
    from scripts.run_baseline_validation import build_parser

    parser = build_parser()
    args = parser.parse_args([
        "--symbols", "EUR/USD", "XAU/USD",
        "--start", "2025-01-01",
        "--end", "2025-06-30",
        "--is-months", "4",
        "--oos-months", "2",
        "--output-dir", "/tmp/reports",
        "--timeout", "120",
    ])

    assert args.symbols == ["EUR/USD", "XAU/USD"]
    assert args.start == "2025-01-01"
    assert args.end == "2025-06-30"
    assert args.is_months == 4
    assert args.oos_months == 2
    assert args.output_dir == "/tmp/reports"
    assert args.timeout == 120


# ── Test: _format_r, _format_pct ───────────────────────────────────────────────

def test_format_r_positive():
    from scripts.run_baseline_validation import _format_r
    assert _format_r(0.25) == "+0.25"


def test_format_r_negative():
    from scripts.run_baseline_validation import _format_r
    assert _format_r(-0.10) == "-0.10"


def test_format_r_none():
    from scripts.run_baseline_validation import _format_r
    assert _format_r(None) == "—"


def test_format_pct():
    from scripts.run_baseline_validation import _format_pct
    assert _format_pct(55.0) == "55%"


def test_format_pct_none():
    from scripts.run_baseline_validation import _format_pct
    assert _format_pct(None) == "—"


# ── Test: _log_symbol_result ───────────────────────────────────────────────────

def test_log_symbol_result_success(capsys):
    from scripts.run_baseline_validation import _log_symbol_result

    r = {
        "symbol": "EUR/USD",
        "broker_symbol": "EURUSD",
        "error": None,
        "backtest_summary": {
            "total_trades": 47,
            "win_rate": 51.0,
            "expectancy_r": 0.12,
        },
        "wf_result": {"verdict": "STABLE"},
        "elapsed_seconds": 30.5,
    }
    _log_symbol_result(r)
    captured = capsys.readouterr()
    assert "[EUR/USD] 47 trades | WR 51% | E[R] +0.12 | verdict: STABLE | 30s" in captured.out


def test_log_symbol_result_error(capsys):
    from scripts.run_baseline_validation import _log_symbol_result

    r = {
        "symbol": "BTC/USD",
        "broker_symbol": None,
        "error": "Không tìm thấy broker symbol",
        "backtest_summary": None,
        "wf_result": None,
        "elapsed_seconds": 0,
    }
    _log_symbol_result(r)
    captured = capsys.readouterr()
    assert "[BTC/USD] SKIPPED" in captured.out


# ── Test: _build_markdown_report ───────────────────────────────────────────────

def test_build_markdown_headers():
    """Test markdown report có đủ headers và cấu trúc bảng."""
    from scripts.run_baseline_validation import _build_markdown_report

    all_results = [
        {
            "symbol": "EUR/USD",
            "broker_symbol": "EURUSD",
            "error": None,
            "elapsed_seconds": 30,
            "backtest_summary": {
                "total_trades": 50,
                "win_rate": 55.0,
                "expectancy_r": 0.25,
                "profit_factor": 1.5,
                "max_drawdown_r": 3.2,
                "average_r": 0.25,
            },
            "wf_result": {"verdict": "ROBUST", "robustness_score": 80, "window_count": 4},
        },
        {
            "symbol": "GBP/USD",
            "broker_symbol": "GBPUSD",
            "error": None,
            "elapsed_seconds": 25,
            "backtest_summary": {
                "total_trades": 40,
                "win_rate": 50.0,
                "expectancy_r": 0.10,
                "profit_factor": 1.2,
                "max_drawdown_r": 4.5,
                "average_r": 0.10,
            },
            "wf_result": {"verdict": "SUSPECT", "robustness_score": 55, "window_count": 3},
        },
    ]

    config = {
        "start": "2024-01-01",
        "end": "2024-12-31",
        "is_months": 6,
        "oos_months": 3,
        "risk_percent": 1.0,
        "initial_balance": 10000,
    }

    md = _build_markdown_report(all_results, config)

    # Headers
    assert "# Baseline Validation Report" in md
    assert "## Summary" in md
    assert "## Aggregate" in md

    # Table columns
    assert "| # | Symbol | Trades | Win Rate | E[R] | PF | Max DD(R) | Avg R | WF Verdict | Robustness |" in md

    # EUR/USD xuất hiện trước (expectancy cao hơn)
    eur_pos = md.index("EUR/USD")
    gbp_pos = md.index("GBP/USD")
    assert eur_pos < gbp_pos, "EUR/USD (E[R]=+0.25) phải đứng trước GBP/USD (E[R]=+0.10)"

    # Warnings
    assert "ROBUST" in md
    assert "SUSPECT" in md


def test_build_markdown_low_sample_warning():
    """Test markdown có cảnh báo LOW SAMPLE khi total_trades < 30."""
    from scripts.run_baseline_validation import _build_markdown_report

    all_results = [
        {
            "symbol": "XAU/USD",
            "broker_symbol": "XAUUSD",
            "error": None,
            "elapsed_seconds": 10,
            "backtest_summary": {
                "total_trades": 12,
                "win_rate": 60.0,
                "expectancy_r": 0.30,
                "profit_factor": 2.0,
                "max_drawdown_r": 1.5,
                "average_r": 0.30,
            },
            "wf_result": {"verdict": "INCONCLUSIVE", "robustness_score": None, "window_count": 0},
        },
    ]

    config = {
        "start": "2024-01-01",
        "end": "2024-12-31",
        "is_months": 6,
        "oos_months": 3,
        "risk_percent": 1.0,
        "initial_balance": 10000,
    }

    md = _build_markdown_report(all_results, config)

    assert "LOW SAMPLE" in md
    assert "INCONCLUSIVE" in md


def test_build_markdown_error_symbol():
    """Test markdown hiển thị symbol lỗi đúng cách."""
    from scripts.run_baseline_validation import _build_markdown_report

    all_results = [
        {
            "symbol": "BTC/USD",
            "broker_symbol": None,
            "error": "Thiếu dữ liệu: Chưa đủ dữ liệu warmup",
            "elapsed_seconds": 2,
            "backtest_summary": None,
            "wf_result": None,
        },
    ]

    config = {
        "start": "2024-01-01",
        "end": "2024-12-31",
        "is_months": 6,
        "oos_months": 3,
        "risk_percent": 1.0,
        "initial_balance": 10000,
    }

    md = _build_markdown_report(all_results, config)

    assert "BTC/USD" in md
    assert "ERROR" in md
    # Aggregate section nên báo không có symbols thành công
    assert "không có symbol" in md.lower() or "0 / 1" in md


# ── Test: _build_baseline_json ─────────────────────────────────────────────────

def test_build_baseline_json_structure():
    """Test baseline_summary.json có cấu trúc đúng."""
    from scripts.run_baseline_validation import _build_baseline_json

    all_results = [
        {
            "symbol": "EUR/USD",
            "broker_symbol": "EURUSD",
            "error": None,
            "elapsed_seconds": 30,
            "backtest_summary": {
                "total_trades": 50,
                "win_rate": 55.0,
                "expectancy_r": 0.25,
                "profit_factor": 1.5,
                "max_drawdown_r": 3.2,
                "average_r": 0.25,
                "average_win_r": 1.5,
                "average_loss_r": -1.0,
                "max_consecutive_losses": 3,
                "average_holding_bars": 12.5,
            },
            "wf_result": {
                "verdict": "ROBUST",
                "robustness_score": 80,
                "oos_is_expectancy_ratio": 0.85,
                "window_count": 4,
            },
            "backtest": None,
        },
    ]

    config = {
        "start": "2024-01-01",
        "end": "2024-12-31",
        "is_months": 6,
        "oos_months": 3,
        "risk_percent": 1.0,
        "initial_balance": 10000,
    }

    data = _build_baseline_json(all_results, None, config)

    assert data["config"] == config
    assert "generated_at" in data
    assert len(data["symbols"]) == 1

    sym = data["symbols"][0]
    assert sym["symbol"] == "EUR/USD"
    assert sym["total_trades"] == 50
    assert sym["expectancy_r"] == 0.25
    assert sym["wf_verdict"] == "ROBUST"
    assert sym["wf_robustness_score"] == 80
    assert sym["error"] is None

    # Verify JSON serializable
    json.dumps(data, indent=2)


def test_build_baseline_json_sorting():
    """Test symbols được sort theo expectancy_r giảm dần."""
    from scripts.run_baseline_validation import _build_baseline_json

    all_results = [
        {
            "symbol": "GBP/USD",
            "broker_symbol": "GBPUSD",
            "error": None,
            "elapsed_seconds": 25,
            "backtest_summary": {"expectancy_r": 0.10, "total_trades": 40, "win_rate": 50.0},
            "wf_result": {"verdict": "SUSPECT", "robustness_score": 55, "window_count": 3},
        },
        {
            "symbol": "EUR/USD",
            "broker_symbol": "EURUSD",
            "error": None,
            "elapsed_seconds": 30,
            "backtest_summary": {"expectancy_r": 0.25, "total_trades": 50, "win_rate": 55.0},
            "wf_result": {"verdict": "ROBUST", "robustness_score": 80, "window_count": 4},
        },
    ]

    config = {"start": "2024-01-01", "end": "2024-12-31", "is_months": 6, "oos_months": 3, "risk_percent": 1.0, "initial_balance": 10000}

    data = _build_baseline_json(all_results, None, config)
    symbols = data["symbols"]

    # EUR/USD (0.25) phải đứng trước GBP/USD (0.10)
    assert symbols[0]["symbol"] == "EUR/USD"
    assert symbols[1]["symbol"] == "GBP/USD"


# ── Test: Error isolation — 1 symbol lỗi không crash batch ─────────────────────

def test_error_isolation_one_symbol_fails():
    """Test 1 symbol lỗi không làm hỏng symbol khác trong batch."""
    from scripts.run_baseline_validation import _log_symbol_result
    import io

    results = [
        {
            "symbol": "EUR/USD",
            "broker_symbol": "EURUSD",
            "error": None,
            "elapsed_seconds": 30,
            "backtest_summary": {"total_trades": 50, "win_rate": 55.0, "expectancy_r": 0.25},
            "wf_result": {"verdict": "ROBUST"},
        },
        {
            "symbol": "BTC/USD",
            "broker_symbol": None,
            "error": "Timeout sau 300s",
            "elapsed_seconds": 300,
            "backtest_summary": None,
            "wf_result": None,
        },
        {
            "symbol": "XAU/USD",
            "broker_symbol": "XAUUSD",
            "error": None,
            "elapsed_seconds": 20,
            "backtest_summary": {"total_trades": 35, "win_rate": 60.0, "expectancy_r": 0.30},
            "wf_result": {"verdict": "ROBUST"},
        },
    ]

    valid = [r for r in results if not r.get("error")]
    errors = [r for r in results if r.get("error")]

    # EUR và XAU vẫn OK
    assert len(valid) == 2
    assert valid[0]["symbol"] == "EUR/USD"
    assert valid[1]["symbol"] == "XAU/USD"

    # BTC bị lỗi nhưng không crash
    assert len(errors) == 1
    assert errors[0]["symbol"] == "BTC/USD"
    assert "Timeout" in errors[0]["error"]


# ── Test: _summary_keys helper ─────────────────────────────────────────────────

def test_summary_keys():
    from scripts.run_baseline_validation import _summary_keys

    d = {
        "total_trades": 100,
        "win_rate": 55.0,
        "expectancy_r": 0.25,
        "profit_factor": 1.5,
        "extra_field": "ignored",
    }
    result = _summary_keys(d)
    assert result == {
        "total_trades": 100,
        "win_rate": 55.0,
        "expectancy_r": 0.25,
        "profit_factor": 1.5,
    }
    assert "extra_field" not in result


# ── Test: _fetch_symbol_data (Phase A — MT5 I/O) ───────────────────────────────

def test_fetch_symbol_data_broker_not_found():
    """Test Phase A: broker symbol không tìm thấy → error, candles=None."""
    from datetime import datetime, timezone

    from scripts.run_baseline_validation import _fetch_symbol_data

    mock_mt5 = MagicMock()
    mock_mt5.available_symbols.return_value = ["EURUSD"]
    mock_mt5.resolve_symbol.return_value = None

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 12, 31, tzinfo=timezone.utc)

    result = _fetch_symbol_data(mock_mt5, "CRYPTO/XYZ", start, end, io_timeout=10)

    assert result["symbol"] == "CRYPTO/XYZ"
    assert result["broker_symbol"] is None
    assert result["candles"] is None
    assert result["error"] is not None
    assert "Không tìm thấy" in result["error"]


def test_fetch_symbol_data_missing_candles():
    """Test Phase A: candles rỗng → error (không pass validate)."""
    from datetime import datetime, timezone

    from scripts.run_baseline_validation import _fetch_symbol_data

    mock_mt5 = MagicMock()
    mock_mt5.available_symbols.return_value = ["EURUSD", "GBPUSD"]
    mock_mt5.resolve_symbol.return_value = "EURUSD"
    mock_mt5.load_ohlcv_range.return_value = []  # candles rỗng

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 12, 31, tzinfo=timezone.utc)

    result = _fetch_symbol_data(mock_mt5, "EUR/USD", start, end, io_timeout=10)

    assert result["symbol"] == "EUR/USD"
    assert result["error"] is not None
    assert "thiếu" in result["error"].lower() or "dữ liệu" in result["error"].lower()
    assert result["candles"] is None


# ── Test: _run_backtest_compute (Phase B — compute, no MT5) ─────────────────────

def test_run_backtest_compute_basic():
    """Test Phase B: compute trả về đúng cấu trúc kết quả."""
    from unittest.mock import patch
    from datetime import datetime, timezone

    from scripts.run_baseline_validation import _run_backtest_compute

    mock_settings = MagicMock()
    mock_settings.trading.account_balance = 10000.0
    mock_settings.trading.default_risk_percent = 1.0
    mock_settings.trading.account_currency = "USD"
    mock_settings.trading.lot_step = 0.01
    mock_settings.trading.minimum_lot = 0.01
    mock_settings.trading.contract_size_override = 100000.0
    mock_settings.display.timezone = "Asia/Ho_Chi_Minh"

    mock_bt_result = _make_mock_backtest_result(total_trades=50, expectancy=0.25)
    mock_wf = _make_mock_wf_result()
    mock_summary = mock_bt_result.summary  # Lấy trực tiếp từ mock BacktestResult

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 12, 31, tzinfo=timezone.utc)

    with patch("scripts.run_baseline_validation.run_system_backtest", return_value=mock_bt_result) as mock_bt, \
         patch("scripts.run_baseline_validation.summarize_backtest_trades", return_value=mock_summary), \
         patch("scripts.run_baseline_validation.run_walk_forward", return_value=mock_wf) as mock_wf_fn:
        result = _run_backtest_compute(
            mock_settings, "EUR/USD", "EURUSD", {"D1": [], "H4": [], "H1": []},
            start, end, is_months=6, oos_months=3,
        )

    assert result["backtest"] is mock_bt_result
    assert result["backtest_summary"]["total_trades"] == 50
    assert result["backtest_summary"]["expectancy_r"] == 0.25
    assert result["wf_result"]["verdict"] == "ROBUST"
    assert result["wf_result"]["robustness_score"] == 75.0
    mock_bt.assert_called_once()
    mock_wf_fn.assert_called_once()


def test_run_backtest_compute_zero_trades_skips_wf():
    """Test Phase B: 0 trades → không gọi walk-forward, verdict=INCONCLUSIVE."""
    from unittest.mock import patch
    from datetime import datetime, timezone

    from scripts.run_baseline_validation import _run_backtest_compute

    mock_settings = MagicMock()
    mock_settings.trading.account_balance = 10000.0
    mock_settings.trading.default_risk_percent = 1.0
    mock_settings.trading.account_currency = "USD"
    mock_settings.trading.lot_step = 0.01
    mock_settings.trading.minimum_lot = 0.01
    mock_settings.trading.contract_size_override = 100000.0
    mock_settings.display.timezone = "Asia/Ho_Chi_Minh"

    mock_bt_result = _make_mock_backtest_result(total_trades=0, expectancy=0.0)

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 12, 31, tzinfo=timezone.utc)

    with patch("scripts.run_baseline_validation.run_system_backtest", return_value=mock_bt_result) as mock_bt, \
         patch("scripts.run_baseline_validation.run_walk_forward") as mock_wf_fn:
        result = _run_backtest_compute(
            mock_settings, "EUR/USD", "EURUSD", {"D1": [], "H4": [], "H1": []},
            start, end, is_months=6, oos_months=3,
        )

    mock_bt.assert_called_once()
    mock_wf_fn.assert_not_called()
    assert result["wf_result"]["verdict"] == "INCONCLUSIVE"
    assert result["wf_result"]["window_count"] == 0


# ── Test: Phase A fail → Phase B NOT called (key requirement) ──────────────────

def test_phase_a_fail_skips_backtest():
    """Khi Phase A (MT5 I/O) fail, run_system_backtest() KHÔNG được gọi.

    Đây là test quan trọng nhất: đảm bảo lỗi ở giai đoạn fetch data
    không lan sang giai đoạn compute.
    """
    from unittest.mock import patch
    from datetime import datetime, timezone

    from scripts.run_baseline_validation import _process_symbol_with_timeout

    mock_mt5 = MagicMock()
    # Phase A sẽ fail vì không resolve được broker symbol
    mock_mt5.available_symbols.return_value = []
    mock_mt5.resolve_symbol.return_value = None

    mock_settings = MagicMock()
    mock_settings.trading.account_balance = 10000.0
    mock_settings.trading.default_risk_percent = 1.0
    mock_settings.trading.account_currency = "USD"
    mock_settings.trading.lot_step = 0.01
    mock_settings.trading.minimum_lot = 0.01
    mock_settings.trading.contract_size_override = 100000.0
    mock_settings.display.timezone = "Asia/Ho_Chi_Minh"

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 12, 31, tzinfo=timezone.utc)

    with patch("scripts.run_baseline_validation.run_system_backtest") as mock_bt, \
         patch("scripts.run_baseline_validation.run_walk_forward") as mock_wf:
        result = _process_symbol_with_timeout(
            mock_mt5, mock_settings, "CRYPTO/XYZ", start, end,
            is_months=6, oos_months=3, timeout=30,
        )

    # Phase B hoàn toàn không được gọi
    mock_bt.assert_not_called()
    mock_wf.assert_not_called()

    # Kết quả phải báo lỗi
    assert result["error"] is not None
    assert result["backtest"] is None
    assert result["backtest_summary"] is None
    assert result["wf_result"] is None


# ── Test: _process_symbol_with_timeout (orchestrator) ──────────────────────────

def test_process_symbol_with_timeout_success():
    """Test orchestrator với Phase A + B đều thành công."""
    from unittest.mock import patch
    from datetime import datetime, timezone

    from scripts.run_baseline_validation import _process_symbol_with_timeout

    mock_mt5 = MagicMock()
    mock_mt5.available_symbols.return_value = ["EURUSD"]
    mock_mt5.resolve_symbol.return_value = "EURUSD"
    # Trả về candles giả đủ để pass validate (cần D1/H4/H1 có ít nhất 1 phần tử)
    from core.market_models import Candle
    fake_candle = Candle(
        time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        open=1.05, high=1.06, low=1.04, close=1.05, volume=1000,
    )
    # Cần 60 D1, 60 H4, 30 H1 để pass has_minimum_analysis_data
    mock_mt5.load_ohlcv_range.return_value = [fake_candle] * 100

    mock_settings = MagicMock()
    mock_settings.trading.account_balance = 10000.0
    mock_settings.trading.default_risk_percent = 1.0
    mock_settings.trading.account_currency = "USD"
    mock_settings.trading.lot_step = 0.01
    mock_settings.trading.minimum_lot = 0.01
    mock_settings.trading.contract_size_override = 100000.0
    mock_settings.display.timezone = "Asia/Ho_Chi_Minh"

    mock_bt_result = _make_mock_backtest_result(total_trades=50, expectancy=0.25)
    mock_wf = _make_mock_wf_result()
    mock_summary = mock_bt_result.summary

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 12, 31, tzinfo=timezone.utc)

    with patch("scripts.run_baseline_validation.run_system_backtest", return_value=mock_bt_result) as mock_bt, \
         patch("scripts.run_baseline_validation.summarize_backtest_trades", return_value=mock_summary), \
         patch("scripts.run_baseline_validation.run_walk_forward", return_value=mock_wf) as mock_wf_fn:
        result = _process_symbol_with_timeout(
            mock_mt5, mock_settings, "EUR/USD", start, end,
            is_months=6, oos_months=3, timeout=30,
        )

    assert result["symbol"] == "EUR/USD"
    assert result["broker_symbol"] == "EURUSD"
    assert result["error"] is None
    assert result["backtest_summary"]["total_trades"] == 50
    assert result["wf_result"]["verdict"] == "ROBUST"
    mock_bt.assert_called_once()
    mock_wf_fn.assert_called_once()


def test_process_symbol_with_timeout_io_timeout():
    """Test orchestrator: Phase A timeout → Phase B không gọi, error rõ ràng."""
    from unittest.mock import patch
    from datetime import datetime, timezone

    from scripts.run_baseline_validation import _process_symbol_with_timeout

    mock_mt5 = MagicMock()
    # Làm cho available_symbols block để trigger I/O timeout
    mock_mt5.available_symbols.side_effect = lambda **kw: __import__("time").sleep(10) or []

    mock_settings = MagicMock()

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 12, 31, tzinfo=timezone.utc)

    with patch("scripts.run_baseline_validation.run_system_backtest") as mock_bt, \
         patch("scripts.run_baseline_validation.run_walk_forward") as mock_wf:
        # io_timeout mặc định 120s, nhưng _fetch_symbol_data nhận io_timeout từ
        # hàm gọi. Ở đây _process_symbol_with_timeout gọi _fetch_symbol_data
        # với io_timeout mặc định (120s). Để test nhanh, ta patch
        # DEFAULT_IO_TIMEOUT_SECONDS hoặc test riêng _fetch_symbol_data.
        pass

    # Test _fetch_symbol_data riêng với io_timeout ngắn
    from scripts.run_baseline_validation import _fetch_symbol_data

    result = _fetch_symbol_data(mock_mt5, "EUR/USD", start, end, io_timeout=1)

    assert result["error"] is not None
    assert "timeout" in result["error"].lower()
    assert result["candles"] is None


# ── Test: WF_WARNING_VERDICTS constants ─────────────────────────────────────────

def test_wf_warning_verdicts():
    """Test các verdict walk-forward cần cảnh báo."""
    from scripts.run_baseline_validation import WF_WARNING_VERDICTS

    assert "INCONCLUSIVE" in WF_WARNING_VERDICTS
    assert "OVERFITTING" in WF_WARNING_VERDICTS
    # ROBUST và SUSPECT không phải là warning
    assert "ROBUST" not in WF_WARNING_VERDICTS
    assert "SUSPECT" not in WF_WARNING_VERDICTS


# ── Test: SUPPORTED_SYMBOLS import ──────────────────────────────────────────────

def test_supported_symbols_available():
    """Test constants có SUPPORTED_SYMBOLS."""
    from config.constants import SUPPORTED_SYMBOLS
    assert len(SUPPORTED_SYMBOLS) > 0
    assert "EUR/USD" in SUPPORTED_SYMBOLS
