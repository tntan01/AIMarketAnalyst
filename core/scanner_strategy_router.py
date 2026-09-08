"""Canonical router for scanner strategy selection (live, độc lập Backtest).

The router owns all branch selection and strategy threshold logic.

Bước 4b loại bỏ Backtest (2026-09-08): quyền auto-trade là cờ độc lập
``auto_trade_permitted`` (Bước 2, lựa chọn tường minh của người dùng).
Bước 5 (2026-09-09): engine Backtest đã xóa — validator evidence cũ
(``validate_backtest_config``) bị xóa cùng engine; router chỉ còn lean
validator. Nhánh ``BACKTEST_VALIDATED`` (giá trị enum lịch sử, hiển thị
"Đã kiểm định") nghĩa là "mã có cấu hình chiến lược riêng hợp lệ"; kiểm
tra live: đúng mã, side/regime hợp lệ, ngưỡng min_score/min_rr dương,
score metric hỗ trợ — tất cả fail-closed về DEFAULT_RULES/không-eligible.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any

from core.scanner_models import (
    BRANCH_BACKTEST_INVALID,
    BRANCH_BACKTEST_VALIDATED,
    BRANCH_DEFAULT_RULES,
    CONFIG_INVALID,
    CONFIG_NOT_CONFIGURED,
    CONFIG_VALIDATED,
    SETUP_SCORE_METRIC,
    SideEvaluation,
    StrategyEvaluation,
)
from core.scanner_strategy_engine import (
    evaluate_sides,
    finite_number,
    normalize_side,
    positive_number,
    unique_codes,
)


DEFAULT_MIN_SCORE = 65.0
DEFAULT_MIN_RR = 1.3
DEFAULT_MIN_SCORE_GAP = 10.0

_SIDE_DATA_CODES = frozenset({
    "MISSING_ANALYSIS",
    "MISSING_SELECTED_SIDE_SCENARIO",
    "FALLBACK_ENTRY_ZONE",
    "SIGNAL_SCORE_MISSING",
    "SETUP_SCORE_MISSING",
    "SETUP_SCORE_NOT_SELECTED_SIDE",
})


def route_strategy(
    row: dict[str, Any],
    auto_trade_config: dict[str, object] | None = None,
    *,
    side_evaluations: tuple[SideEvaluation, ...] | None = None,
    now: datetime | None = None,
) -> tuple[StrategyEvaluation, SideEvaluation | None]:
    """Route one symbol to exactly one strategy branch for this scan.

    ``now`` được giữ trong chữ ký vì tương thích caller; nhánh cấu hình riêng
    không còn phụ thuộc thời gian (expiry kiểm định đã gỡ — Bước 4b).
    """

    sides = (
        side_evaluations
        if side_evaluations is not None
        else evaluate_sides(row)
    )
    if auto_trade_config is None:
        return _evaluate_default_rules(row, sides)

    config_status, config_reasons = validate_auto_trade_config(
        auto_trade_config,
        row,
    )
    if config_status != CONFIG_VALIDATED:
        fallback, selected = _evaluate_default_rules(row, sides)
        reasons = unique_codes((
            "BACKTEST_CONFIG_INVALID",
            *config_reasons,
            *fallback.reason_codes,
        ))
        return (
            replace(
                fallback,
                branch=BRANCH_BACKTEST_INVALID,
                config_status=config_status,
                eligible=False,
                reason_codes=reasons,
            ),
            selected,
        )

    return _evaluate_validated_backtest(row, auto_trade_config, sides)


def validate_auto_trade_config(
    config: object,
    row: dict[str, Any] | None = None,
) -> tuple[str, tuple[str, ...]]:
    """Kiểm tra cấu hình chiến lược per-symbol — KHÔNG kiểm định Backtest.

    Chỉ giữ các kiểm tra cần thiết cho quyết định live:
    - payload phải là dict (malformed ⇒ fail-closed, không auto-trade);
    - symbol của config phải khớp row (tránh áp nhầm ngưỡng mã khác);
    - side ∈ {buy, sell, best}; có regime cấu hình;
    - min_score / min_rr là số dương dùng được;
    - score_metric (nếu khai báo) phải là metric router đánh giá.

    Reason codes giữ nguyên chuỗi lịch sử (``BACKTEST_*``) để không gãy
    dịch thuật UI/observability — đổi tên là việc cosmetic của Bước 5.
    """

    reasons: list[str] = []
    if not isinstance(config, dict):
        return CONFIG_INVALID, (
            "BACKTEST_CONFIG_INVALID",
            "BACKTEST_CONFIG_MALFORMED",
        )

    metric = str(config.get("score_metric", "") or "").strip()
    if metric and metric != SETUP_SCORE_METRIC:
        reasons.append("UNSUPPORTED_SCORE_METRIC")

    side = str(config.get("side", "") or "").strip().lower()
    if side not in {"buy", "sell", "best"}:
        reasons.append("BACKTEST_SIDE_INVALID")

    if not _configured_regimes(config):
        reasons.append("BACKTEST_REGIME_MISSING")

    if positive_number(config.get("min_score")) is None:
        reasons.append("BACKTEST_MIN_SCORE_MISSING")
    if positive_number(config.get("min_rr")) is None:
        reasons.append("BACKTEST_MIN_RR_MISSING")

    config_symbol = _normalize_symbol(config.get("symbol"))
    row_symbol = (
        _normalize_symbol(row.get("symbol")) if isinstance(row, dict) else ""
    )
    if config_symbol and row_symbol and config_symbol != row_symbol:
        reasons.append("BACKTEST_SYMBOL_MISMATCH")

    codes = unique_codes(reasons)
    if not codes:
        return CONFIG_VALIDATED, ()
    return CONFIG_INVALID, codes


def _evaluate_validated_backtest(
    row: dict[str, Any],
    config: dict[str, object],
    sides: tuple[SideEvaluation, ...],
) -> tuple[StrategyEvaluation, SideEvaluation | None]:
    reasons: list[str] = []
    if not isinstance(row, dict):
        reasons.append("INVALID_SCANNER_ROW")
        row = {}
    if not isinstance(row.get("analysis_result"), dict):
        reasons.append("MISSING_ANALYSIS")

    raw_best_side = str(row.get("best_side", "") or "").strip().lower()
    best_side = normalize_side(raw_best_side)
    if raw_best_side in {"neutral", "stand_aside", "skip"}:
        reasons.append("NO_TRADE_SIDE")
    elif best_side is None:
        reasons.append("INVALID_BEST_SIDE")

    configured_side = str(config.get("side", "") or "").strip().lower()
    selected_side = best_side if configured_side == "best" else normalize_side(
        configured_side
    )
    if selected_side is None:
        reasons.append("MISSING_SELECTED_SIDE")
    if (
        configured_side in {"buy", "sell"}
        and best_side is not None
        and selected_side != best_side
    ):
        reasons.append("CONFIG_SIDE_MISMATCH")

    side_evaluation = _side_map(sides).get(selected_side)
    _append_side_errors(reasons, side_evaluation)

    row_regime = str(row.get("market_regime", "") or "").strip().lower()
    if row_regime not in _configured_regimes(config):
        reasons.append("BACKTEST_REGIME_MISMATCH")

    score_value = (
        side_evaluation.setup_score if side_evaluation is not None else None
    )
    min_score = positive_number(config.get("min_score"))
    if score_value is None:
        reasons.append("SETUP_SCORE_MISSING")
    elif min_score is not None and score_value < min_score:
        reasons.append("SETUP_SCORE_BELOW_MIN")

    expected_rr = (
        side_evaluation.expected_effective_rr
        if side_evaluation is not None
        else None
    )
    min_rr = positive_number(config.get("min_rr"))
    if expected_rr is None:
        reasons.append("EXPECTED_RR_MISSING")
    elif min_rr is not None and expected_rr < min_rr:
        reasons.append("EXPECTED_RR_BELOW_MIN")

    reason_codes = unique_codes(reasons)
    return (
        StrategyEvaluation(
            branch=BRANCH_BACKTEST_VALIDATED,
            config_status=CONFIG_VALIDATED,
            selected_side=selected_side,
            score_metric=SETUP_SCORE_METRIC,
            score_value=score_value,
            min_score=min_score,
            expected_effective_rr=expected_rr,
            min_rr=min_rr,
            eligible=not reason_codes,
            reason_codes=reason_codes,
        ),
        side_evaluation,
    )


def _evaluate_default_rules(
    row: dict[str, Any],
    sides: tuple[SideEvaluation, ...],
) -> tuple[StrategyEvaluation, SideEvaluation | None]:
    reasons: list[str] = []
    if not isinstance(row, dict):
        row = {}
        reasons.append("INVALID_SCANNER_ROW")
    if not isinstance(row.get("analysis_result"), dict):
        reasons.append("MISSING_ANALYSIS")

    raw_best_side = str(row.get("best_side", "") or "").strip().lower()
    best_side = normalize_side(raw_best_side)
    if raw_best_side in {"neutral", "stand_aside", "skip"}:
        reasons.append("NO_TRADE_SIDE")
    elif best_side is None:
        reasons.append("INVALID_BEST_SIDE")

    direction_bias = (
        row.get("direction_bias")
        if isinstance(row.get("direction_bias"), dict)
        else {}
    )
    raw_score_gap = row.get("score_gap")
    if raw_score_gap is None:
        raw_score_gap = direction_bias.get("score_gap")
    score_gap = finite_number(raw_score_gap)
    min_gap = positive_number(
        direction_bias.get(
            "min_gap",
            row.get("min_score_gap", DEFAULT_MIN_SCORE_GAP),
        )
    ) or DEFAULT_MIN_SCORE_GAP
    if score_gap is None:
        reasons.append("SCORE_GAP_MISSING")
    elif score_gap < min_gap:
        reasons.append("SCORE_GAP_BELOW_MIN")
    if (
        "is_clear_bias" in direction_bias
        and direction_bias.get("is_clear_bias") is not True
    ):
        reasons.append("BEST_SIDE_NOT_CLEAR")

    side_evaluation = _side_map(sides).get(best_side)
    _append_side_errors(reasons, side_evaluation)

    min_score = positive_number(row.get("min_score")) or DEFAULT_MIN_SCORE
    score_value = (
        side_evaluation.setup_score if side_evaluation is not None else None
    )
    if score_value is None:
        reasons.append("SETUP_SCORE_MISSING")
    elif score_value < min_score:
        reasons.append("SETUP_SCORE_BELOW_DEFAULT_MIN")

    min_rr = positive_number(row.get("min_rr")) or DEFAULT_MIN_RR
    expected_rr = (
        side_evaluation.expected_effective_rr
        if side_evaluation is not None
        else None
    )
    if expected_rr is None:
        reasons.append("EXPECTED_RR_MISSING")
    elif expected_rr < min_rr:
        reasons.append("EXPECTED_RR_BELOW_DEFAULT_MIN")

    reason_codes = unique_codes(reasons)
    return (
        StrategyEvaluation(
            branch=BRANCH_DEFAULT_RULES,
            config_status=CONFIG_NOT_CONFIGURED,
            selected_side=best_side,
            score_metric=SETUP_SCORE_METRIC,
            score_value=score_value,
            min_score=min_score,
            expected_effective_rr=expected_rr,
            min_rr=min_rr,
            eligible=not reason_codes,
            reason_codes=reason_codes,
        ),
        side_evaluation,
    )


def _append_side_errors(
    reasons: list[str],
    side_evaluation: SideEvaluation | None,
) -> None:
    if side_evaluation is None:
        reasons.append("MISSING_SIDE_EVALUATION")
        return
    reasons.extend(
        code
        for code in side_evaluation.reason_codes
        if code in _SIDE_DATA_CODES
    )


def _side_map(
    sides: tuple[SideEvaluation, ...],
) -> dict[str, SideEvaluation]:
    return {item.side: item for item in sides}


def _configured_regimes(config: dict[str, object]) -> tuple[str, ...]:
    raw_allowed = config.get("allowed_regimes")
    values: list[str] = []
    if isinstance(raw_allowed, (list, tuple, set)):
        values.extend(str(item or "").strip().lower() for item in raw_allowed)
    raw_regime = str(config.get("regime", "") or "").strip().lower()
    if raw_regime:
        values.append(raw_regime)
    return unique_codes([value for value in values if value])


def _normalize_symbol(value: object) -> str:
    return "".join(char for char in str(value or "").upper() if char.isalnum())
