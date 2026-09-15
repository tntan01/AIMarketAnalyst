"""Analysis engine — thin wrapper around :class:`core.analysis_pipeline.AnalysisPipeline`.

Public API
----------
* :func:`analyze_symbol` — main entry point (delegates to AnalysisPipeline).
* :func:`build_analysis_context` — legacy helper for trend + structure context.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.analysis_pipeline import AnalysisPipeline, build_analysis_context
from core.market_models import Candle
from core.risk_engine import AnalysisInput


def analyze_symbol(
    request: AnalysisInput,
    candles_by_timeframe: dict[str, list[Candle]],
    *,
    data_quality: dict[str, Any] | None = None,
    macro_alignment: dict[str, int] | None = None,
    macro_confidence: float = 1.0,
    ai_commentary: str | None = None,
    ai_meta: dict[str, Any] | None = None,
    m15_candles: list[Candle] | None = None,
    m15_as_of: datetime | str | None = None,
    snapshot_as_of: datetime | str | None = None,
    tick_size: float | None = None,
    tick_size_source: str | None = None,
    core_reason_codes: tuple[str, ...] = (),
    correlation_context: dict[str, Any] | None = None,
    quote_to_usd_rate: float | None = None,
    closed_trades: list[dict[str, Any]] | None = None,
    open_trades: list[dict[str, Any]] | None = None,
    account_guard_settings: dict[str, Any] | None = None,
    trade_date: datetime | None = None,
    execution_quality_score: int | float | str | None = None,
    thresholds: dict[str, int | float] | None = None,
    scanner_fast_tier1: bool = False,
) -> dict[str, Any]:
    """Orchestrate the full market analysis pipeline.

    This is the main entry point used by the scanner controller and
    integration tests.  It delegates to
    :class:`~core.analysis_pipeline.AnalysisPipeline` while keeping the
    exact same signature and output contract.

    Returns a dict with keys documented in ``test_analyze_symbol_all_keys_present``.
    """
    pipeline = AnalysisPipeline()
    return pipeline.execute(
        request,
        candles_by_timeframe,
        data_quality=data_quality,
        macro_alignment=macro_alignment,
        macro_confidence=macro_confidence,
        ai_commentary=ai_commentary,
        ai_meta=ai_meta,
        m15_candles=m15_candles,
        m15_as_of=m15_as_of,
        snapshot_as_of=snapshot_as_of,
        tick_size=tick_size,
        tick_size_source=tick_size_source,
        core_reason_codes=core_reason_codes,
        correlation_context=correlation_context,
        quote_to_usd_rate=quote_to_usd_rate,
        closed_trades=closed_trades,
        open_trades=open_trades,
        account_guard_settings=account_guard_settings,
        trade_date=trade_date,
        execution_quality_score=execution_quality_score,
        thresholds=thresholds,
        scanner_fast_tier1=scanner_fast_tier1,
    )
