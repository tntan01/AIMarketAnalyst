"""Bước 7 — VIX Pair Sensitivity Backtest Engine.

Tính tương quan giữa thay đổi VIX hàng ngày và returns của từng cặp tiền
để xây dựng sensitivity mapping thay cho hệ số phạt cào bằng hiện tại.

Cung cấp:
- compute_vix_pair_sensitivity(): tính Pearson correlation ΔVIX% vs pair returns
- get_vix_sensitivity_map(): đọc map từ disk
- is_sensitivity_map_stale(): kiểm tra TTL
- generate_seed_sensitivity_map(): tạo seed map từ kiến thức thị trường
  (dùng làm fallback trước khi có backtest data thực tế)
"""

from __future__ import annotations

import json
import logging
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from config.paths import app_data_dir
from core.market_models import Candle

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Ngưỡng correlation để phân loại
SAFE_HAVEN_THRESHOLD = -0.25       # correlation < -0.25 → safe haven
RISK_SENSITIVE_THRESHOLD = 0.25    # correlation > +0.25 → risk sensitive
MILD_SAFE_HAVEN_THRESHOLD = -0.15
MILD_RISK_SENSITIVE_THRESHOLD = 0.15

# Dải sensitivity score
SENSITIVITY_MIN = -5.0
SENSITIVITY_MAX = 5.0

# Lookback mặc định: ~1 năm giao dịch
DEFAULT_LOOKBACK_DAYS = 252

# Số ngày tối thiểu để backtest có ý nghĩa
MIN_LOOKBACK_DAYS = 20

# TTL mặc định cho sensitivity map: 90 ngày
DEFAULT_TTL_DAYS = 90

# Đường dẫn mặc định tới sensitivity file
DEFAULT_SENSITIVITY_PATH: Path | None = None


def _default_sensitivity_path() -> Path:
    """Đường dẫn mặc định tới file sensitivity map trong data/."""
    global DEFAULT_SENSITIVITY_PATH
    if DEFAULT_SENSITIVITY_PATH is not None:
        return DEFAULT_SENSITIVITY_PATH
    # Project data dir — app_data_dir() trả về ./data trong project
    path = app_data_dir() / "vix_pair_sensitivity.json"
    DEFAULT_SENSITIVITY_PATH = path
    return path


# ---------------------------------------------------------------------------
# Backtest computation
# ---------------------------------------------------------------------------


def _daily_pct_changes(candles: list[Candle]) -> list[float]:
    """Tính chuỗi phần trăm thay đổi ngày-qua-ngày từ list candles.

    Returns:
        list[float]: len = len(candles) - 1, mỗi phần tử là (close[t] - close[t-1]) / close[t-1] * 100
    """
    changes: list[float] = []
    for i in range(1, len(candles)):
        prev = candles[i - 1].close
        curr = candles[i].close
        if prev <= 0 or curr <= 0:
            continue
        changes.append((curr - prev) / prev * 100.0)
    return changes


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


def _correlation_to_sensitivity(corr: float) -> float:
    """Quy đổi Pearson correlation → sensitivity score trong [-5, +5].

    sensitivity_score mang dấu của correlation:
    - correlation < 0: VIX↑ → pair↓ (safe haven behavior)
    - correlation > 0: VIX↑ → pair↑ hoặc VIX↓ → pair↓ (risk-on behavior)

    Quy đổi phi tuyến: dùng correlation^2 để khuếch đại tín hiệu mạnh.
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

    0.0 = VIX fully explains pair movement (|corr| ≈ 1.0) → minimal penalty
    1.0 = VIX is noise (|corr| ≈ 0.0)       → full penalty

    Uses piecewise mapping:
    - |corr| >= 0.80 → factor = 0.00 (fully explained)
    - |corr| <= 0.15 → factor = 1.00 (pure noise)
    - Linear between: factor = 1.0 - (|corr| - 0.15) / 0.65
    """
    abs_corr = abs(corr)
    if abs_corr >= 0.80:
        return 0.0
    if abs_corr <= 0.15:
        return 1.0
    return round(1.0 - (abs_corr - 0.15) / 0.65, 2)


def _classify_pair(corr: float) -> str:
    """Phân loại cặp dựa trên correlation với VIX."""
    if corr < SAFE_HAVEN_THRESHOLD:
        return "safe_haven"
    if corr > RISK_SENSITIVE_THRESHOLD:
        return "risk_sensitive"
    if corr < MILD_SAFE_HAVEN_THRESHOLD:
        return "mild_safe_haven"
    if corr > MILD_RISK_SENSITIVE_THRESHOLD:
        return "mild_risk_sensitive"
    return "neutral"


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
        Dữ liệu VIX daily candles. Cần ít nhất MIN_LOOKBACK_DAYS candles.
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

    # Validate VIX data
    if not vix_candles or len(vix_candles) < MIN_LOOKBACK_DAYS:
        return {
            "meta": {
                "generated_at_utc": datetime.now(UTC).isoformat(),
                "lookback_days": lookback_days,
                "status": "insufficient_data",
                "error": f"VIX data has {len(vix_candles) if vix_candles else 0} candles, need >= {MIN_LOOKBACK_DAYS}",
            },
            "pairs": {},
            "warnings": ["Không đủ dữ liệu VIX để backtest."],
        }

    # Cắt về lookback_days gần nhất
    effective_candles = vix_candles[-lookback_days:] if len(vix_candles) > lookback_days else vix_candles
    if len(effective_candles) < MIN_LOOKBACK_DAYS:
        warnings.append(
            f"Chỉ có {len(effective_candles)} ngày dữ liệu VIX sau khi cắt lookback "
            f"(cần >= {MIN_LOOKBACK_DAYS}). Kết quả có thể không ổn định."
        )

    # Tính chuỗi ΔVIX%
    vix_changes = _daily_pct_changes(effective_candles)
    if len(vix_changes) < MIN_LOOKBACK_DAYS - 1:
        return {
            "meta": {
                "generated_at_utc": datetime.now(UTC).isoformat(),
                "lookback_days": lookback_days,
                "status": "insufficient_data",
                "error": f"Only {len(vix_changes)} valid daily changes from {len(effective_candles)} candles",
            },
            "pairs": {},
            "warnings": warnings + ["Không đủ dữ liệu VIX sau khi tính daily changes."],
        }

    # Xác định data range
    try:
        data_start = effective_candles[0].time.strftime("%Y-%m-%d")
        data_end = effective_candles[-1].time.strftime("%Y-%m-%d")
    except (AttributeError, IndexError):
        data_start = "unknown"
        data_end = "unknown"

    # Tính correlation cho từng cặp
    pairs_result: dict[str, dict[str, Any]] = {}
    for symbol, pair_candles in sorted(pair_candles_map.items()):
        if not pair_candles or len(pair_candles) < MIN_LOOKBACK_DAYS:
            warnings.append(
                f"{symbol}: không đủ dữ liệu candles ({len(pair_candles) if pair_candles else 0}), bỏ qua."
            )
            pairs_result[symbol] = {
                "correlation": 0.0,
                "sensitivity_score": 0.0,
                "sensitivity_factor": 1.0,
                "vix_direction": "indeterminate",
                "interpretation": "unknown",
                "note": "Không đủ dữ liệu để backtest.",
                "data_points": 0,
            }
            continue

        # Cắt về cùng độ dài với VIX
        pair_effective = pair_candles[-lookback_days:] if len(pair_candles) > lookback_days else pair_candles
        pair_returns = _daily_pct_changes(pair_effective)

        # Align 2 chuỗi về cùng độ dài (lấy min)
        min_len = min(len(vix_changes), len(pair_returns))
        if min_len < 10:
            warnings.append(
                f"{symbol}: chỉ có {min_len} điểm dữ liệu aligned, bỏ qua."
            )
            pairs_result[symbol] = {
                "correlation": 0.0,
                "sensitivity_score": 0.0,
                "sensitivity_factor": 1.0,
                "vix_direction": "indeterminate",
                "interpretation": "unknown",
                "note": f"Quá ít điểm dữ liệu ({min_len}).",
                "data_points": min_len,
            }
            continue

        vix_aligned = vix_changes[-min_len:]
        pair_aligned = pair_returns[-min_len:]

        corr = _pearson_correlation(vix_aligned, pair_aligned)
        sensitivity = _correlation_to_sensitivity(corr)
        interpretation = _classify_pair(corr)

        # Tạo note mô tả
        note = _build_pair_note(symbol, corr, interpretation)

        pairs_result[symbol] = {
            "correlation": round(corr, 4),
            "sensitivity_score": round(sensitivity, 1),
            "sensitivity_factor": _correlation_to_sensitivity_factor(corr),
            "vix_direction": _correlation_to_vix_direction(corr),
            "interpretation": interpretation,
            "note": note,
            "data_points": min_len,
        }

    return {
        "meta": {
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "lookback_days": lookback_days,
            "data_start": data_start,
            "data_end": data_end,
            "vix_source": "yahoo",
            "version": "1.0.0",
            "ttl_days": DEFAULT_TTL_DAYS,
            "pair_count": len(pairs_result),
            "vix_data_points": len(vix_changes),
        },
        "pairs": pairs_result,
        "warnings": warnings,
    }


def _build_pair_note(symbol: str, corr: float, interpretation: str) -> str:
    """Tạo human-readable note cho một cặp."""
    sym = symbol.upper()

    if "JPY" in sym:
        base = sym.split("/")[0] if "/" in sym else sym[:3]
        if corr < -0.2:
            return (
                f"JPY là safe haven — VIX tăng → JPY mạnh → {sym} giảm. "
                f"SELL hưởng lợi khi risk-off."
            )
        else:
            return (
                f"Mặc dù JPY thường là safe haven, dữ liệu gần đây ({corr:.2f}) "
                f"không thể hiện rõ hành vi này. Có thể do BOJ phân kỳ chính sách."
            )

    if "AUD" in sym and interpretation == "risk_sensitive":
        return (
            f"AUD là risk-on currency — VIX tăng → AUD yếu → {sym} giảm. "
            f"SELL hưởng lợi khi risk-off, BUY bị phạt nặng hơn."
        )

    if "NZD" in sym and interpretation == "risk_sensitive":
        return (
            f"NZD là risk-on currency — VIX tăng → NZD yếu → {sym} giảm. "
            f"SELL hưởng lợi khi risk-off, BUY bị phạt nặng hơn."
        )

    if "CAD" in sym and interpretation == "risk_sensitive":
        return (
            f"CAD nhạy với giá dầu và risk sentiment — VIX tăng có thể gây áp lực "
            f"lên {sym}. SELL hưởng lợi nhẹ khi risk-off."
        )

    if interpretation == "neutral":
        return f"{sym} không có tương quan rõ ràng với VIX (r={corr:.2f})."

    if interpretation == "safe_haven":
        return f"{sym} thể hiện hành vi safe haven — VIX tăng → {sym} giảm."

    if interpretation == "mild_safe_haven":
        return f"{sym} có xu hướng safe haven nhẹ — VIX tăng → {sym} giảm nhẹ."

    if interpretation == "mild_risk_sensitive":
        return f"{sym} nhạy cảm nhẹ với risk-off — VIX tăng → {sym} có xu hướng giảm."

    return f"{sym}: correlation={corr:.2f} với ΔVIX."


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

    Dùng làm fallback trước khi có backtest data thực tế. Các giá trị được
    calibrate dựa trên hành vi lịch sử đã biết của từng nhóm tiền tệ.

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
        return age_days > float(ttl_days)
    except (ValueError, TypeError, OverflowError):
        return True  # fail-safe


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

    with open(dest, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

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

    if "pairs" not in data:
        logger.warning("VIX sensitivity map missing 'pairs' key")
        return None

    if warn_stale and is_sensitivity_map_stale(data):
        meta = data.get("meta", {})
        generated = meta.get("generated_at_utc", "unknown")
        ttl = meta.get("ttl_days", DEFAULT_TTL_DAYS)
        logger.warning(
            "VIX sensitivity map is STALE (generated %s, TTL %d days). "
            "Consider re-running backtest. "
            "Journal from Bước 6 will catch systematic scoring errors.",
            generated, ttl,
        )

    return data


def get_vix_sensitivity_map(
    path: Path | None = None,
    *,
    warn_stale: bool = True,
    auto_generate_seed: bool = True,
) -> dict[str, Any] | None:
    """Đọc sensitivity map, tự động fallback về seed nếu cần.

    Đây là hàm chính để pipeline gọi.

    Parameters
    ----------
    path : Path | None
        Đường dẫn tới file JSON. None → dùng default.
    warn_stale : bool
        Nếu True → log warning khi map hết hạn.
    auto_generate_seed : bool
        Nếu True và không tìm thấy file → tự động tạo + lưu seed map.

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
