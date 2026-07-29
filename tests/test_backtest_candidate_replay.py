"""Phase-4 candidate-ledger and frozen OOS replay tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from core.backtest_candidate_ledger import (
    CANDIDATE_LEDGER_VERSION,
    CANDIDATE_REPLAY_VERSION,
    FROZEN_STRATEGY_VERSION,
    CandidateLedgerEntry,
    FrozenStrategyConfig,
    candidate_ledger_fingerprint,
    evaluate_frozen_strategy,
    optimize_frozen_strategy,
    release_candidate_rejection_reasons,
    release_optimizer_candidate_rows,
    release_optimizer_diagnostics,
    side_setup_score,
)
from core.backtest_contract import (
    BACKTEST_PURPOSE_RESEARCH,
    BACKTEST_PURPOSE_VALIDATION,
)
from core.system_backtest_engine import (
    BacktestRequest,
    trade_open_block_reason,
    validate_backtest_input,
)
from core.market_models import Candle


UTC = timezone.utc


def _request() -> BacktestRequest:
    return BacktestRequest(
        symbol="EUR/USD",
        broker_symbol="EURUSD",
        start=datetime(2025, 1, 1, tzinfo=UTC),
        end=datetime(2025, 4, 11, tzinfo=UTC),
        initial_balance=10_000,
        risk_percent=1.0,
    )


def _ledger_rows(*, side: str = "buy") -> list[dict]:
    rows: list[dict] = []
    for index in range(8):
        rows.append({
            "candidate_id": f"candidate-{index}",
            "symbol": "EUR/USD",
            "decision_time": (
                datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=index)
            ).isoformat(),
            "side": side,
            "setup_score": 72,
            "setup_score_source": f"side_scores.{side}.setup_score",
            "signal_score": 78,
            "market_regime": "range",
            "expected_effective_rr": 1.6,
            "scenario_available": True,
            "base_eligible": True,
            "base_rejection_reason": None,
            "entry_zone_source": "smc_v2_selected",
            "m15_quality": "strict",
            "entry_status": "confirmed_entry",
            "decision": "READY_TO_TRADE",
            "tp1_source": "target_zone",
            "scenario_source": "pipeline",
            "research_only": False,
            "frozen_config_id": "",
            "strategy_eligible": True,
            "strategy_rejection_reasons": [],
            "simulated_trade": {
                "result_r": 1.0 if index < 6 else -1.0,
            },
            "executed": True,
            "version": CANDIDATE_LEDGER_VERSION,
        })
    return rows


def test_setup_score_never_aliases_final_score() -> None:
    score, source = side_setup_score(
        {
            "final_score": 99,
            "scenario_scores": {"buy": {"signal_score": 88}},
        },
        "buy",
    )

    assert score is None
    assert source == "missing_buy_setup_score"


def test_setup_score_is_explicitly_owned_by_selected_side() -> None:
    score, source = side_setup_score(
        {
            "side_scores": {
                "buy": {"setup_score": 73},
                "sell": {"setup_score": 61},
            }
        },
        "sell",
    )

    assert score == 61
    assert source == "side_scores.sell.setup_score"


def test_optimizer_is_deterministic_for_same_is_ledger() -> None:
    rows = _ledger_rows()

    first = optimize_frozen_strategy(rows, symbol="EUR/USD")
    second = optimize_frozen_strategy(list(rows), symbol="EUR/USD")

    assert first is not None
    assert second == first
    assert first.version == FROZEN_STRATEGY_VERSION
    assert first.score_metric == "setup_score"


def test_optimizer_output_does_not_depend_on_unseen_oos_rows() -> None:
    in_sample = _ledger_rows()
    hostile_oos = _ledger_rows(side="sell")

    before_oos = optimize_frozen_strategy(in_sample, symbol="EUR/USD")
    after_oos_arrives = optimize_frozen_strategy(in_sample, symbol="EUR/USD")

    assert hostile_oos
    assert before_oos == after_oos_arrives
    assert before_oos is not None and before_oos.side == "buy"


def test_frozen_strategy_explains_every_rejection() -> None:
    config = FrozenStrategyConfig(
        config_id="EURUSD-frozen-test",
        symbol="EUR/USD",
        side="buy",
        allowed_regimes=("range",),
        min_setup_score=70,
        min_expected_rr=1.5,
    )
    entry = CandidateLedgerEntry(
        candidate_id="candidate-rejected",
        symbol="EUR/USD",
        decision_time="2025-03-01T00:00:00+00:00",
        side="sell",
        setup_score=60,
        setup_score_source="side_scores.sell.setup_score",
        signal_score=65,
        market_regime="trend_down",
        expected_effective_rr=1.2,
        scenario_available=True,
        base_eligible=True,
        base_rejection_reason=None,
        entry_zone_source="smc_v2_selected",
        m15_quality="strict",
        entry_status="confirmed_entry",
        decision="READY_TO_TRADE",
        tp1_source="target_zone",
        simulated_trade={"result_r": 1.0},
    )

    accepted, reasons = evaluate_frozen_strategy(entry, config)

    assert accepted is False
    assert reasons == [
        "FROZEN_SIDE_MISMATCH",
        "FROZEN_REGIME_MISMATCH",
        "FROZEN_SETUP_SCORE_BELOW_MIN",
        "FROZEN_EXPECTED_RR_BELOW_MIN",
    ]


def test_release_candidate_rejects_dirty_sources_and_unfilled_watch_states() -> None:
    clean = _ledger_rows()[0]

    assert release_candidate_rejection_reasons(clean) == []

    fallback = dict(clean, entry_zone_source="fallback")
    distant = dict(clean, entry_zone_source="smc_distant")
    loose_m15 = dict(clean, m15_quality="loose")
    missing_m15 = dict(clean, m15_quality=None)
    watch = dict(clean, entry_status="watch_zone", simulated_trade=None)
    no_tp1 = dict(clean, tp1_source="none")
    not_ready = dict(clean, decision="WATCH_ONLY", simulated_trade=None)

    assert "RELEASE_ENTRY_ZONE_SOURCE_NOT_CLEAN" in (
        release_candidate_rejection_reasons(fallback)
    )
    assert "RELEASE_ENTRY_ZONE_SOURCE_NOT_CLEAN" in (
        release_candidate_rejection_reasons(distant)
    )
    assert "RELEASE_M15_QUALITY_NOT_STRICT" in (
        release_candidate_rejection_reasons(loose_m15)
    )
    assert "RELEASE_M15_QUALITY_NOT_STRICT" in (
        release_candidate_rejection_reasons(missing_m15)
    )
    assert "RELEASE_ENTRY_STATUS_NOT_CONFIRMED" in (
        release_candidate_rejection_reasons(watch)
    )
    assert "RELEASE_TP1_MISSING" in release_candidate_rejection_reasons(no_tp1)
    assert "RELEASE_DECISION_NOT_READY" in (
        release_candidate_rejection_reasons(not_ready)
    )


def test_release_candidate_accepts_simulated_fill_pending_scan_state() -> None:
    row = dict(
        _ledger_rows()[0],
        base_eligible=False,
        base_rejection_reason="blocked_by_trade_gate",
        entry_status="watch_zone",
        decision="WATCH_ONLY",
        m15_quality="strict",
    )

    assert release_candidate_rejection_reasons(row) == []


def test_release_candidate_rejects_simulated_fill_without_strict_m15() -> None:
    row = dict(
        _ledger_rows()[0],
        base_eligible=False,
        base_rejection_reason="blocked_by_trade_gate",
        entry_status="watch_zone",
        decision="WATCH_ONLY",
        m15_quality="loose",
    )

    assert release_candidate_rejection_reasons(row) == [
        "RELEASE_M15_QUALITY_NOT_STRICT"
    ]


def test_optimizer_ignores_fallback_distant_unfilled_watch_and_no_tp1_rows() -> None:
    dirty_rows = []
    for index, source in enumerate(["fallback", "smc_distant"] * 4):
        row = dict(_ledger_rows()[index], entry_zone_source=source)
        dirty_rows.append(row)
    dirty_rows.extend(
        dict(row, entry_status="watch_zone", simulated_trade=None)
        for row in _ledger_rows(side="sell")
    )
    dirty_rows.extend(
        dict(row, m15_quality="loose")
        for row in _ledger_rows(side="sell")
    )
    dirty_rows.extend(
        dict(row, tp1_source="none")
        for row in _ledger_rows(side="sell")
    )

    assert optimize_frozen_strategy(dirty_rows, symbol="EUR/USD") is None


def test_optimizer_and_diagnostics_share_release_selector() -> None:
    clean_rows = _ledger_rows()
    dirty_rows = [
        dict(
            _ledger_rows(side="sell")[0],
            candidate_id="dirty-loose",
            m15_quality="loose",
        ),
        dict(
            _ledger_rows(side="sell")[1],
            candidate_id="dirty-unfilled",
            simulated_trade=None,
        ),
    ]
    rows = clean_rows + dirty_rows

    selected = release_optimizer_candidate_rows(rows, symbol="EUR/USD")
    diagnostics = release_optimizer_diagnostics(rows, symbol="EUR/USD")

    expected_ids = [row["candidate_id"] for row in clean_rows]
    assert [row["candidate_id"] for row in selected] == expected_ids
    assert diagnostics["release_candidate_ids"] == expected_ids
    assert diagnostics["release_candidate_count"] == len(clean_rows)
    assert diagnostics["passing_threshold_bucket_count"] > 0
    assert optimize_frozen_strategy(rows, symbol="EUR/USD") is not None


def test_candidate_ledger_fingerprint_detects_mutation() -> None:
    rows = _ledger_rows()
    original = candidate_ledger_fingerprint(rows)
    rows[0]["setup_score"] = 71

    assert candidate_ledger_fingerprint(rows) != original


def test_production_ledger_rejects_research_only_readiness_states() -> None:
    analysis = {
        "trade_gate": {"allowed": True, "decision_cap": None},
        "trade_permission": {"status": "caution"},
        "decision_engine": {"decision": "WATCH_ONLY"},
    }
    scenario = {
        "entry_status": "watch_zone",
        "ready_to_trade": False,
        "m15_quality": "relaxed",
    }

    assert trade_open_block_reason(analysis, scenario) is None
    assert trade_open_block_reason(
        analysis,
        scenario,
        strict_execution=True,
    ) == "blocked_by_permission"


def test_production_ledger_accepts_only_live_equivalent_candidate() -> None:
    analysis = {
        "trade_gate": {"allowed": True, "decision_cap": None},
        "trade_permission": {"status": "allowed"},
        "decision_engine": {"decision": "READY_TO_TRADE"},
        "journal_feedback": {},
    }
    scenario = {
        "entry_status": "confirmed_entry",
        "ready_to_trade": True,
        "m15_quality": "strict",
    }

    assert trade_open_block_reason(
        analysis,
        scenario,
        strict_execution=True,
    ) is None


def test_validation_engine_requires_a_frozen_strategy() -> None:
    candle = Candle(
        time=datetime(2025, 1, 1, tzinfo=UTC),
        open=1.1,
        high=1.2,
        low=1.0,
        close=1.1,
        volume=1,
    )
    request = replace(
        _request(),
        purpose=BACKTEST_PURPOSE_VALIDATION,
        execution_mode="EXECUTION_PARITY",
        cost_model_configured=True,
    )

    try:
        validate_backtest_input(
            request,
            {name: [candle] for name in ("D1", "H4", "H1", "M15")},
        )
    except ValueError as exc:
        assert "FROZEN_STRATEGY_CONFIG_REQUIRED" in str(exc)
    else:
        raise AssertionError("VALIDATION must reject a missing frozen config")


def test_validation_replay_optimizes_is_then_resets_and_replays_oos(
    monkeypatch,
) -> None:
    import core.backtest_validation_replay as replay_module

    requests: list[BacktestRequest] = []
    is_rows = _ledger_rows()
    oos_rows = _ledger_rows()

    def fake_run(request, _candles, **_kwargs):
        requests.append(request)
        if request.purpose == BACKTEST_PURPOSE_RESEARCH:
            return SimpleNamespace(
                candidate_ledger=is_rows,
                summary={"total_trades": 8},
            )
        assert request.purpose == BACKTEST_PURPOSE_VALIDATION
        assert request.initial_balance == 10_000
        assert request.frozen_strategy_config is not None
        frozen_id = request.frozen_strategy_config.config_id
        persisted_rows = [dict(row) for row in oos_rows]
        for row in persisted_rows:
            row["frozen_config_id"] = frozen_id
        return SimpleNamespace(
            candidate_ledger=persisted_rows,
            summary={"total_trades": 8},
            to_dict=lambda: {
                "trades": [],
                "backtest_contract": {},
                "scoring_contract": {},
                "data_manifest": {},
                "backtest_provenance": {},
                "request": {},
            },
        )

    monkeypatch.setattr(replay_module, "run_system_backtest", fake_run)

    result = replay_module.run_frozen_validation_replay(_request(), {})

    assert result["status"] == "COMPLETE"
    assert result["replay_version"] == CANDIDATE_REPLAY_VERSION
    assert len(requests) == 2
    assert requests[0].end == requests[1].start
    assert requests[1].frozen_strategy_config is not None
    assert result["account_state_reset"] == {
        "initial_balance": 10_000,
        "closed_trades": 0,
        "open_positions": 0,
    }


def test_validation_replay_reports_exact_optimizer_candidate_ids_when_inconclusive(
    monkeypatch,
) -> None:
    import core.backtest_validation_replay as replay_module

    requests: list[BacktestRequest] = []
    clean_rows = _ledger_rows()[:7]
    dirty_row = dict(
        _ledger_rows(side="sell")[0],
        candidate_id="dirty-loose",
        m15_quality="loose",
    )
    is_rows = clean_rows + [dirty_row]

    def fake_run(request, _candles, **_kwargs):
        requests.append(request)
        assert request.purpose == BACKTEST_PURPOSE_RESEARCH
        return SimpleNamespace(
            candidate_ledger=is_rows,
            summary={"total_trades": 7},
        )

    monkeypatch.setattr(replay_module, "run_system_backtest", fake_run)

    result = replay_module.run_frozen_validation_replay(_request(), {})

    diagnostics = result["is_optimizer_diagnostics"]
    assert result["status"] == "INCONCLUSIVE"
    assert result["reason"] == "IS_CANDIDATE_LEDGER_NOT_OPTIMIZABLE"
    assert len(requests) == 1
    assert diagnostics["release_candidate_ids"] == [
        row["candidate_id"] for row in clean_rows
    ]
    assert diagnostics["release_candidate_count"] == 7
    assert diagnostics["passing_threshold_bucket_count"] == 0
    assert diagnostics["rejection_reasons"]["RELEASE_M15_QUALITY_NOT_STRICT"] == 1
