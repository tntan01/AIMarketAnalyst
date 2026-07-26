"""Phase-5 calendar, statistics, provenance and deduplication tests."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from core.backtest_provenance import (
    build_backtest_provenance,
    validate_backtest_provenance,
)
from core.backtest_statistics import (
    bootstrap_trade_uncertainty,
    permutation_sequence_risk,
)
from core.system_backtest_engine import BacktestRequest
from core.walk_forward_engine import (
    add_calendar_months,
    calendar_walk_forward_windows,
    run_walk_forward,
)


UTC = timezone.utc


def test_calendar_months_do_not_use_fixed_31_day_periods() -> None:
    start = datetime(2024, 1, 15, 8, tzinfo=UTC)

    assert add_calendar_months(start, 1) == datetime(2024, 2, 15, 8, tzinfo=UTC)
    windows = calendar_walk_forward_windows(
        start,
        datetime(2024, 8, 15, 8, tzinfo=UTC),
        is_months=3,
        oos_months=2,
        step_months=1,
    )
    assert windows[0] == (
        start,
        datetime(2024, 4, 15, 8, tzinfo=UTC),
        datetime(2024, 4, 15, 8, tzinfo=UTC),
        datetime(2024, 6, 15, 8, tzinfo=UTC),
    )
    assert all(is_end == oos_start for _, is_end, oos_start, _ in windows)


def test_bootstrap_changes_invariant_metrics_but_permutation_does_not() -> None:
    values = [1.5, -1.0, 1.5, -1.0, 1.5, -1.0, 1.5, -1.0]

    bootstrap = bootstrap_trade_uncertainty(values, samples=500, seed_material="test")
    permutation = permutation_sequence_risk(values, samples=500, seed_material="test")

    assert bootstrap["method"] == "BOOTSTRAP_WITH_REPLACEMENT"
    assert bootstrap["expectancy_r"]["p95_low"] < bootstrap["expectancy_r"]["p95_high"]
    assert bootstrap["profit_factor"]["p95_low"] < bootstrap["profit_factor"]["p95_high"]
    assert permutation["method"] == "PERMUTATION_WITHOUT_REPLACEMENT"
    assert "expectancy_r" not in permutation
    assert permutation["invariant_metrics"] == [
        "expectancy_r",
        "profit_factor",
        "win_rate",
    ]


def test_bootstrap_reports_probability_and_power_evidence() -> None:
    strong = bootstrap_trade_uncertainty(
        [1.0] * 10 + [-1.0] * 2,
        samples=1000,
        seed_material="strong",
    )
    uncertain = bootstrap_trade_uncertainty(
        [1.0, -1.0] * 6,
        samples=1000,
        seed_material="uncertain",
    )

    assert strong["probability_positive_edge_pct"] >= 95.0
    assert strong["one_sided_p_value"] <= 0.05
    assert uncertain["probability_positive_edge_pct"] < 95.0
    assert uncertain["statistical_power_passed"] is False


def test_provenance_fingerprint_detects_component_tampering() -> None:
    provenance = build_backtest_provenance(
        code_revision="a" * 40,
        request={"symbol": "EUR/USD", "risk_percent": 1.0},
        data_manifest={"dataset_hash": "b" * 64},
        execution_contract={"engine": "v2"},
        scoring_contract={"metric": "setup_score"},
        frozen_strategy_config={"config_id": "frozen-1"},
    )

    assert validate_backtest_provenance(provenance) == []
    provenance["code_revision"] = "c" * 40
    assert "BACKTEST_PROVENANCE_FINGERPRINT_INVALID" in (
        validate_backtest_provenance(provenance)
    )


def test_walk_forward_deduplicates_overlapping_oos_trades(monkeypatch) -> None:
    import core.walk_forward_engine as module

    def trade(candidate_id: str, result_r: float = 1.0):
        return SimpleNamespace(
            candidate_id=candidate_id,
            symbol="EUR/USD",
            side="buy",
            entry_time="2025-06-01T00:00:00+00:00",
            exit_time="2025-06-01T01:00:00+00:00",
            result="win" if result_r > 0 else "loss",
            result_r=result_r,
            gross_r=result_r,
            cost_r=0.0,
            net_r=result_r,
            gross_pnl_account=100.0 * result_r,
            net_pnl_account=100.0 * result_r,
            spread_slippage_account=0.0,
            commission_account=0.0,
            swap_account=0.0,
            holding_bars=1,
        )

    is_ledger = []
    is_trades = []
    for index in range(8):
        result_r = 1.0 if index < 6 else -1.0
        candidate_id = f"is-{index}"
        is_trades.append(trade(candidate_id, result_r))
        is_ledger.append({
            "candidate_id": candidate_id,
            "symbol": "EUR/USD",
            "side": "buy",
            "market_regime": "range",
            "setup_score": 72,
            "expected_effective_rr": 1.6,
            "base_eligible": True,
            "research_only": False,
            "simulated_trade": {"result_r": result_r},
        })

    def fake_run(request, _candles, **_kwargs):
        if request.purpose == "RESEARCH":
            return SimpleNamespace(candidate_ledger=is_ledger, trades=is_trades)
        return SimpleNamespace(
            candidate_ledger=[],
            trades=[trade("same-oos-candidate")],
        )

    monkeypatch.setattr(module, "run_system_backtest", fake_run)
    request = BacktestRequest(
        symbol="EUR/USD",
        broker_symbol="EURUSD",
        start=datetime(2025, 1, 1, tzinfo=UTC),
        end=datetime(2025, 10, 1, tzinfo=UTC),
        initial_balance=10_000,
        risk_percent=1.0,
    )

    result = run_walk_forward(
        request,
        {},
        is_months=2,
        oos_months=2,
        step_months=1,
    )

    assert result["calendar_periods"] is True
    assert result["deduplication_applied"] is True
    assert result["unique_oos_trade_count"] == 1
    assert result["duplicate_oos_trade_count"] == result["successful_window_count"] - 1
    assert result["aggregate_oos"]["total_trades"] == 1
