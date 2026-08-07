from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from core.market_models import Candle

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# VIX sensitivity map — lazy-loaded from data/vix_pair_sensitivity.json
# ---------------------------------------------------------------------------

_VIX_SENSITIVITY_CACHE: dict[str, dict[str, Any]] | None = None
_VIX_SENSITIVITY_LOADED: bool = False


def _load_vix_sensitivity() -> dict[str, dict[str, Any]]:
    """Load pair→VIX sensitivity mapping from data/vix_pair_sensitivity.json.

    Returns empty dict if the file is missing or malformed (fail-open:
    missing data means flat scoring, preserving current behavior).
    Cached in module-level variable after first load.
    """
    global _VIX_SENSITIVITY_CACHE, _VIX_SENSITIVITY_LOADED
    if _VIX_SENSITIVITY_LOADED:
        return _VIX_SENSITIVITY_CACHE or {}

    _VIX_SENSITIVITY_LOADED = True

    # Try multiple paths: project-relative, then app-data
    candidates = [
        Path(__file__).resolve().parents[1] / "data" / "vix_pair_sensitivity.json",
    ]
    try:
        from config.paths import app_data_dir
        candidates.append(app_data_dir() / "vix_pair_sensitivity.json")
    except Exception:
        pass

    for path in candidates:
        try:
            data = json.loads(path.read_text("utf-8"))
            if isinstance(data, dict) and "pairs" in data:
                _VIX_SENSITIVITY_CACHE = data["pairs"]
                logger.info(
                    "VIX sensitivity map loaded from %s (%d pairs)",
                    path, len(_VIX_SENSITIVITY_CACHE),
                )
                # Log warning if seed data
                meta = data.get("meta", {})
                if isinstance(meta, dict) and meta.get("is_seed") is True:
                    logger.warning(
                        "VIX sensitivity map is SEED DATA (market knowledge based). "
                        "Run backtest with real data to validate."
                    )
                return _VIX_SENSITIVITY_CACHE
        except (OSError, json.JSONDecodeError, KeyError):
            continue

    logger.info("No VIX sensitivity map found — using flat scoring (current behavior).")
    _VIX_SENSITIVITY_CACHE = {}
    return {}


def _reset_vix_sensitivity_cache() -> None:
    """Reset sensitivity cache (for testing)."""
    global _VIX_SENSITIVITY_CACHE, _VIX_SENSITIVITY_LOADED
    _VIX_SENSITIVITY_CACHE = None
    _VIX_SENSITIVITY_LOADED = False


def _dxy_direction(candles: list[Candle] | None) -> str | None:
    if not candles or len(candles) < 5:
        return None
    first_close = candles[0].close
    last_close = candles[-1].close
    if first_close <= 0:
        return None
    change_pct = (last_close - first_close) / first_close * 100
    if change_pct > 0.3:
        return "up"
    if change_pct < -0.3:
        return "down"
    return "flat"


def _us10y_direction(candles: list[Candle] | None) -> str | None:
    if not candles or len(candles) < 5:
        return None
    first_close = candles[0].close
    last_close = candles[-1].close
    if first_close <= 0:
        return None
    change_pct = (last_close - first_close) / first_close * 100
    if change_pct > 0.5:
        return "up"
    if change_pct < -0.5:
        return "down"
    return "flat"


def check_dxy_alignment(symbol: str, side: str, dxy_candles: list[Candle] | None) -> dict[str, Any]:
    dxy_dir = _dxy_direction(dxy_candles)
    base, _, quote = symbol.partition("/")
    if not quote:
        return {"warning": None, "alignment": "neutral", "dxy_direction": dxy_dir}

    if base == "USD":
        usd_bullish = side == "buy"
    elif quote == "USD":
        usd_bullish = side == "sell"
    else:
        return {"warning": None, "alignment": "neutral", "dxy_direction": dxy_dir}

    if dxy_dir is None:
        return {
            "warning": None,
            "alignment": "neutral",
            "dxy_direction": None,
            "detail": "Không có dữ liệu DXY để kiểm tra tương quan.",
        }

    if (usd_bullish and dxy_dir == "up") or (not usd_bullish and dxy_dir == "down"):
        return {
            "warning": None,
            "alignment": "supports",
            "dxy_direction": dxy_dir,
            "detail": f"DXY {dxy_dir} — thuận với lệnh {side.upper()} {symbol}.",
        }

    return {
        "warning": f"DXY đang đi ngược hướng với lệnh {side.upper()} {symbol}.",
        "alignment": "against",
        "dxy_direction": dxy_dir,
        "detail": f"DXY {dxy_dir} — ngược hướng với lệnh {side.upper()} {symbol}. Cảnh báo phân kỳ DXY.",
    }


def _us2y_direction(candles: list[Candle] | None) -> str | None:
    if not candles or len(candles) < 5:
        return None
    first_close = candles[0].close
    last_close = candles[-1].close
    if first_close <= 0:
        return None
    change_pct = (last_close - first_close) / first_close * 100
    if change_pct > 0.5:
        return "up"
    if change_pct < -0.5:
        return "down"
    return "flat"


def check_yield_spread(
    symbol: str,
    side: str,
    us10y_candles: list[Candle] | None,
) -> dict[str, Any]:
    direction = _us10y_direction(us10y_candles)
    if direction is None:
        return {"warning": None, "alignment": "neutral", "us10y_direction": None}

    if symbol in {"XAU/USD", "XAG/USD"}:
        if side == "buy" and direction == "down":
            return {
                "warning": None,
                "alignment": "supports",
                "us10y_direction": direction,
                "detail": f"US10Y {direction} — lợi suất giảm hỗ trợ vàng.",
            }
        if side == "sell" and direction == "up":
            return {
                "warning": None,
                "alignment": "supports",
                "us10y_direction": direction,
                "detail": f"US10Y {direction} — lợi suất tăng thuận với bán vàng.",
            }
        if side == "buy" and direction == "up":
            return {
                "warning": f"US10Y đang tăng — lợi suất cao gây áp lực lên vàng, cảnh báo cho lệnh BUY {symbol}.",
                "alignment": "against",
                "us10y_direction": direction,
                "detail": f"US10Y {direction} — lợi suất tăng thường gây sức ép lên vàng.",
            }
        if side == "sell" and direction == "down":
            return {
                "warning": f"US10Y đang giảm — lợi suất thấp hỗ trợ vàng, cảnh báo cho lệnh SELL {symbol}.",
                "alignment": "against",
                "us10y_direction": direction,
                "detail": f"US10Y {direction} — lợi suất giảm thường hỗ trợ vàng.",
            }

    if "JPY" in symbol:
        if direction == "up":
            return {
                "warning": None,
                "alignment": "supports",
                "us10y_direction": direction,
                "detail": f"US10Y {direction} — chênh lệch lợi suất US-JPY mở rộng, thuận cho JPY yếu.",
            }
        return {
            "warning": f"US10Y đang giảm — chênh lệch lợi suất thu hẹp, JPY có thể mạnh lên.",
            "alignment": "against",
            "us10y_direction": direction,
            "detail": f"US10Y {direction} — chênh lệch lợi suất thu hẹp, JPY có thể mạnh lên.",
        }

    return {"warning": None, "alignment": "neutral", "us10y_direction": direction}


def check_us2y_spread(
    symbol: str,
    side: str,
    us2y_candles: list[Candle] | None,
) -> dict[str, Any]:
    direction = _us2y_direction(us2y_candles)
    if direction is None:
        return {"warning": None, "alignment": "neutral", "us2y_direction": None}

    if symbol in {"XAU/USD", "XAG/USD"}:
        if side == "buy" and direction == "down":
            return {
                "warning": None,
                "alignment": "supports",
                "us2y_direction": direction,
                "detail": f"US2Y {direction} — lợi suất ngắn hạn giảm hỗ trợ vàng.",
            }
        if side == "sell" and direction == "up":
            return {
                "warning": None,
                "alignment": "supports",
                "us2y_direction": direction,
                "detail": f"US2Y {direction} — lợi suất ngắn hạn tăng thuận với bán vàng.",
            }
        if side == "buy" and direction == "up":
            return {
                "warning": f"US2Y đang tăng — lợi suất ngắn hạn cao gây áp lực lên vàng, cảnh báo cho lệnh BUY {symbol}.",
                "alignment": "against",
                "us2y_direction": direction,
                "detail": f"US2Y {direction} — lợi suất ngắn hạn tăng thường gây sức ép lên vàng.",
            }
        if side == "sell" and direction == "down":
            return {
                "warning": f"US2Y đang giảm — lợi suất ngắn hạn thấp hỗ trợ vàng, cảnh báo cho lệnh SELL {symbol}.",
                "alignment": "against",
                "us2y_direction": direction,
                "detail": f"US2Y {direction} — lợi suất ngắn hạn giảm thường hỗ trợ vàng.",
            }

    if "JPY" in symbol:
        if direction == "up":
            return {
                "warning": None,
                "alignment": "supports",
                "us2y_direction": direction,
                "detail": f"US2Y {direction} — lợi suất ngắn hạn US tăng, chênh lệch với JPY mở rộng, thuận cho JPY yếu.",
            }
        return {
            "warning": f"US2Y đang giảm — lợi suất ngắn hạn US giảm, JPY có thể mạnh lên.",
            "alignment": "against",
            "us2y_direction": direction,
            "detail": f"US2Y {direction} — chênh lệch lợi suất ngắn hạn thu hẹp, JPY có thể mạnh lên.",
        }

    return {"warning": None, "alignment": "neutral", "us2y_direction": direction}


_COMMODITY_MAP: dict[str, str] = {
    "AUD": "AUD nhạy với quặng sắt và dữ liệu Trung Quốc.",
    "NZD": "NZD nhạy với giá sữa (Global Dairy Trade) và dữ liệu Trung Quốc.",
    "CAD": "CAD nhạy với giá dầu WTI.",
    "XAU": "Vàng nhạy với lợi suất thực, DXY và rủi ro địa chính trị.",
    "XAG": "Bạc nhạy với lợi suất thực, DXY, gold/silver ratio và nhu cầu công nghiệp.",
    "BTC": "BTC nhạy với thanh khoản USD, risk sentiment, ETF flow và catalyst crypto.",
}


def check_commodity(symbol: str, side: str) -> dict[str, Any]:
    base, _, quote = symbol.partition("/")
    notes: list[str] = []
    for currency in (base, quote):
        if currency in _COMMODITY_MAP:
            notes.append(_COMMODITY_MAP[currency])
    if notes:
        return {
            "warning": None,
            "alignment": "neutral",
            "detail": " | ".join(notes),
        }
    return {"warning": None, "alignment": "neutral", "detail": None}


def check_vix_context(vix_candles: list[Candle] | None) -> dict[str, Any]:
    if not vix_candles or len(vix_candles) < 1:
        return {"warning": None, "vix_level": None, "alignment": "neutral"}
    current = vix_candles[-1].close
    if current <= 0:
        return {"warning": None, "vix_level": None, "alignment": "neutral"}
    if current > 25:
        return {
            "warning": f"VIX cao ({current:.1f} > 25) — thị trường risk-off, ưu tiên sell hoặc đứng ngoài.",
            "vix_level": current,
            "alignment": "against",
            "detail": f"VIX {current:.1f} — biến động cao, thị trường sợ hãi. Cân nhắc giảm lot hoặc đứng ngoài.",
        }
    if current > 20:
        return {
            "warning": f"VIX trung bình-cao ({current:.1f}, 20-25) — thận trọng.",
            "vix_level": current,
            "alignment": "neutral",
            "detail": f"VIX {current:.1f} — biến động trên trung bình, nên giảm kỳ vọng R:R.",
        }
    if current < 15:
        return {
            "warning": None,
            "vix_level": current,
            "alignment": "supports",
            "detail": f"VIX thấp ({current:.1f} < 15) — thị trường ổn định, thuận lợi cho swing trade.",
        }
    return {
        "warning": None,
        "vix_level": current,
        "alignment": "neutral",
        "detail": f"VIX {current:.1f} — mức bình thường.",
    }


def get_correlation_warnings(
    symbol: str,
    side: str,
    dxy_candles: list[Candle] | None = None,
    us10y_candles: list[Candle] | None = None,
    us2y_candles: list[Candle] | None = None,
    vix_candles: list[Candle] | None = None,
) -> list[str]:
    warnings: list[str] = []
    dxy = check_dxy_alignment(symbol, side, dxy_candles)
    if dxy.get("warning"):
        warnings.append(str(dxy["warning"]))

    us10y = check_yield_spread(symbol, side, us10y_candles)
    if us10y.get("warning"):
        warnings.append(str(us10y["warning"]))

    us2y = check_us2y_spread(symbol, side, us2y_candles)
    if us2y.get("warning"):
        warnings.append(str(us2y["warning"]))

    vix = check_vix_context(vix_candles)
    if vix.get("warning"):
        warnings.append(str(vix["warning"]))

    return warnings


def summarize_correlation_context(
    symbol: str,
    side: str,
    dxy_candles: list[Candle] | None = None,
    us10y_candles: list[Candle] | None = None,
    us2y_candles: list[Candle] | None = None,
    vix_candles: list[Candle] | None = None,
) -> dict[str, Any]:
    dxy = check_dxy_alignment(symbol, side, dxy_candles)
    us10y = check_yield_spread(symbol, side, us10y_candles)
    us2y = check_us2y_spread(symbol, side, us2y_candles)
    commodity = check_commodity(symbol, side)
    vix = check_vix_context(vix_candles)

    context_lines: list[str] = []
    if dxy.get("detail"):
        context_lines.append(f"DXY: {dxy['detail']}")
    if us10y.get("detail"):
        context_lines.append(f"US10Y: {us10y['detail']}")
    if us2y.get("detail"):
        context_lines.append(f"US2Y: {us2y['detail']}")
    if commodity.get("detail"):
        context_lines.append(f"Commodity: {commodity['detail']}")
    if vix.get("detail"):
        context_lines.append(f"VIX: {vix['detail']}")

    return {
        "dxy_alignment": dxy,
        "us10y_spread": us10y,
        "us2y_spread": us2y,
        "commodity_note": commodity,
        "vix_context": vix,
        "summary_lines": context_lines,
        "warnings": [
            str(w) for w in (dxy.get("warning"), us10y.get("warning"), us2y.get("warning"), vix.get("warning")) if w
        ],
    }


def _dxy_score(side: str, symbol: str, dxy_candles: list | None) -> float:
    """
    DXY adjustment cho USD pairs.
    DXY tăng → USD mạnh → thuận BUY USD, SELL XXX/USD.
    DXY giảm → USD yếu → thuận SELL USD, BUY XXX/USD.

    Mức điều chỉnh:
      - Cùng hướng, DXY move nhẹ (<0.3%): +1
      - Cùng hướng, DXY move rõ (0.3-0.5%): +2
      - Cùng hướng, DXY move mạnh (>0.5%): +3
      - Ngược hướng, DXY move nhẹ: -2
      - Ngược hướng, DXY move rõ: -3
      - Ngược hướng, DXY move mạnh: -5
      - Không có USD hoặc không đủ data: 0
    """
    if not dxy_candles or len(dxy_candles) < 2:
        return 0.0

    if "USD" not in symbol.upper():
        return 0.0

    current = dxy_candles[-1].close
    prev = dxy_candles[-2].close
    if prev <= 0:
        return 0.0

    dxy_up = current > prev
    dxy_change = abs(current - prev) / prev

    # BUY USD/XXX hoặc SELL XXX/USD = long USD
    buy_usd = (symbol.upper().startswith("USD") and side == "buy") or \
              (symbol.upper().endswith("/USD") and side == "sell")

    aligned = (buy_usd and dxy_up) or (not buy_usd and not dxy_up)

    # Dead zone (<0.1%): biến động chỉ là nhiễu, không thưởng không phạt
    if dxy_change < 0.001:
        return 0.0

    # Tính magnitude
    if dxy_change > 0.005:
        mag = 3.0
    elif dxy_change > 0.003:
        mag = 2.0
    else:
        mag = 1.0

    if aligned:
        return mag
    else:
        # Ngược hướng: phạt nặng hơn
        if dxy_change > 0.005:
            return -5.0
        elif dxy_change > 0.003:
            return -3.0
        else:
            return -2.0


def _vix_score(symbol: str, side: str, vix_candles: list | None) -> float:
    """VIX adjustment CÓ NHẬN THỨC CẶP TIỀN (Bước 7).

    Dựa trên backtest correlation giữa ΔVIX và pair returns để điều chỉnh
    mức phạt/thưởng theo độ nhạy thực tế của từng cặp với risk-off.

    Logic:
    1. Base penalty từ mức VIX tuyệt đối (giữ nguyên threshold cũ)
    2. Điều chỉnh theo sensitivity_factor từ data:
       - factor ~0: VIX giải thích tốt chuyển động của cặp → giảm phạt
       - factor ~1: VIX không liên quan → giữ nguyên phạt
    3. Điều chỉnh theo hướng giao dịch (side-aware):
       - Nếu giao dịch THUẬN với VIX-driven flow → giảm phạt mạnh
       - Nếu giao dịch NGƯỢC → giữ phạt gần như nguyên

    Fallback: nếu không có sensitivity data → flat scoring (giữ nguyên behavior cũ).

    Parameters
    ----------
    symbol : str
        Cặp tiền (EUR/USD, USD/JPY, ...).
    side : str
        Hướng giao dịch ("buy" hoặc "sell").
    vix_candles : list | None
        VIX daily candles.
    """
    if not vix_candles or len(vix_candles) < 1:
        return 0.0

    current = vix_candles[-1].close
    if current <= 0:
        return 0.0

    # ---- Base penalty từ mức VIX tuyệt đối (giữ nguyên) ----
    if current > 25:
        base_penalty = -5.0
    elif current > 20:
        base_penalty = -2.0
    elif current < 15:
        base_penalty = 2.0   # bonus — low vol always helps
    else:
        base_penalty = 0.0

    if base_penalty == 0.0:
        return 0.0

    # VIX bonus (< 15) không bị điều chỉnh — low vol luôn tốt cho mọi cặp
    if base_penalty > 0:
        return base_penalty

    # ---- Pair-aware modulation (chỉ áp dụng cho penalty, không cho bonus) ----
    sensitivity_data = _load_vix_sensitivity()
    pair_data = sensitivity_data.get(symbol.upper())

    if pair_data is None:
        return base_penalty  # unknown pair → flat scoring

    corr = float(pair_data.get("correlation", 0.0))
    factor = float(pair_data.get("sensitivity_factor", 1.0))
    vix_dir = str(pair_data.get("vix_direction", "indeterminate"))

    # sensitivity_factor: 0 = VIX fully explains movement → no penalty
    #                     1 = VIX is noise → full penalty
    factor = max(0.0, min(1.0, factor))

    # Side-aware adjustment:
    # - falls_on_vix_up (corr < -0.15): pair↓ when VIX↑ → SELL is with the flow
    # - rises_on_vix_up  (corr > +0.15): pair↑ when VIX↑ → BUY is with the flow
    # - indeterminate: no clear direction → use factor as-is
    trade_aligned = False
    if vix_dir == "falls_on_vix_up" and side == "sell":
        trade_aligned = True
    elif vix_dir == "rises_on_vix_up" and side == "buy":
        trade_aligned = True

    if trade_aligned:
        # Trading WITH the VIX-driven flow → reduce penalty significantly
        # Stronger correlation → more reduction
        effective_factor = factor * 0.3  # 70% reduction for aligned trades
    else:
        # Trading AGAINST the flow → keep most of the penalty
        # Floor at 0.2 so even uncorrelated pairs get some penalty
        effective_factor = factor * 0.8 + 0.2

    adjusted = base_penalty * effective_factor
    return round(adjusted, 1)


def _us10y_score(side: str, symbol: str, us10y_candles: list | None) -> float:
    """
    US10Y 3 tầng cho XAU và JPY pairs.

    Tầng 1 - Directional (60%): Yield tăng → USD mạnh
      - BUY USD/XXX + yield up: +2
      - SELL USD/XXX + yield down: +2
      - Ngược lại: -2 đến -3

    Tầng 2 - Absolute Level (25%): Yield > 5.5% → debt concern
      - BUY USD khi yield > 5.5%: -2 (rủi ro USD dài hạn)
      - Yield > 4.5%: -1

    Tầng 3 - Momentum (15%): Yield biến động >0.3%/tuần
      - Thị trường bất ổn → -1 đến -2 cả 2 hướng
    """
    if not us10y_candles or len(us10y_candles) < 2:
        return 0.0

    # Chỉ áp dụng cho kim loại quý và JPY pairs
    sym_upper = symbol.upper()
    if not any(code in sym_upper for code in ("XAU", "XAG", "JPY")):
        if not sym_upper.endswith("/USD"):
            return 0.0

    # ^TNX trả về trực tiếp lợi suất % (4.617 ≈ 4.617%) — so sánh trực tiếp.
    current = us10y_candles[-1].close
    prev_day = us10y_candles[-2].close
    y_up = current > prev_day

    # --- Tầng 1: Directional (60%) ---
    buy_usd = (sym_upper.startswith("USD") and side == "buy") or \
              (sym_upper.endswith("/USD") and side == "sell")

    directional = 0.0
    if "XAU" in sym_upper or "XAG" in sym_upper:
        # Precious metals: yield up supports SELL (USD stronger + higher opportunity cost).
        if (side == "sell" and y_up) or (side == "buy" and not y_up):
            directional = 2.0
        else:
            directional = -3.0
    elif "JPY" in sym_upper:
        # JPY: yield up → USD/JPY tăng (chênh lệch lợi suất mở rộng, JPY yếu)
        if buy_usd:
            directional = 2.0 if y_up else -2.0
        else:
            directional = 2.0 if not y_up else -2.0
    elif sym_upper.endswith("/USD"):
        # Các cặp XXX/USD (EUR, GBP, AUD, NZD, CAD):
        # US10Y tăng → USD mạnh → SELL XXX/USD thuận, BUY XXX/USD ngược
        if (side == "buy" and not y_up) or (side == "sell" and y_up):
            directional = 1.5
        else:
            directional = -1.5
        total = directional
        return round(total, 1)

    # --- Tầng 2: Absolute Level (25%) ---
    level_score = 0.0
    if current > 5.5:
        if buy_usd:
            level_score = -2.0  # debt concern, USD rủi ro dài hạn
    elif current > 4.5:
        if buy_usd:
            level_score = -1.0

    # --- Tầng 3: Momentum 5 ngày (15%) ---
    momentum_score = 0.0
    if len(us10y_candles) >= 5:
        five_day_ago = us10y_candles[-5].close
        if five_day_ago > 0:
            change = abs(current - five_day_ago)
            if change > 0.5:
                momentum_score = -2.0
            elif change > 0.3:
                momentum_score = -1.0

    total = directional * 0.60 + level_score * 0.25 + momentum_score * 0.15
    return round(total, 1)


def _us2y_score(side: str, symbol: str, us2y_candles: list | None) -> float:
    """
    US2Y 3-tier scoring cho XAU, XAG và JPY pairs.

    US2Y phản ánh kỳ vọng chính sách Fed ngắn hạn, nhạy hơn US10Y
    với các thay đổi lãi suất. Đường cong 2s10s cho tín hiệu suy thoái.

    Tầng 1 - Directional (60%): Yield tăng → USD mạnh ngắn hạn
      - BUY USD/XXX + yield up: +2
      - SELL USD/XXX + yield down: +2
      - Ngược lại: -2 đến -3

    Tầng 2 - Absolute Level (25%): US2Y > 4.5% → thắt chặt mạnh
      - BUY USD khi US2Y > 4.5%: -2 (rủi ro đảo chiều chính sách)
      - US2Y > 3.5%: -1

    Tầng 3 - Momentum (15%): US2Y biến động >0.4%/tuần
      - Thị trường bất ổn → -1 đến -2 cả 2 hướng
    """
    if not us2y_candles or len(us2y_candles) < 2:
        return 0.0

    sym_upper = symbol.upper()
    if not any(code in sym_upper for code in ("XAU", "XAG", "JPY")):
        if not sym_upper.endswith("/USD"):
            return 0.0

    current = us2y_candles[-1].close
    prev_day = us2y_candles[-2].close
    y_up = current > prev_day

    # --- Tầng 1: Directional (60%) ---
    buy_usd = (sym_upper.startswith("USD") and side == "buy") or \
              (sym_upper.endswith("/USD") and side == "sell")

    directional = 0.0
    if "XAU" in sym_upper or "XAG" in sym_upper:
        if (side == "sell" and y_up) or (side == "buy" and not y_up):
            directional = 2.0
        else:
            directional = -3.0
    elif "JPY" in sym_upper:
        if buy_usd:
            directional = 2.0 if y_up else -2.0
        else:
            directional = 2.0 if not y_up else -2.0
    elif sym_upper.endswith("/USD"):
        # Các cặp XXX/USD (EUR, GBP, AUD, NZD, CAD):
        # US2Y tăng → USD mạnh → SELL XXX/USD thuận, BUY XXX/USD ngược
        if (side == "buy" and not y_up) or (side == "sell" and y_up):
            directional = 1.0
        else:
            directional = -1.0
        total = directional
        return round(total, 1)

    # --- Tầng 2: Absolute Level (25%) ---
    level_score = 0.0
    if current > 4.5:
        if buy_usd:
            level_score = -2.0
    elif current > 3.5:
        if buy_usd:
            level_score = -1.0

    # --- Tầng 3: Momentum 5 ngày (15%) ---
    momentum_score = 0.0
    if len(us2y_candles) >= 5:
        five_day_ago = us2y_candles[-5].close
        if five_day_ago > 0:
            change = abs(current - five_day_ago)
            if change > 0.4:
                momentum_score = -2.0
            elif change > 0.25:
                momentum_score = -1.0

    total = directional * 0.60 + level_score * 0.25 + momentum_score * 0.15
    return round(total, 1)


def compute_correlation_adjustment(
    symbol: str,
    side: str,
    dxy_candles: list | None = None,
    us10y_candles: list | None = None,
    us2y_candles: list | None = None,
    vix_candles: list | None = None,
) -> float:
    """
    Tổng hợp điều chỉnh điểm Macro từ DXY + VIX + US10Y + US2Y.
    Trả về float từ -11 đến +7.

    Nhóm DXY + US10Y + US2Y cùng đo sức mạnh USD nên được kẹp trong
    [-6, +5]; điểm VIX (hiện tượng khác) nằm ngoài giới hạn này.

    Returns:
        float: Số điểm điều chỉnh (có thể âm hoặc dương)
    """
    adjustment = 0.0

    if dxy_candles is not None:
        adjustment += _dxy_score(side, symbol, dxy_candles)

    if us10y_candles is not None:
        adjustment += _us10y_score(side, symbol, us10y_candles)

    if us2y_candles is not None:
        adjustment += _us2y_score(side, symbol, us2y_candles)

    # Nhóm sức mạnh USD: kẹp trong [-6, +5] để tránh tính trùng 3 lần
    adjustment = max(-6.0, min(5.0, adjustment))

    if vix_candles is not None:
        adjustment += _vix_score(symbol, side, vix_candles)

    return round(adjustment, 1)
