"""Chronological IS optimization followed by frozen OOS replay."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any, Callable

from core.backtest_candidate_ledger import (
    CANDIDATE_REPLAY_VERSION,
    candidate_ledger_fingerprint,
    optimize_frozen_strategy,
)
from core.backtest_contract import (
    BACKTEST_PURPOSE_RESEARCH,
    BACKTEST_PURPOSE_VALIDATION,
)
from core.system_backtest_engine import (
    AnalysisFn,
    BacktestRequest,
    run_system_backtest,
)


def run_frozen_validation_replay(
    request: BacktestRequest,
    candles_by_timeframe: dict[str, list],
    *,
    split_ratio: float = 0.70,
    analysis_fn: AnalysisFn | None = None,
    progress_callback: Callable[[int, str], None] | None = None,
) -> dict[str, Any]:
    """Optimize only IS ledger and run OOS from a clean account state."""

    if not 0.5 <= split_ratio <= 0.9:
        raise ValueError("split_ratio phải nằm trong [0.5, 0.9].")
    split_time = request.start + (request.end - request.start) * split_ratio
    progress = progress_callback or (lambda _percent, _message: None)
    runner_kwargs: dict[str, Any] = {"progress_callback": progress}
    if analysis_fn is not None:
        runner_kwargs["analysis_fn"] = analysis_fn

    is_request = replace(
        request,
        start=request.start,
        end=split_time,
        purpose=BACKTEST_PURPOSE_RESEARCH,
        frozen_strategy_config=None,
        min_final_score=0,
        candidate_ledger_enabled=True,
    )
    progress(5, "Đang tạo Candidate Ledger In-Sample...")
    is_result = run_system_backtest(
        is_request,
        candles_by_timeframe,
        **runner_kwargs,
        phase_label="Kiểm chứng In-Sample",
    )
    frozen = optimize_frozen_strategy(
        is_result.candidate_ledger,
        symbol=request.symbol,
    )
    if frozen is None:
        return {
            "replay_version": CANDIDATE_REPLAY_VERSION,
            "status": "INCONCLUSIVE",
            "reason": "IS_CANDIDATE_LEDGER_NOT_OPTIMIZABLE",
            "is_start": request.start.isoformat(),
            "is_end": split_time.isoformat(),
            "oos_start": split_time.isoformat(),
            "oos_end": request.end.isoformat(),
            "is_candidate_ledger": is_result.candidate_ledger,
            "is_candidate_ledger_fingerprint": candidate_ledger_fingerprint(
                is_result.candidate_ledger
            ),
            "frozen_strategy_config": None,
            "oos_candidate_ledger": [],
            "oos_trades": [],
        }

    oos_request = replace(
        request,
        start=split_time,
        end=request.end,
        initial_balance=request.initial_balance,
        purpose=BACKTEST_PURPOSE_VALIDATION,
        frozen_strategy_config=frozen,
        min_final_score=0,
        candidate_ledger_enabled=True,
    )
    progress(55, "Đang replay OOS với cấu hình đã đóng băng...")
    oos_result = run_system_backtest(
        oos_request,
        candles_by_timeframe,
        **runner_kwargs,
        phase_label="Kiểm chứng Out-Of-Sample",
    )
    oos_payload = oos_result.to_dict()
    return {
        "replay_version": CANDIDATE_REPLAY_VERSION,
        "status": "COMPLETE",
        "is_start": request.start.isoformat(),
        "is_end": split_time.isoformat(),
        "oos_start": split_time.isoformat(),
        "oos_end": request.end.isoformat(),
        "interval": "[start,end)",
        "is_summary": is_result.summary,
        "oos_summary": oos_result.summary,
        "is_candidate_ledger": is_result.candidate_ledger,
        "is_candidate_ledger_fingerprint": candidate_ledger_fingerprint(
            is_result.candidate_ledger
        ),
        "oos_candidate_ledger": oos_result.candidate_ledger,
        "oos_candidate_ledger_fingerprint": candidate_ledger_fingerprint(
            oos_result.candidate_ledger
        ),
        "frozen_strategy_config": frozen.to_dict(),
        "oos_trades": oos_payload["trades"],
        "backtest_contract": oos_payload["backtest_contract"],
        "scoring_contract": oos_payload["scoring_contract"],
        "data_manifest": oos_payload["data_manifest"],
        "backtest_provenance": oos_payload["backtest_provenance"],
        "request": oos_payload["request"],
        "account_state_reset": {
            "initial_balance": request.initial_balance,
            "closed_trades": 0,
            "open_positions": 0,
        },
    }
