"""Schema/policy + eligibility của bản đồ độ nhạy VIX theo cặp tiền.

Tách từ ``core/vix_pair_backtest.py`` ở Bước 4 loại bỏ Backtest
(2026-09-08): ``core/correlation_check`` (phân tích live) chỉ cần các
predicate eligibility fail-closed và hằng số schema; phần thống kê/seed/
lưu nạp (producer, chạy offline qua ``scripts/run_vix_pair_backtest.py``)
nằm lại module cũ và import ngược từ đây. Hành vi giữ nguyên từng dòng.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

# --- Hằng số schema/policy của sensitivity map (giá trị giữ nguyên) ---
STRONG_NEGATIVE_THRESHOLD = -0.25
STRONG_POSITIVE_THRESHOLD = 0.25
MILD_NEGATIVE_THRESHOLD = -0.15
MILD_POSITIVE_THRESHOLD = 0.15

SENSITIVITY_MIN = -5.0
SENSITIVITY_MAX = 5.0

MIN_LOOKBACK_DAYS = 120

SIGNIFICANCE_ALPHA = 0.05

MIN_SENSITIVITY_FACTOR = 0.10

SENSITIVITY_SCHEMA_VERSION = 2

DEFAULT_TTL_DAYS = 90


def is_sensitivity_map_stale(
    sensitivity_map: dict[str, Any],
    *,
    now: datetime | None = None,
) -> bool:
    """Kiểm tra sensitivity map đã hết hạn chưa.

    Parameters
    ----------
    sensitivity_map : dict
        Sensitivity map đã load (phải có key "meta" với "generated_at_utc" và "ttl_days").
    now : datetime | None
        Thời điểm kiểm tra. None → dùng UTC now.

    Returns
    -------
    bool
        True nếu map đã hết hạn hoặc không thể xác định.
    """
    meta = sensitivity_map.get("meta")
    if not isinstance(meta, dict):
        return True  # fail-safe

    # Seed data luôn được coi là stale (cần backtest thực tế)
    if meta.get("is_seed") is True:
        return True

    ttl_days = meta.get("ttl_days", DEFAULT_TTL_DAYS)
    generated_str = meta.get("generated_at_utc", "")

    try:
        generated = datetime.fromisoformat(str(generated_str))
        _now = now if now is not None else datetime.now(UTC)
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=UTC)
        if _now.tzinfo is None:
            _now = _now.replace(tzinfo=UTC)
        age_days = (_now - generated).total_seconds() / 86400.0
        ttl = float(ttl_days)
        # Future timestamps beyond a small clock-skew tolerance and invalid TTL
        # are both unsafe, not "fresh forever".
        return ttl <= 0 or age_days < -1.0 or age_days > ttl
    except (ValueError, TypeError, OverflowError):
        return True  # fail-safe


def sensitivity_map_ineligibility_reason(
    sensitivity_map: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> str | None:
    """Trả lý do map không được phép tác động production scoring."""
    if not isinstance(sensitivity_map, dict):
        return "map_not_dict"
    meta = sensitivity_map.get("meta")
    pairs = sensitivity_map.get("pairs")
    if not isinstance(meta, dict):
        return "missing_meta"
    if not isinstance(pairs, dict) or not pairs:
        return "missing_pairs"
    if meta.get("is_seed") is not False:
        return "seed_or_unverified_origin"
    if meta.get("status") != "validated":
        return "backtest_not_validated"
    try:
        schema_version = int(meta.get("schema_version", 0))
        vix_points = int(meta.get("vix_data_points", 0))
    except (TypeError, ValueError, OverflowError):
        return "invalid_evidence_metadata"
    if schema_version < SENSITIVITY_SCHEMA_VERSION:
        return "legacy_alignment_schema"
    if meta.get("alignment_method") != "intersect_close_dates_before_returns":
        return "unsafe_alignment_method"
    if vix_points < MIN_LOOKBACK_DAYS:
        return "insufficient_vix_observations"
    if is_sensitivity_map_stale(sensitivity_map, now=now):
        return "stale"

    has_validated_pair = False
    has_actionable_pair = False
    for pair_data in pairs.values():
        if not isinstance(pair_data, dict):
            return "malformed_pair_entry"
        try:
            data_points = int(pair_data.get("data_points", 0))
        except (TypeError, ValueError, OverflowError):
            return "malformed_pair_entry"
        if data_points >= MIN_LOOKBACK_DAYS:
            # Schema-2 results explicitly retain significance evidence even
            # when the pair is neutral/non-actionable.
            if "p_value" not in pair_data or "statistically_significant" not in pair_data:
                return "missing_significance_evidence"
            has_validated_pair = True
            try:
                corr = float(pair_data.get("correlation", 0.0))
                p_value = float(pair_data.get("p_value", 1.0))
                factor = float(pair_data.get("sensitivity_factor", 1.0))
            except (TypeError, ValueError, OverflowError):
                return "malformed_pair_entry"
            if not all(math.isfinite(value) for value in (corr, p_value, factor)):
                return "malformed_pair_entry"
            if not 0.0 <= p_value <= 1.0 or not 0.0 <= factor <= 1.0:
                return "malformed_pair_entry"
            significant = pair_data.get("statistically_significant")
            actionable = pair_data.get("actionable")
            direction = pair_data.get("vix_direction")
            if not isinstance(significant, bool) or not isinstance(actionable, bool):
                return "malformed_significance_evidence"
            if actionable:
                if (
                    not significant
                    or p_value > SIGNIFICANCE_ALPHA
                    or abs(corr) <= MILD_POSITIVE_THRESHOLD
                    or direction not in {"falls_on_vix_up", "rises_on_vix_up"}
                ):
                    return "inconsistent_actionable_pair"
                has_actionable_pair = True
            elif direction != "indeterminate" or factor != 1.0:
                return "non_actionable_pair_not_neutral"
    if not has_validated_pair:
        return "insufficient_pair_observations"
    if not has_actionable_pair:
        return "hypothesis_not_confirmed"
    return None


def is_sensitivity_map_eligible(
    sensitivity_map: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> bool:
    """True chỉ cho map data-backed, schema mới, đủ mẫu và còn TTL."""
    return sensitivity_map_ineligibility_reason(sensitivity_map, now=now) is None
