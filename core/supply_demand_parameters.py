from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class SDParameterSpec:
    name: str
    unit: str
    default: Decimal
    minimum: Decimal
    maximum: Decimal


_SPECS = {
    "min_candles_per_timeframe": ("nến", 100, 30, 5000),
    "atr_period": ("nến", 14, 5, 100),
    "atr_warmup_bars": ("True Range", 200, 50, 5000),
    "epsilon_atr_ratio": ("ATR", 0.01, 0, 0.10),
    "epsilon_min_ticks": ("tick", 1, 1, 10),
    "leg_min_bars": ("nến", 1, 1, 3), "leg_max_bars": ("nến", 3, 1, 10),
    "leg_min_net_move_atr": ("ATR", 1.0, 0.25, 5.0),
    "leg_min_directional_range_ratio": ("tỷ lệ", 0.60, 0.50, 1.0),
    "leg_min_body_ratio": ("tỷ lệ", 0.60, 0.10, 1.0),
    "base_min_bars": ("nến", 1, 1, 4), "base_max_bars": ("nến", 4, 1, 4),
    "base_max_candle_range_atr": ("ATR", 0.80, 0.10, 3.0),
    "base_max_body_ratio": ("tỷ lệ", 0.50, 0.05, 1.0),
    "base_max_cluster_width_atr": ("ATR", 1.20, 0.10, 5.0),
    "base_min_overlap_ratio": ("tỷ lệ nến", 0.50, 0, 1.0),
    "base_max_gap_atr": ("ATR", 0.10, 0, 1.0),
    "departure_min_move_atr": ("ATR", 1.50, 0.50, 6.0),
    "departure_breakout_atr": ("ATR", 0.10, 0, 1.0),
    "departure_max_base_reentry_ratio": ("tỷ lệ base", 0.50, 0, 1.0),
    "departure_min_body_ratio": ("tỷ lệ", 0.65, 0.10, 1.0),
    "duplicate_confirmation_window_bars": ("nến", 3, 0, 20),
    "duplicate_min_overlap_ratio": ("tỷ lệ", 0.80, 0.50, 1.0),
    "zone_max_width_atr": ("ATR", 1.20, 0.10, 5.0), "zone_min_width_ticks": ("tick", 2, 1, 20),
    "swing_left_bars": ("nến", 2, 1, 10), "swing_right_bars": ("nến", 2, 1, 10),
    "d1_structure_lookback_bars": ("nến D1", 250, 20, 2000),
    "discount_position_max": ("tỷ lệ range", 0.45, 0, 0.50), "premium_position_min": ("tỷ lệ range", 0.55, 0.50, 1.0),
    "nested_min_overlap_ratio": ("tỷ lệ H1", 0.80, 0.50, 1.0), "break_wick_buffer_atr": ("ATR", 0.20, 0, 2.0),
    "zone_max_age_d1_bars": ("nến D1", 120, 20, 500), "d1_h4_min_overlap_ratio": ("tỷ lệ H4", 0.80, 0.50, 1.0),
    "d1_obstacle_near_atr": ("current ATR H4", 0.50, 0, 2.0), "zone_max_age_h4_bars": ("nến H4", 120, 10, 2000),
    "zone_max_age_h1_bars": ("nến H1", 240, 10, 5000), "departure_swing_lookback_bars": ("nến", 60, 5, 500),
    "m15_swing_lookback_bars": ("nến M15", 40, 5, 500),
    "quality_departure_mid_atr": ("ATR", 2.0, 1.5, 5.0), "quality_departure_high_atr": ("ATR", 2.5, 1.5, 6.0),
    "quality_base_compact_max_bars": ("nến", 2, 1, 4), "quality_base_narrow_width_atr": ("ATR", 0.60, 0.10, 1.20),
    "quality_base_small_body_ratio": ("tỷ lệ", 0.35, 0.05, 0.50), "quality_rr_mid": ("R", 2.5, 1.0, 10.0),
    "quality_rr_high": ("R", 3.0, 1.0, 15.0), "quality_grade_a_min": ("điểm", 85, 70, 100),
    "quality_grade_b_min": ("điểm", 70, 1, 99), "h4_entry_proximal_ratio": ("tỷ lệ vùng", 0.50, 0.10, 1.0),
    "watch_distance_atr": ("ATR", 0.50, 0, 5.0), "m15_confirmation_max_bars": ("nến M15", 8, 1, 50),
    "rejection_min_body_ratio": ("tỷ lệ", 0.20, 0.01, 1.0), "rejection_min_body_atr": ("ATR M15", 0.10, 0, 2.0),
    "rejection_min_wick_body_ratio": ("wick/body", 1.0, 0, 10.0), "sl_buffer_atr": ("ATR", 0.10, 0, 2.0),
    "sl_buffer_min_ticks": ("tick", 2, 1, 20), "min_risk_ticks": ("tick", 2, 1, 20), "min_rr": ("R", 2.0, 1.0, 10.0),
    "max_spread_risk_ratio": ("tỷ lệ", 0.10, 0, 0.50), "data_stale_expected_bars": ("biên", 2, 1, 10),
    "candle_time_tolerance_seconds": ("giây", 1, 0, 60), "analysis_poll_seconds": ("giây", 5, 1, 60),
}


def parameter_specs() -> dict[str, SDParameterSpec]:
    return {name: SDParameterSpec(name, unit, Decimal(str(default)), Decimal(str(minimum)), Decimal(str(maximum))) for name, (unit, default, minimum, maximum) in _SPECS.items()}


def validate_parameters(values: dict[str, Any] | None = None) -> dict[str, Decimal]:
    values = values or {}
    specs = parameter_specs()
    unknown = sorted(set(values) - set(specs))
    if unknown:
        raise ValueError(f"Unknown SD parameters: {', '.join(unknown)}")
    result = {name: spec.default for name, spec in specs.items()}
    for name, raw in values.items():
        try: value = Decimal(str(raw))
        except Exception as exc: raise ValueError(f"Invalid SD parameter: {name}") from exc
        if not value.is_finite() or not specs[name].minimum <= value <= specs[name].maximum:
            raise ValueError(f"SD parameter out of range: {name}")
        result[name] = value
    relations = (("leg_min_bars", "leg_max_bars"), ("base_min_bars", "base_max_bars"), ("atr_period", "atr_warmup_bars"), ("discount_position_max", "premium_position_min"), ("departure_min_move_atr", "quality_departure_mid_atr"), ("quality_departure_mid_atr", "quality_departure_high_atr"), ("min_rr", "quality_rr_mid"), ("quality_rr_mid", "quality_rr_high"), ("quality_grade_b_min", "quality_grade_a_min"), ("quality_base_compact_max_bars", "base_max_bars"), ("quality_base_narrow_width_atr", "base_max_cluster_width_atr"), ("quality_base_narrow_width_atr", "zone_max_width_atr"), ("quality_base_small_body_ratio", "base_max_body_ratio"))
    for left, right in relations:
        if result[left] >= result[right]: raise ValueError(f"Invalid SD parameter relation: {left} < {right}")
    return result
