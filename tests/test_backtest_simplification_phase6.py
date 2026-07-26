from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.backtest_advanced import (
    advanced_research_manifest,
    run_monte_carlo_if_eligible,
)
from core.backtest_contract import (
    BACKTEST_PURPOSE_VALIDATION,
    resolve_backtest_run_policy,
)
from core.backtest_execution_parity import (
    EXECUTION_MODE_PARITY,
    EXECUTION_MODE_RESEARCH,
)
from core.backtest_market_data import _unexpected_gaps
from core.backtest_migration import migrate_snapshot_payload
from core.backtest_presentation import ACTION_NONE, result_action
from core.market_models import Candle
from core.scanner_candidate_engine import evaluate_scanner_candidate
from core.scanner_models import BRANCH_BACKTEST_VALIDATED, READY_NOW
from services.settings_service import SettingsService
from tests.test_scanner_strategy_router import _row, _validated_config


UTC = timezone.utc


def _candle(moment: datetime) -> Candle:
    return Candle(
        time=moment,
        open=1.0,
        high=1.1,
        low=0.9,
        close=1.0,
        volume=100,
    )


def test_final_acceptance_weekend_is_allowed_but_real_gap_is_detected() -> None:
    weekend = _unexpected_gaps(
        [
            _candle(datetime(2026, 1, 9, 21, tzinfo=UTC)),
            _candle(datetime(2026, 1, 11, 22, tzinfo=UTC)),
        ],
        timedelta(hours=1),
        symbol="EUR/USD",
        timeframe="H1",
    )
    weekday = _unexpected_gaps(
        [
            _candle(datetime(2026, 1, 12, 10, tzinfo=UTC)),
            _candle(datetime(2026, 1, 12, 12, tzinfo=UTC)),
        ],
        timedelta(hours=1),
        symbol="EUR/USD",
        timeframe="H1",
    )

    assert weekend == []
    assert len(weekday) == 1
    assert weekday[0]["missing_intervals"] == 1


def test_final_acceptance_validation_forces_parity_and_evidence() -> None:
    policy = resolve_backtest_run_policy(
        BACKTEST_PURPOSE_VALIDATION,
        EXECUTION_MODE_RESEARCH,
    )

    assert policy.execution_mode == EXECUTION_MODE_PARITY
    assert policy.run_validation_replay is True
    assert policy.run_walk_forward is True
    assert policy.release_candidate is True


def test_final_acceptance_research_and_advanced_outputs_cannot_publish() -> None:
    action = result_action(
        {
            "mode": "system_backtest",
            "request": {"symbol": "EUR/USD"},
            "lifecycle": {"status": "RESEARCH_ONLY"},
        },
        selected_symbol="EUR/USD",
    )
    manifest = advanced_research_manifest("portfolio")
    monte_carlo = run_monte_carlo_if_eligible([])

    assert action.kind == ACTION_NONE
    assert action.visible is False
    assert manifest["can_publish_config"] is False
    assert manifest["can_apply_symbol_config"] is False
    assert monte_carlo["status"] == "SKIPPED"
    assert monte_carlo["lifecycle"] == "RESEARCH_ONLY"


def test_final_acceptance_validated_config_reaches_strategy_router() -> None:
    decision = evaluate_scanner_candidate(_row(), _validated_config())

    assert decision.branch == BRANCH_BACKTEST_VALIDATED
    assert decision.status == READY_NOW
    assert decision.strategy_eligible is True


def test_final_acceptance_legacy_settings_and_snapshot_remain_fail_closed(
    tmp_path,
) -> None:
    service = SettingsService(tmp_path / "settings.json")
    service.storage.save({
        "features": {
            "backtest_config_v2": True,
            "backtest_engine_v2": True,
            "smc_scoring_mode": "v2",
        },
        "trading": {
            "symbol_settings": {
                "EUR/USD": {
                    "backtest": True,
                    "backtest_status": "VALIDATED",
                    "backtest_validation_fingerprint": "legacy-evidence",
                }
            }
        },
    })
    settings = service.load()
    symbol = settings.trading.symbol_settings["EUR/USD"]
    migrated = migrate_snapshot_payload({
        "backtest_contract": {"engine_version": "legacy-engine"},
        "summary": {"total_trades": 3},
    })

    assert not hasattr(settings.features, "backtest_config_v2")
    assert not hasattr(settings.features, "backtest_engine_v2")
    assert symbol.backtest is False
    assert symbol.backtest_validation_fingerprint == "legacy-evidence"
    assert migrated["lifecycle"]["status"] == "LEGACY_RESEARCH"
    assert migrated["summary"] == {"total_trades": 3}
