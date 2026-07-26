"""Calendar-based Walk-Forward optimize/freeze/OOS replay."""

from __future__ import annotations

import calendar
from dataclasses import replace
from datetime import datetime
import hashlib
from typing import Any, Callable

from core.backtest_candidate_ledger import (
    CANDIDATE_REPLAY_VERSION,
    FrozenStrategyConfig,
    optimize_frozen_strategy,
)
from core.backtest_contract import (
    BACKTEST_PURPOSE_RESEARCH,
    BACKTEST_PURPOSE_VALIDATION,
)
from core.system_backtest_engine import (
    BacktestRequest,
    BacktestTrade,
    run_system_backtest,
    summarize_backtest_trades,
)


WALK_FORWARD_VERSION = "walk-forward-calendar-v2"


def run_walk_forward(
    request: BacktestRequest,
    candles_by_timeframe: dict[str, list],
    is_months: int = 6,
    oos_months: int = 3,
    step_months: int = 3,
    progress_callback: Callable[[int, str], None] | None = None,
) -> dict[str, Any]:
    if min(is_months, oos_months, step_months) <= 0:
        raise ValueError("Số tháng IS, OOS và step phải lớn hơn 0.")
    boundaries = calendar_walk_forward_windows(
        request.start,
        request.end,
        is_months=is_months,
        oos_months=oos_months,
        step_months=step_months,
    )
    if not boundaries:
        return _inconclusive(
            error=(
                f"Khoảng thời gian quá ngắn. Cần đủ {is_months} tháng IS "
                f"và {oos_months} tháng OOS theo lịch."
            )
        )

    progress = progress_callback or (lambda _percent, _message: None)
    windows: list[dict[str, Any]] = []
    unique_is: dict[str, BacktestTrade] = {}
    unique_oos: dict[str, BacktestTrade] = {}
    duplicate_oos_count = 0

    for index, (is_start, is_end, oos_start, oos_end) in enumerate(
        boundaries,
        start=1,
    ):
        progress(
            int(index * 100 / len(boundaries)),
            (
                f"Walk-Forward {index}/{len(boundaries)}: "
                f"IS={is_start:%Y-%m-%d} OOS={oos_start:%Y-%m-%d}"
            ),
        )
        base_window = {
            "window_id": f"wf-{index:03d}",
            "interval": "[start,end)",
            "is_start": is_start.isoformat(),
            "is_end": is_end.isoformat(),
            "oos_start": oos_start.isoformat(),
            "oos_end": oos_end.isoformat(),
            "optimization_source": "IS_CANDIDATE_LEDGER",
            "oos_replay": True,
            "replay_version": CANDIDATE_REPLAY_VERSION,
        }
        is_request = replace(
            request,
            start=is_start,
            end=is_end,
            purpose=BACKTEST_PURPOSE_RESEARCH,
            frozen_strategy_config=None,
            min_final_score=0,
            candidate_ledger_enabled=True,
        )
        try:
            is_result = run_system_backtest(
                is_request,
                candles_by_timeframe,
                progress_callback=progress,
            )
            frozen = optimize_frozen_strategy(
                is_result.candidate_ledger,
                symbol=request.symbol,
            )
            if frozen is None:
                windows.append({
                    **base_window,
                    "is_summary": summarize_backtest_trades(is_result.trades),
                    "oos_summary": None,
                    "frozen_strategy_config": None,
                    "error": "IS_CANDIDATE_LEDGER_NOT_OPTIMIZABLE",
                })
                continue
            selected_is = _selected_is_trades(
                is_result.trades,
                is_result.candidate_ledger,
                frozen,
            )
            oos_request = replace(
                request,
                start=oos_start,
                end=oos_end,
                initial_balance=request.initial_balance,
                purpose=BACKTEST_PURPOSE_VALIDATION,
                frozen_strategy_config=frozen,
                min_final_score=0,
                candidate_ledger_enabled=True,
            )
            oos_result = run_system_backtest(
                oos_request,
                candles_by_timeframe,
                progress_callback=progress,
            )
        except Exception as exc:
            windows.append({
                **base_window,
                "is_summary": None,
                "oos_summary": None,
                "frozen_strategy_config": None,
                "error": str(exc),
            })
            continue

        for trade in selected_is:
            unique_is.setdefault(_trade_identity(trade), trade)
        window_duplicates = 0
        for trade in oos_result.trades:
            identity = _trade_identity(trade)
            if identity in unique_oos:
                duplicate_oos_count += 1
                window_duplicates += 1
            else:
                unique_oos[identity] = trade
        windows.append({
            **base_window,
            "is_summary": summarize_backtest_trades(selected_is),
            "oos_summary": summarize_backtest_trades(oos_result.trades),
            "frozen_strategy_config": frozen.to_dict(),
            "is_candidate_count": len(is_result.candidate_ledger),
            "oos_candidate_count": len(oos_result.candidate_ledger),
            "oos_trade_count": len(oos_result.trades),
            "duplicate_oos_excluded_from_aggregate": window_duplicates,
            "oos_trade_ids": [
                _trade_identity(trade) for trade in oos_result.trades
            ],
            "oos_rejection_reasons": _candidate_rejection_counts(
                oos_result.candidate_ledger
            ),
        })

    aggregate_is = (
        summarize_backtest_trades(list(unique_is.values()))
        if unique_is
        else None
    )
    aggregate_oos = (
        summarize_backtest_trades(list(unique_oos.values()))
        if unique_oos
        else None
    )
    successful = [
        window for window in windows
        if isinstance(window.get("frozen_strategy_config"), dict)
        and isinstance(window.get("oos_summary"), dict)
    ]
    if aggregate_is is None or aggregate_oos is None or not successful:
        return _inconclusive(
            windows=windows,
            aggregate_is=aggregate_is,
            aggregate_oos=aggregate_oos,
            duplicate_oos_count=duplicate_oos_count,
        )

    is_expectancy = float(aggregate_is.get("expectancy_r", 0) or 0)
    oos_expectancy = float(aggregate_oos.get("expectancy_r", 0) or 0)
    ratio = round(oos_expectancy / is_expectancy, 4) if is_expectancy > 0 else 0.0
    if ratio >= 1.0:
        score = 100.0
    elif ratio < 0.3:
        score = 0.0
    else:
        score = round((ratio - 0.3) / 0.7 * 100.0, 1)
    verdict = "ROBUST" if score >= 70 else "SUSPECT" if score >= 40 else "OVERFITTING"
    return {
        "version": WALK_FORWARD_VERSION,
        "replay_version": CANDIDATE_REPLAY_VERSION,
        "interval": "[start,end)",
        "calendar_periods": True,
        "deduplication_applied": True,
        "windows": windows,
        "aggregate_is": aggregate_is,
        "aggregate_oos": aggregate_oos,
        "oos_is_expectancy_ratio": ratio,
        "robustness_score": score,
        "verdict": verdict,
        "window_count": len(windows),
        "successful_window_count": len(successful),
        "unique_oos_trade_count": len(unique_oos),
        "duplicate_oos_trade_count": duplicate_oos_count,
        "unique_oos_trade_fingerprint": _identity_fingerprint(unique_oos),
    }


def calendar_walk_forward_windows(
    start: datetime,
    end: datetime,
    *,
    is_months: int,
    oos_months: int,
    step_months: int,
) -> list[tuple[datetime, datetime, datetime, datetime]]:
    """Return exact calendar windows with half-open IS/OOS boundaries."""

    windows: list[tuple[datetime, datetime, datetime, datetime]] = []
    current = start
    while True:
        is_end = add_calendar_months(current, is_months)
        oos_end = add_calendar_months(is_end, oos_months)
        if oos_end > end:
            break
        windows.append((current, is_end, is_end, oos_end))
        current = add_calendar_months(current, step_months)
    return windows


def add_calendar_months(value: datetime, months: int) -> datetime:
    total = value.year * 12 + value.month - 1 + int(months)
    year, month_index = divmod(total, 12)
    month = month_index + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _selected_is_trades(
    trades: list[BacktestTrade],
    ledger: list[dict[str, Any]],
    frozen: FrozenStrategyConfig,
) -> list[BacktestTrade]:
    selected_ids = {
        str(row.get("candidate_id") or "")
        for row in ledger
        if isinstance(row, dict)
        and row.get("base_eligible") is True
        and row.get("research_only") is not True
        and str(row.get("side") or "") == frozen.side
        and str(row.get("market_regime") or "") in frozen.allowed_regimes
        and float(row.get("setup_score", 0) or 0) >= frozen.min_setup_score
        and float(row.get("expected_effective_rr", 0) or 0)
        >= frozen.min_expected_rr
    }
    return [trade for trade in trades if trade.candidate_id in selected_ids]


def _trade_identity(trade: BacktestTrade) -> str:
    if trade.candidate_id:
        return trade.candidate_id
    raw = "|".join((trade.symbol, trade.side, trade.entry_time, trade.exit_time or ""))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _identity_fingerprint(values: dict[str, BacktestTrade]) -> str:
    canonical = "|".join(sorted(values))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _candidate_rejection_counts(ledger: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in ledger:
        reasons = entry.get("strategy_rejection_reasons", [])
        if isinstance(reasons, list):
            for reason in reasons:
                key = str(reason or "")
                if key:
                    counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _inconclusive(
    *,
    error: str | None = None,
    windows: list[dict[str, Any]] | None = None,
    aggregate_is: dict[str, Any] | None = None,
    aggregate_oos: dict[str, Any] | None = None,
    duplicate_oos_count: int = 0,
) -> dict[str, Any]:
    values = windows or []
    result = {
        "version": WALK_FORWARD_VERSION,
        "replay_version": CANDIDATE_REPLAY_VERSION,
        "interval": "[start,end)",
        "calendar_periods": True,
        "deduplication_applied": True,
        "windows": values,
        "aggregate_is": aggregate_is,
        "aggregate_oos": aggregate_oos,
        "oos_is_expectancy_ratio": None,
        "robustness_score": None,
        "verdict": "INCONCLUSIVE",
        "window_count": len(values),
        "successful_window_count": sum(
            isinstance(window.get("frozen_strategy_config"), dict)
            and isinstance(window.get("oos_summary"), dict)
            for window in values
        ),
        "unique_oos_trade_count": (
            int((aggregate_oos or {}).get("total_trades", 0) or 0)
        ),
        "duplicate_oos_trade_count": duplicate_oos_count,
        "unique_oos_trade_fingerprint": hashlib.sha256(b"").hexdigest(),
    }
    if error:
        result["error"] = error
    return result
