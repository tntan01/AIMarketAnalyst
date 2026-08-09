"""Bước 7 — VIX Pair Sensitivity Backtest Engine.

Tính tương quan giữa thay đổi VIX hàng ngày và returns của từng cặp tiền
để xây dựng sensitivity mapping thay cho hệ số phạt cào bằng hiện tại.

Cung cấp:
- compute_vix_pair_sensitivity(): tính Pearson correlation ΔVIX% vs pair returns
  trên đúng các khoảng ngày giao dịch chung
- get_vix_sensitivity_map(): đọc map từ disk
- is_sensitivity_map_stale(): kiểm tra TTL
- is_sensitivity_map_eligible(): chặn seed/map cũ/map thiếu bằng chứng
- generate_seed_sensitivity_map(): tạo seed chẩn đoán từ kiến thức thị trường;
  seed không bao giờ đủ điều kiện dùng cho scoring runtime
"""

from __future__ import annotations

import json
import logging
import math
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from config.paths import app_data_dir
from core.market_models import Candle

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Ngưỡng correlation để mô tả quan hệ theo hướng. Tên gọi cố ý không gán
# nguyên nhân "safe haven"/"risk-on": correlation ở cấp pair không thể phân
# biệt base yếu với quote được mua vào.
STRONG_NEGATIVE_THRESHOLD = -0.25
STRONG_POSITIVE_THRESHOLD = 0.25
MILD_NEGATIVE_THRESHOLD = -0.15
MILD_POSITIVE_THRESHOLD = 0.15

# Dải sensitivity score
SENSITIVITY_MIN = -5.0
SENSITIVITY_MAX = 5.0

# Lookback mặc định: ~1 năm giao dịch
DEFAULT_LOOKBACK_DAYS = 252

# Số daily-return observations tối thiểu để một pair được phép tác động
# production scoring. 20 điểm như bản cũ quá ít để kết luận về regime.
MIN_LOOKBACK_DAYS = 120

# Significance gate hai phía. Tương quan không vượt gate vẫn được báo cáo,
# nhưng direction/factor bị neutralize nên không thể thay đổi điểm.
SIGNIFICANCE_ALPHA = 0.05

# Không cho một correlation duy nhất triệt tiêu tuyệt đối VIX penalty.
MIN_SENSITIVITY_FACTOR = 0.10

# Schema 2 khóa hai invariant: align trên common close dates và significance.
SENSITIVITY_SCHEMA_VERSION = 2

# TTL mặc định cho sensitivity map: 90 ngày
DEFAULT_TTL_DAYS = 90

# Đường dẫn mặc định tới sensitivity file
DEFAULT_SENSITIVITY_PATH: Path | None = None


def _default_sensitivity_path() -> Path:
    """Đường dẫn runtime chuẩn trong app-data của người dùng."""
    global DEFAULT_SENSITIVITY_PATH
    if DEFAULT_SENSITIVITY_PATH is not None:
        return DEFAULT_SENSITIVITY_PATH
    # app_data_dir() là %APPDATA%/ai-market-analyst trên Windows (không phải
    # <repo>/data). Runtime loader ưu tiên chính đường dẫn này.
    path = app_data_dir() / "vix_pair_sensitivity.json"
    DEFAULT_SENSITIVITY_PATH = path
    return path


# ---------------------------------------------------------------------------
# Backtest computation
# ---------------------------------------------------------------------------


def _daily_closes_by_date(candles: list[Candle]) -> tuple[dict[date, float], int]:
    """Chuẩn hóa candles thành ``date -> positive close``.

    Input được sort/deduplicate theo ngày; nếu có nhiều bar cùng ngày thì bar
    có timestamp muộn nhất thắng. Số bar time/close không hợp lệ được trả kèm
    để report không âm thầm nuốt dữ liệu lỗi.
    """
    by_date: dict[date, tuple[datetime, float]] = {}
    invalid = 0
    for candle in candles:
        try:
            timestamp = candle.time
            close = float(candle.close)
            if not isinstance(timestamp, datetime) or not math.isfinite(close) or close <= 0:
                invalid += 1
                continue
            day = timestamp.date()
            comparable_time = timestamp.replace(tzinfo=None)
            previous = by_date.get(day)
            if previous is None or comparable_time >= previous[0]:
                by_date[day] = (comparable_time, close)
        except (AttributeError, TypeError, ValueError, OverflowError):
            invalid += 1
    return {day: item[1] for day, item in by_date.items()}, invalid


def _daily_pct_changes(candles: list[Candle]) -> list[float]:
    """Tính daily returns sau khi sort/deduplicate theo calendar date."""
    closes, _invalid = _daily_closes_by_date(candles)
    days = sorted(closes)
    return [
        (closes[days[i]] - closes[days[i - 1]]) / closes[days[i - 1]] * 100.0
        for i in range(1, len(days))
    ]


def _aligned_daily_pct_changes(
    vix_candles: list[Candle],
    pair_candles: list[Candle],
    *,
    lookback_days: int,
) -> tuple[list[float], list[float], dict[str, Any]]:
    """Tạo hai chuỗi return trên cùng start/end date cho từng observation.

    Chỉ join return theo endpoint là chưa đủ: nếu FX thiếu bar thứ Ba nhưng VIX
    có bar đó, return thứ Tư của hai chuỗi sẽ có horizon khác nhau. Vì vậy hàm
    này intersect *close dates trước*, rồi mới tính cả hai return qua cùng cặp
    ngày liên tiếp trong intersection.
    """
    vix_closes, invalid_vix = _daily_closes_by_date(vix_candles)
    pair_closes, invalid_pair = _daily_closes_by_date(pair_candles)
    common_dates = sorted(set(vix_closes).intersection(pair_closes))
    if len(common_dates) > lookback_days + 1:
        common_dates = common_dates[-(lookback_days + 1):]

    metadata: dict[str, Any] = {
        "invalid_vix_bars": invalid_vix,
        "invalid_pair_bars": invalid_pair,
        "dropped_vix_dates": 0,
        "dropped_pair_dates": 0,
        "data_start": "unknown",
        "data_end": "unknown",
    }
    if not common_dates:
        return [], [], metadata

    start, end = common_dates[0], common_dates[-1]
    common_set = set(common_dates)
    vix_window_dates = {day for day in vix_closes if start <= day <= end}
    pair_window_dates = {day for day in pair_closes if start <= day <= end}
    metadata.update({
        "dropped_vix_dates": len(vix_window_dates - common_set),
        "dropped_pair_dates": len(pair_window_dates - common_set),
        "data_start": start.isoformat(),
        "data_end": end.isoformat(),
    })

    vix_returns: list[float] = []
    pair_returns: list[float] = []
    for previous_day, current_day in zip(common_dates, common_dates[1:]):
        vix_returns.append(
            (vix_closes[current_day] - vix_closes[previous_day])
            / vix_closes[previous_day]
            * 100.0
        )
        pair_returns.append(
            (pair_closes[current_day] - pair_closes[previous_day])
            / pair_closes[previous_day]
            * 100.0
        )
    return vix_returns, pair_returns, metadata


def _pearson_correlation(x: list[float], y: list[float]) -> float:
    """Tính Pearson correlation coefficient giữa 2 chuỗi.

    Trả về 0.0 nếu không đủ dữ liệu hoặc độ lệch chuẩn = 0.
    """
    n = len(x)
    if n < 3 or len(y) != n:
        return 0.0

    mean_x = sum(x) / n
    mean_y = sum(y) / n

    cov = 0.0
    var_x = 0.0
    var_y = 0.0

    for i in range(n):
        dx = x[i] - mean_x
        dy = y[i] - mean_y
        cov += dx * dy
        var_x += dx * dx
        var_y += dy * dy

    if var_x == 0.0 or var_y == 0.0:
        return 0.0

    return cov / (math.sqrt(var_x) * math.sqrt(var_y))


def _correlation_p_value(corr: float, sample_size: int) -> float:
    """Two-sided p-value via Fisher's z normal approximation.

    Với n>=120 (gate ở trên), approximation đủ ổn định cho mục đích loại bỏ
    correlation nhiễu mà không kéo thêm scipy vào runtime desktop.
    """
    if sample_size < 4 or not math.isfinite(corr):
        return 1.0
    bounded = max(-1.0, min(1.0, corr))
    if abs(bounded) >= 1.0:
        return 0.0
    z_score = math.atanh(bounded) * math.sqrt(sample_size - 3)
    return max(0.0, min(1.0, math.erfc(abs(z_score) / math.sqrt(2.0))))


def _correlation_to_sensitivity(corr: float) -> float:
    """Quy đổi Pearson correlation → sensitivity score trong [-5, +5].

    sensitivity_score mang dấu của correlation:
    - correlation < 0: VIX↑ → pair↓
    - correlation > 0: VIX↑ → pair↑

    Dấu ở cấp pair không tự cho biết chuyển động đến từ base hay quote.

    Quy đổi piecewise-linear sau dead zone |r| <= 0.15.
    """
    if -0.15 <= corr <= 0.15:
        return 0.0

    abs_corr = abs(corr)
    score = (abs_corr - 0.15) / 0.85 * SENSITIVITY_MAX
    score = max(0.0, min(SENSITIVITY_MAX, score))
    return -score if corr < 0 else score


def _correlation_to_vix_direction(corr: float) -> str:
    """Quy đổi correlation → vix_direction string dùng bởi _vix_score().

    - "falls_on_vix_up": pair↓ when VIX↑ (corr < -0.15), SELL is with the flow
    - "rises_on_vix_up":  pair↑ when VIX↑ (corr > +0.15), BUY is with the flow
    - "indeterminate":    no clear directional relationship
    """
    if corr < -0.15:
        return "falls_on_vix_up"
    if corr > 0.15:
        return "rises_on_vix_up"
    return "indeterminate"


def _correlation_to_sensitivity_factor(corr: float) -> float:
    """Quy đổi correlation → sensitivity_factor (0-1).

    0.10 = VIX giải thích rất mạnh (|corr| >= 0.80) → gần-minimal penalty
    1.0 = VIX is noise (|corr| ≈ 0.0)       → full penalty

    Uses piecewise mapping:
    - |corr| >= 0.80 → factor = 0.10 (không triệt tiêu tuyệt đối penalty)
    - |corr| <= 0.15 → factor = 1.00 (pure noise)
    - Linear between: factor = 1.0 - (|corr| - 0.15) / 0.65
    """
    abs_corr = abs(corr)
    if abs_corr >= 0.80:
        return MIN_SENSITIVITY_FACTOR
    if abs_corr <= 0.15:
        return 1.0
    return round(
        max(
            MIN_SENSITIVITY_FACTOR,
            1.0 - (abs_corr - 0.15) / 0.65,
        ),
        2,
    )


def _classify_pair(corr: float) -> str:
    """Mô tả hướng/độ mạnh, không suy diễn nguyên nhân ở currency-level."""
    if corr < STRONG_NEGATIVE_THRESHOLD:
        return "strong_negative"
    if corr > STRONG_POSITIVE_THRESHOLD:
        return "strong_positive"
    if corr < MILD_NEGATIVE_THRESHOLD:
        return "mild_negative"
    if corr > MILD_POSITIVE_THRESHOLD:
        return "mild_positive"
    return "neutral"


def _unknown_pair_result(
    note: str,
    *,
    data_points: int = 0,
    alignment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "correlation": 0.0,
        "p_value": 1.0,
        "statistically_significant": False,
        "actionable": False,
        "sensitivity_score": 0.0,
        "sensitivity_factor": 1.0,
        "vix_direction": "indeterminate",
        "interpretation": "unknown",
        "note": note,
        "data_points": data_points,
    }
    if alignment:
        result.update(alignment)
    return result


def compute_vix_pair_sensitivity(
    vix_candles: list[Candle],
    pair_candles_map: dict[str, list[Candle]],
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> dict[str, Any]:
    """Tính sensitivity score cho từng cặp dựa trên tương quan với VIX.

    Parameters
    ----------
    vix_candles : list[Candle]
        Dữ liệu VIX daily candles.
    pair_candles_map : dict[str, list[Candle]]
        Map symbol → daily candles cho từng cặp cần phân tích.
    lookback_days : int
        Số ngày lookback (mặc định 252, ~1 năm).

    Returns
    -------
    dict
        {
            "meta": {...},
            "pairs": {symbol: {correlation, sensitivity_score, interpretation, note}},
            "warnings": [...],
        }
    """
    warnings: list[str] = []

    if (
        isinstance(lookback_days, bool)
        or not isinstance(lookback_days, int)
        or lookback_days < MIN_LOOKBACK_DAYS
    ):
        return {
            "meta": {
                "generated_at_utc": datetime.now(UTC).isoformat(),
                "lookback_days": lookback_days,
                "status": "invalid_configuration",
                "is_seed": False,
                "schema_version": SENSITIVITY_SCHEMA_VERSION,
                "error": (
                    f"lookback_days must be an integer >= {MIN_LOOKBACK_DAYS}"
                ),
            },
            "pairs": {},
            "warnings": ["Lookback không đủ dài để kiểm chứng VIX sensitivity."],
        }

    vix_closes, invalid_vix_bars = _daily_closes_by_date(vix_candles or [])
    required_closes = MIN_LOOKBACK_DAYS + 1
    if len(vix_closes) < required_closes:
        return {
            "meta": {
                "generated_at_utc": datetime.now(UTC).isoformat(),
                "lookback_days": lookback_days,
                "status": "insufficient_data",
                "is_seed": False,
                "schema_version": SENSITIVITY_SCHEMA_VERSION,
                "error": (
                    f"VIX has {len(vix_closes)} valid daily closes; "
                    f"need >= {required_closes}"
                ),
            },
            "pairs": {},
            "warnings": ["Không đủ dữ liệu VIX hợp lệ để backtest."],
        }

    selected_vix_dates = sorted(vix_closes)[-(lookback_days + 1):]
    data_start = selected_vix_dates[0].isoformat()
    data_end = selected_vix_dates[-1].isoformat()
    if invalid_vix_bars:
        warnings.append(
            f"VIX: loại {invalid_vix_bars} bar có time/close không hợp lệ."
        )

    pairs_result: dict[str, dict[str, Any]] = {}
    validated_pair_count = 0
    actionable_pair_count = 0
    for symbol, pair_candles in sorted(pair_candles_map.items()):
        normalized_symbol = str(symbol).upper()
        pair_closes, invalid_pair_bars = _daily_closes_by_date(pair_candles or [])
        if len(pair_closes) < required_closes:
            warnings.append(
                f"{normalized_symbol}: chỉ có {len(pair_closes)} daily closes hợp lệ "
                f"(cần >= {required_closes}), neutralize."
            )
            pairs_result[normalized_symbol] = _unknown_pair_result(
                "Không đủ dữ liệu để backtest.",
                alignment={"invalid_pair_bars": invalid_pair_bars},
            )
            continue

        vix_aligned, pair_aligned, alignment = _aligned_daily_pct_changes(
            vix_candles,
            pair_candles,
            lookback_days=lookback_days,
        )
        overlap = len(vix_aligned)
        dropped_vix = int(alignment.get("dropped_vix_dates", 0))
        dropped_pair = int(alignment.get("dropped_pair_dates", 0))
        invalid_pair = int(alignment.get("invalid_pair_bars", 0))
        if dropped_vix or dropped_pair or invalid_pair:
            warnings.append(
                f"{normalized_symbol}: align theo ngày loại "
                f"{dropped_vix} ngày chỉ có VIX, {dropped_pair} ngày chỉ có pair; "
                f"{invalid_pair} pair bars không hợp lệ."
            )
        if overlap < MIN_LOOKBACK_DAYS:
            warnings.append(
                f"{normalized_symbol}: chỉ có {overlap} common-date returns "
                f"(cần >= {MIN_LOOKBACK_DAYS}), neutralize."
            )
            pairs_result[normalized_symbol] = _unknown_pair_result(
                f"Quá ít common-date observations ({overlap}).",
                data_points=overlap,
                alignment=alignment,
            )
            continue

        corr = _pearson_correlation(vix_aligned, pair_aligned)
        p_value = _correlation_p_value(corr, overlap)
        significant = p_value <= SIGNIFICANCE_ALPHA
        actionable = significant and abs(corr) > MILD_POSITIVE_THRESHOLD
        effective_corr = corr if actionable else 0.0
        sensitivity = _correlation_to_sensitivity(effective_corr)
        interpretation = _classify_pair(effective_corr)
        note = _build_pair_note(
            normalized_symbol,
            corr,
            interpretation,
            statistically_significant=significant,
            actionable=actionable,
            p_value=p_value,
        )

        validated_pair_count += 1
        actionable_pair_count += int(actionable)
        pairs_result[normalized_symbol] = {
            "correlation": round(corr, 4),
            "p_value": round(p_value, 6),
            "statistically_significant": significant,
            "actionable": actionable,
            "sensitivity_score": round(sensitivity, 1),
            "sensitivity_factor": _correlation_to_sensitivity_factor(effective_corr),
            "vix_direction": _correlation_to_vix_direction(effective_corr),
            "interpretation": interpretation,
            "note": note,
            "data_points": overlap,
            **alignment,
        }

    return {
        "meta": {
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "lookback_days": lookback_days,
            "data_start": data_start,
            "data_end": data_end,
            "vix_source": "yahoo",
            "version": "2.0.0",
            "schema_version": SENSITIVITY_SCHEMA_VERSION,
            "status": "validated" if validated_pair_count else "insufficient_data",
            "is_seed": False,
            "ttl_days": DEFAULT_TTL_DAYS,
            "pair_count": len(pairs_result),
            "validated_pair_count": validated_pair_count,
            "actionable_pair_count": actionable_pair_count,
            "vix_data_points": min(lookback_days, len(selected_vix_dates) - 1),
            "minimum_overlap_days": MIN_LOOKBACK_DAYS,
            "significance_alpha": SIGNIFICANCE_ALPHA,
            "significance_method": "two_sided_fisher_z_normal_approximation",
            "alignment_method": "intersect_close_dates_before_returns",
            "methodology": "pearson_delta_vix_pct_vs_pair_return",
        },
        "pairs": pairs_result,
        "warnings": warnings,
    }


def _build_pair_note(
    symbol: str,
    corr: float,
    interpretation: str,
    *,
    statistically_significant: bool = True,
    actionable: bool = True,
    p_value: float | None = None,
) -> str:
    """Mô tả bằng chứng quan sát, không gán nhân quả cho currency nào."""
    sym = symbol.upper()
    p_text = f", p={p_value:.3f}" if p_value is not None else ""
    if not statistically_significant:
        return (
            f"{sym}: correlation với ΔVIX chưa có ý nghĩa thống kê "
            f"(r={corr:.2f}{p_text}); giữ VIX scoring phẳng."
        )
    if not actionable or interpretation == "neutral":
        return (
            f"{sym}: correlation có ý nghĩa nhưng độ lớn chưa đủ ngưỡng hành động "
            f"(r={corr:.2f}{p_text}); giữ VIX scoring phẳng."
        )
    if corr < 0:
        return (
            f"Dữ liệu cho thấy {sym} thường giảm khi VIX tăng "
            f"(r={corr:.2f}{p_text}); SELL thuận flow, BUY ngược flow. "
            "Correlation không tự xác định nguyên nhân ở base hay quote."
        )
    return (
        f"Dữ liệu cho thấy {sym} thường tăng khi VIX tăng "
        f"(r={corr:.2f}{p_text}); BUY thuận flow, SELL ngược flow. "
        "Correlation không tự xác định nguyên nhân ở base hay quote."
    )


# ---------------------------------------------------------------------------
# Seed sensitivity map
# ---------------------------------------------------------------------------


def generate_seed_sensitivity_map() -> dict[str, Any]:
    """Tạo seed sensitivity map dựa trên currency-level appreciation model.

    Thay vì gán correlation thủ công cho từng cặp, dùng mô hình lan truyền:
    - Mỗi đồng tiền có độ nhạy appreciation riêng với VIX (dương = safe haven,
      tăng giá khi VIX↑)
    - pair_correlation = base_appreciation - quote_appreciation
    - Công thức này tự động xử lý đúng trường hợp như EUR/AUD (AUD ở mẫu số
      nên khi AUD weakens → pair RISE, correlation dương)

    Chỉ dùng để minh họa/sanity-check tooling trước khi có data thực tế. Seed
    luôn bị runtime eligibility gate từ chối và không phải fallback scoring.

    QUAN TRỌNG: Đây là seed dựa trên assumption, cần được backtest thực tế
    xác nhận hoặc điều chỉnh. Xem docstring của module để biết cơ chế
    re-validate.
    """
    # Độ nhạy appreciation của từng đồng tiền với VIX.
    # Dương = safe haven: VIX↑ → đồng tiền TĂNG giá
    # Âm   = risk-on:     VIX↑ → đồng tiền GIẢM giá
    # Giá trị calibrated dựa trên hành vi lịch sử quan sát được.
    CURRENCY_APPRECIATION_ON_VIX_UP: dict[str, float] = {
        "JPY": 0.45,   # Safe haven mạnh nhất
        "CHF": 0.30,   # Safe haven (yếu hơn JPY)
        "USD": 0.10,   # Vừa safe haven vừa reserve — phức tạp
        "EUR": 0.00,   # Trung tính
        "GBP": 0.00,   # Trung tính
        "AUD": -0.35,  # Risk-on
        "NZD": -0.32,  # Risk-on
        "CAD": -0.25,  # Risk-sensitive (dầu + risk)
        "XAU": 0.15,   # Kim loại quý (safe haven nhẹ)
        "XAG": -0.10,  # Vừa quý vừa công nghiệp
        "BTC": -0.22,  # Nhạy risk sentiment
    }

    # Hàm lấy appreciation của 1 currency code (3-letter hoặc XAU/XAG/BTC)
    def _appr(ccy: str) -> float:
        return CURRENCY_APPRECIATION_ON_VIX_UP.get(ccy.upper(), 0.0)

    def _make_note(symbol: str, corr: float) -> str:
        sym = symbol.upper()
        base, quote = sym.split("/") if "/" in sym else (sym[:3], sym[3:])

        base_sens = _appr(base)
        quote_sens = _appr(quote)

        base_label = "safe haven" if base_sens > 0.05 else ("risk-on" if base_sens < -0.05 else "trung tính")
        quote_label = "safe haven" if quote_sens > 0.05 else ("risk-on" if quote_sens < -0.05 else "trung tính")

        if corr < -0.15:
            if quote_sens > 0.05:
                return f"{quote} là {quote_label} — VIX↑ → {quote}↑ → {sym}↓. SELL hưởng lợi khi risk-off."
            if base_sens < -0.05:
                return f"{base} là {base_label} — VIX↑ → {base}↓ → {sym}↓. SELL hưởng lợi khi risk-off."
            return f"{sym} có xu hướng giảm khi VIX tăng (r={corr:.2f}). SELL hưởng lợi."
        if corr > 0.15:
            if quote_sens < -0.05:
                return f"{quote} là {quote_label} — VIX↑ → {quote}↓ → {sym}↑. BUY hưởng lợi khi risk-off."
            if base_sens > 0.05:
                return f"{base} là {base_label} — VIX↑ → {base}↑ → {sym}↑. BUY hưởng lợi khi risk-off."
            return f"{sym} có xu hướng tăng khi VIX tăng (r={corr:.2f}). BUY hưởng lợi."
        return f"{sym} không có tương quan rõ ràng với VIX (r={corr:.2f})."

    # Lấy tất cả symbols từ constants
    try:
        from config.constants import SUPPORTED_SYMBOLS
    except ImportError:
        SUPPORTED_SYMBOLS: list[str] = []  # type: ignore[no-redef]

    pairs: dict[str, dict[str, Any]] = {}
    for symbol in sorted(SUPPORTED_SYMBOLS):
        if "/" not in symbol:
            continue
        base_raw, quote_raw = symbol.split("/")[:2]

        # Giải mã metal/crypto codes
        base = base_raw.strip().upper()
        quote = quote_raw.strip().upper()

        # Tính correlation từ chênh lệch appreciation
        corr = _appr(base) - _appr(quote)
        corr = round(corr, 4)

        sensitivity = _correlation_to_sensitivity(corr)
        factor = _correlation_to_sensitivity_factor(corr)
        vix_dir = _correlation_to_vix_direction(corr)
        interpretation = _classify_pair(corr)
        note = _make_note(symbol, corr)

        pairs[symbol] = {
            "correlation": corr,
            "p_value": None,
            "statistically_significant": False,
            "actionable": False,
            "sensitivity_score": round(sensitivity, 1),
            "sensitivity_factor": factor,
            "vix_direction": vix_dir,
            "interpretation": interpretation,
            "note": note,
            "data_points": 0,  # 0 = seed, chưa có backtest thực tế
        }

    return {
        "meta": {
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "lookback_days": 0,
            "data_start": "N/A (seed data)",
            "data_end": "N/A (seed data)",
            "vix_source": "market_knowledge_seed",
            "version": "1.0.0",
            "schema_version": 1,
            "status": "seed_only",
            "ttl_days": DEFAULT_TTL_DAYS,
            "pair_count": len(pairs),
            "vix_data_points": 0,
            "is_seed": True,
            "methodology": "currency_level_appreciation_propagation",
            "warning": (
                "SEED DATA dựa trên kiến thức thị trường, CHƯA được "
                "backtest xác nhận. Chạy compute_vix_pair_sensitivity() với "
                "data thực tế để thay thế."
            ),
        },
        "pairs": pairs,
        "warnings": ["Seed data — cần backtest thực tế để xác nhận."],
    }


# ---------------------------------------------------------------------------
# Sensitivity map I/O + re-validation
# ---------------------------------------------------------------------------


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


def save_sensitivity_map(
    result: dict[str, Any],
    path: Path | None = None,
) -> Path:
    """Ghi sensitivity map ra file JSON.

    Parameters
    ----------
    result : dict
        Output của compute_vix_pair_sensitivity() hoặc generate_seed_sensitivity_map().
    path : Path | None
        Đường dẫn file đích. None → dùng default.

    Returns
    -------
    Path
        Đường dẫn file đã ghi.
    """
    dest = path if path is not None else _default_sensitivity_path()
    dest.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "meta": result.get("meta", {}),
        "pairs": result.get("pairs", {}),
    }

    temp_dest = dest.with_name(f"{dest.name}.tmp")
    with open(temp_dest, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    temp_dest.replace(dest)

    logger.info("VIX sensitivity map saved to %s (%d pairs)", dest, len(payload.get("pairs", {})))
    return dest


def load_sensitivity_map(
    path: Path | None = None,
    *,
    warn_stale: bool = True,
) -> dict[str, Any] | None:
    """Đọc sensitivity map từ disk.

    Parameters
    ----------
    path : Path | None
        Đường dẫn tới file JSON. None → dùng default.
    warn_stale : bool
        Nếu True và map đã hết hạn → log warning.

    Returns
    -------
    dict | None
        Sensitivity map hoặc None nếu file không tồn tại/lỗi.
    """
    src = path if path is not None else _default_sensitivity_path()

    if not src.exists():
        logger.info("VIX sensitivity map not found at %s", src)
        return None

    try:
        with open(src, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load VIX sensitivity map: %s", exc)
        return None

    if not isinstance(data, dict):
        logger.warning("VIX sensitivity map is not a dict")
        return None

    if not isinstance(data.get("pairs"), dict):
        logger.warning("VIX sensitivity map missing 'pairs' key")
        return None

    if warn_stale and is_sensitivity_map_stale(data):
        meta = data.get("meta", {})
        generated = meta.get("generated_at_utc", "unknown")
        ttl = meta.get("ttl_days", DEFAULT_TTL_DAYS)
        logger.warning(
            "VIX sensitivity map is STALE (generated %s, TTL %d days). "
            "Re-run scripts/run_vix_pair_backtest.py before enabling pair-aware scoring.",
            generated, ttl,
        )

    return data


def get_vix_sensitivity_map(
    path: Path | None = None,
    *,
    warn_stale: bool = True,
    auto_generate_seed: bool = False,
) -> dict[str, Any] | None:
    """Đọc sensitivity map; chỉ tạo seed khi caller yêu cầu tường minh.

    Parameters
    ----------
    path : Path | None
        Đường dẫn tới file JSON. None → dùng default.
    warn_stale : bool
        Nếu True → log warning khi map hết hạn.
    auto_generate_seed : bool
        Nếu True và không tìm thấy file → tạo + lưu seed để chẩn đoán. Seed
        vẫn không đủ điều kiện production scoring.

    Returns
    -------
    dict | None
        Sensitivity map hoặc None nếu không có data và auto_generate_seed=False.
    """
    # Thử load từ file
    result = load_sensitivity_map(path, warn_stale=warn_stale)
    if result is not None:
        return result

    # Fallback: generate seed
    if auto_generate_seed:
        logger.info(
            "Generating seed VIX sensitivity map (market knowledge based). "
            "Run compute_vix_pair_sensitivity() with real data to replace."
        )
        seed = generate_seed_sensitivity_map()
        try:
            save_sensitivity_map(seed, path)
        except OSError:
            pass
        return seed

    return None


# ---------------------------------------------------------------------------
# Convenience: sensitivity lookup
# ---------------------------------------------------------------------------


def lookup_pair_sensitivity(
    symbol: str,
    sensitivity_map: dict[str, Any] | None,
) -> dict[str, Any]:
    """Tra cứu sensitivity data cho một cặp.

    Parameters
    ----------
    symbol : str
        Symbol cần tra (VD: "EUR/USD", "USD/JPY").
    sensitivity_map : dict | None
        Map đã load từ get_vix_sensitivity_map().

    Returns
    -------
    dict
        {"correlation": float, "sensitivity_score": float, "interpretation": str, "note": str}
        Nếu không tìm thấy → giá trị mặc định neutral.
    """
    default = {
        "correlation": 0.0,
        "sensitivity_score": 0.0,
        "sensitivity_factor": 1.0,
        "vix_direction": "indeterminate",
        "interpretation": "neutral",
        "note": "Chưa có dữ liệu sensitivity cho cặp này.",
        "data_points": 0,
    }

    if sensitivity_map is None:
        return default

    pairs = sensitivity_map.get("pairs")
    if not isinstance(pairs, dict):
        return default

    pair_data = pairs.get(symbol.upper())
    if not isinstance(pair_data, dict):
        return default

    return {
        "correlation": float(pair_data.get("correlation", 0.0)),
        "sensitivity_score": float(pair_data.get("sensitivity_score", 0.0)),
        "sensitivity_factor": float(pair_data.get("sensitivity_factor", 1.0)),
        "vix_direction": str(pair_data.get("vix_direction", "indeterminate")),
        "interpretation": str(pair_data.get("interpretation", "neutral")),
        "note": str(pair_data.get("note", "")),
        "data_points": int(pair_data.get("data_points", 0)),
    }
