from __future__ import annotations

from dataclasses import dataclass
from math import floor
from typing import Any

from core.entry_engine import evaluate_entry
from core.market_models import Candle
from core.signal_engine import clamp
from core.correlation_check import get_correlation_warnings, summarize_correlation_context


# SYMBOL_CONFIG chỉ chứa symbol có contract_size khác mặc định 100,000 (forex standard).
# Với forex: contract_size luôn lấy từ controller (settings.trading.contract_size_override, mặc định 100,000),
# không dùng trade_contract_size từ MT5 vì cent account trả về 100 gây sai lot.
SYMBOL_CONFIG: dict[str, dict[str, Any]] = {
    "XAU/USD": {"contract_size": 100.0, "quote_currency": "USD", "method": "price_distance_x_contract_size"},
    "XAG/USD": {"contract_size": 5000.0, "quote_currency": "USD", "method": "price_distance_x_contract_size"},
    "BTC/USD": {"contract_size": 1.0, "quote_currency": "USD", "method": "price_distance_x_contract_size"},
}

STRENGTH_RANK = {"strong": 3, "moderate": 2, "weak": 1}


@dataclass(frozen=True, slots=True)
class AnalysisInput:
    symbol: str
    broker_symbol: str
    account_balance: float
    risk_percent: float
    account_currency: str = "USD"
    lot_step: float = 0.01
    minimum_lot: float = 0.01
    contract_size_override: float | None = None
    timezone_name: str = "Asia/Ho_Chi_Minh"


def reward_risk(entry: float, stop: float, target: float) -> float:
    risk = abs(entry - stop)
    if risk == 0:
        raise ValueError("stop must differ from entry")
    return abs(target - entry) / risk


def calc_trade_permission(data_quality: dict[str, Any], risk_score: int, best_score: int) -> dict[str, Any]:
    if not data_quality.get("terminal_connected", False) or not data_quality.get("broker_logged_in", False):
        return {"status": "blocked", "reason": "MT5 chưa sẵn sàng hoặc broker chưa đăng nhập.", "resume_after": None}
    if data_quality.get("spread_status") == "abnormal":
        return {"status": "blocked", "reason": "Spread đang bất thường, cần kiểm tra lại dữ liệu mới.", "resume_after": None}
    if data_quality.get("warning"):
        return {"status": "blocked", "reason": data_quality["warning"], "resume_after": None}
    if data_quality.get("high_impact_event_within_30m"):
        return {
            "status": "blocked",
            "reason": "Có tin kinh tế tác động cao rất gần, không nên vào lệnh trước/sau tin.",
            "resume_after": data_quality.get("resume_after"),
        }
    if data_quality.get("news_in_3h"):
        return {
            "status": "caution",
            "reason": "Có tin kinh tế tác động cao trong 3 giờ tới, chỉ theo dõi và chờ sau tin.",
            "resume_after": data_quality.get("resume_after"),
        }
    if risk_score < 9 or best_score < 65:
        return {"status": "caution", "reason": "Điều kiện rủi ro hoặc điểm setup chưa đủ mạnh, cần chờ xác nhận.", "resume_after": None}
    return {"status": "allowed", "reason": "Dữ liệu ổn, không có cảnh báo rủi ro chính.", "resume_after": None}


def build_scenarios(
    request: AnalysisInput,
    technical: dict[str, Any],
    smc: dict[str, Any],
    scores: dict[str, dict[str, Any]],
    trade_permission: dict[str, Any],
    h1_candles: list[Candle] | None = None,
    m15_candles: list[Candle] | None = None,
    correlation_context: dict[str, Any] | None = None,
    quote_to_usd_rate: float | None = None,
    spread_price: float = 0.0,
) -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []
    for side in ("buy", "sell"):
        side_total = scores[side].get("signal_score", scores[side].get("total", 0))
        if side_total < 50 or trade_permission["status"] == "blocked":
            continue
        plan = build_trade_plan(side, request, technical, smc, h1_candles or [], m15_candles=m15_candles, correlation_context=correlation_context, quote_to_usd_rate=quote_to_usd_rate, spread_price=spread_price)
        if not plan:
            continue
        plan.update({
            "type": side,
            "priority": "primary" if not scenarios else "secondary",
            "score": side_total,
        })
        scenarios.append(plan)
    return sorted(scenarios, key=lambda item: item["score"], reverse=True)


def build_trade_plan(
    side: str,
    request: AnalysisInput,
    technical: dict[str, Any],
    smc: dict[str, Any],
    h1_candles: list[Candle] | None = None,
    *,
    m15_candles: list[Candle] | None = None,
    correlation_context: dict[str, Any] | None = None,
    quote_to_usd_rate: float | None = None,
    spread_price: float = 0.0,
) -> dict[str, Any] | None:
    price = technical["price"]
    atr_value = technical["atr_h4"] or technical["atr_d1"] or 0.0
    if atr_value <= 0:
        return None
    min_stop_distance = max(atr_value * 0.20, price * 0.0002)
    h4_smc = smc.get("H4", {}) if isinstance(smc, dict) else {}
    smc_supports = _smc_zones_to_levels(h4_smc.get("demand_zones", []))
    smc_resistances = _smc_zones_to_levels(h4_smc.get("supply_zones", []))

    support_zones = list(technical["support_zones"]) + smc_supports
    resistance_zones = list(technical["resistance_zones"]) + smc_resistances

    if side == "buy":
        support = select_best_level(support_zones, price, atr_value * 1.5, below=True)
        if not support:
            return None
        level = support["level"]
        entry_zone_score = support.get("zone_score")
        entry_zone_source = support.get("source", "technical")
        watch_low = level - atr_value * 0.10
        watch_high = level + atr_value * 0.50
        entry_low = level - atr_value * 0.20
        entry_high = level + atr_value * 0.20
        stop_loss = level - max(atr_value * 0.50, min_stop_distance)
        tp1 = nearest_target(resistance_zones, entry_high, above=True)
        tp2 = next_target(resistance_zones, tp1, above=True) if tp1 else None
        entry_for_rr = entry_high
        if tp1 is None or (tp1 - entry_for_rr) < (entry_for_rr - stop_loss):
            return None
        condition = _build_buy_condition(h4_smc)
        invalidation = _build_buy_invalidation(stop_loss, h4_smc)
    else:
        resistance = select_best_level(resistance_zones, price, atr_value * 1.5, below=False)
        if not resistance:
            return None
        level = resistance["level"]
        entry_zone_score = resistance.get("zone_score")
        entry_zone_source = resistance.get("source", "technical")
        watch_low = level - atr_value * 0.50
        watch_high = level + atr_value * 0.10
        entry_low = level - atr_value * 0.20
        entry_high = level + atr_value * 0.20
        stop_loss = level + max(atr_value * 0.50, min_stop_distance)
        tp1 = nearest_target(support_zones, entry_low, above=False)
        tp2 = next_target(support_zones, tp1, above=False) if tp1 else None
        entry_for_rr = entry_low
        if tp1 is None or (entry_for_rr - tp1) < (stop_loss - entry_for_rr):
            return None
        condition = _build_sell_condition(h4_smc)
        invalidation = _build_sell_invalidation(stop_loss, h4_smc)

    entry_zone = [round_price(entry_low), round_price(entry_high)]
    watch_zone = [round_price(watch_low), round_price(watch_high)]
    entry_state = evaluate_entry(
        side=side,
        technical=technical,
        smc=smc,
        h1_candles=h1_candles or [],
        entry_zone=entry_zone,
        m15_candles=m15_candles,
    )
    sizing = position_sizing(request, (entry_low + entry_high) / 2, stop_loss, quote_to_usd_rate=quote_to_usd_rate)

    corr_warnings: list[str] = []
    corr_context: dict[str, Any] | None = None
    if correlation_context:
        corr_dxy = correlation_context.get("dxy_candles")
        corr_us10y = correlation_context.get("us10y_candles")
        corr_vix = correlation_context.get("vix_candles")
        corr_warnings = get_correlation_warnings(request.symbol, side, dxy_candles=corr_dxy, us10y_candles=corr_us10y, vix_candles=corr_vix)
        corr_context = summarize_correlation_context(request.symbol, side, dxy_candles=corr_dxy, us10y_candles=corr_us10y, vix_candles=corr_vix)

    return {
        "entry_zone": entry_zone,
        "watch_zone": watch_zone,
        "stop_loss": round_price(stop_loss),
        "take_profit": [round_price(value) for value in (tp1, tp2) if value is not None],
        "risk_reward": f"1:{reward_risk(entry_for_rr, stop_loss, tp1):.1f}",
        "expected_effective_rr": calculate_expected_effective_rr(
            direction=side,
            entry=entry_for_rr,
            stop_loss=stop_loss,
            take_profit=tp1,
            spread_price=spread_price,
        ),
        "condition": condition,
        "invalidation": invalidation,
        "position_sizing": sizing,
        "correlation_warnings": corr_warnings,
        "correlation_context": corr_context,
        "entry_zone_score": entry_zone_score,
        "entry_zone_source": entry_zone_source,
        **entry_state,
    }


def _smc_zones_to_levels(zones: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for zone in zones[:4]:
        if zone.get("broken"):
            continue
        low = zone.get("low")
        high = zone.get("high")
        if low is None or high is None:
            continue
        level = (low + high) / 2
        converted.append(
            {
                "level": level,
                "low": low,
                "high": high,
                "type": zone.get("type", "smc_zone"),
                "strength": zone.get("strength", "moderate"),
                "confluence_count": zone.get("confluence_count", 1),
                "consolidation_bars": zone.get("consolidation_bars", 0),
                "zone_score": zone.get("zone_score", 50),
                "freshness_bars": zone.get("freshness_bars"),
                "mitigated": zone.get("mitigated", False),
                "broken": zone.get("broken", False),
                "test_count": zone.get("test_count", 0),
                "displacement_multiple": zone.get("displacement_multiple", 0),
                "liquidity_sweep": zone.get("liquidity_sweep", False),
                "zone_location": zone.get("zone_location", "unknown"),
                "source": "smc",
            }
        )
    return converted


def _build_buy_condition(h4_smc: dict[str, Any]) -> str:
    base = "Chỉ cân nhắc nếu H1 đóng nến tăng tại vùng hỗ trợ và spread vẫn bình thường."
    extras: list[str] = []
    if h4_smc.get("bos") and h4_smc.get("displacement") == "bullish":
        extras.append("BOS H4 đã xác nhận theo hướng tăng")
    if h4_smc.get("demand_zones"):
        extras.append("ưu tiên khớp khi giá vào demand zone gần nhất")
    if h4_smc.get("fvg"):
        extras.append("nếu giá lấp FVG bullish, ưu tiên xác nhận thêm")
    if not extras:
        return base
    return base + " " + "; ".join(extras) + "."


def _build_buy_invalidation(stop_loss: float, h4_smc: dict[str, Any]) -> str:
    base = f"H1 đóng dưới {stop_loss:.5f} hoặc spread giãn bất thường."
    if h4_smc.get("choch") and h4_smc.get("displacement") == "bearish":
        return base + " Cảnh báo CHOCH bearish trên H4 — ưu tiên đứng ngoài."
    return base


def _build_sell_condition(h4_smc: dict[str, Any]) -> str:
    base = "Chỉ cân nhắc nếu H1 đóng nến giảm tại vùng kháng cự và spread vẫn bình thường."
    extras: list[str] = []
    if h4_smc.get("bos") and h4_smc.get("displacement") == "bearish":
        extras.append("BOS H4 đã xác nhận theo hướng giảm")
    if h4_smc.get("supply_zones"):
        extras.append("ưu tiên khớp khi giá vào supply zone gần nhất")
    if h4_smc.get("fvg"):
        extras.append("nếu giá lấp FVG bearish, ưu tiên xác nhận thêm")
    if not extras:
        return base
    return base + " " + "; ".join(extras) + "."


def _build_sell_invalidation(stop_loss: float, h4_smc: dict[str, Any]) -> str:
    base = f"H1 đóng trên {stop_loss:.5f} hoặc spread giãn bất thường."
    if h4_smc.get("choch") and h4_smc.get("displacement") == "bullish":
        return base + " Cảnh báo CHOCH bullish trên H4 — ưu tiên đứng ngoài."
    return base


def select_best_level(
    zones: list[dict[str, Any]], price: float, max_distance: float, *, below: bool
) -> dict[str, Any] | None:
    candidates = [
        zone
        for zone in zones
        if (zone["level"] <= price + max_distance if below else zone["level"] >= price - max_distance)
        and abs(zone["level"] - price) <= max_distance
    ]
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda zone: (-STRENGTH_RANK.get(zone.get("strength", "weak"), 0), abs(zone["level"] - price)),
    )[0]


def nearest_target(zones: list[dict[str, Any]], reference: float, *, above: bool) -> float | None:
    levels = sorted(
        {zone["level"] for zone in zones if zone["level"] > reference}
        if above
        else {zone["level"] for zone in zones if zone["level"] < reference},
        reverse=not above,
    )
    return levels[0] if levels else None


def next_target(zones: list[dict[str, Any]], first_target: float, *, above: bool) -> float | None:
    levels = sorted(
        {zone["level"] for zone in zones if zone["level"] > first_target}
        if above
        else {zone["level"] for zone in zones if zone["level"] < first_target},
        reverse=not above,
    )
    return levels[0] if levels else None


def position_sizing(request: AnalysisInput, entry_price: float, stop_loss: float, *, quote_to_usd_rate: float | None = None) -> dict[str, Any]:
    contract_size = contract_size_for(request)
    risk_amount = request.account_balance * request.risk_percent / 100
    price_distance = abs(entry_price - stop_loss)
    loss_per_lot = price_distance * contract_size
    if quote_to_usd_rate is None:
        quote_to_usd_rate = _resolve_quote_to_usd_rate(request.symbol)
    if quote_to_usd_rate is not None and quote_to_usd_rate > 0:
        loss_per_lot = loss_per_lot * quote_to_usd_rate
    raw_lot = risk_amount / loss_per_lot if loss_per_lot else 0.0
    lot = round_lot(raw_lot, request.lot_step, request.minimum_lot)
    return {
        "account_balance": request.account_balance,
        "risk_pct": request.risk_percent,
        "risk_amount_usd": risk_amount,
        "entry_price": round_price(entry_price),
        "stop_loss": round_price(stop_loss),
        "price_distance": round_price(price_distance),
        "contract_size": contract_size,
        "suggested_lot": lot,
    }


def _resolve_quote_to_usd_rate(symbol: str) -> float | None:
    """Try to get quote-currency to USD conversion rate from MT5."""
    if "/" not in symbol:
        return None
    quote = symbol.split("/")[-1]
    if quote == "USD":
        return 1.0
    mt5 = None
    initialized = False
    try:
        import MetaTrader5 as mt5

        initialized = mt5.initialize()
        if not initialized:
            return None
        for pair_name in (quote + "USD", "USD" + quote):
            tick = mt5.symbol_info_tick(pair_name)
            if tick is None:
                symbols = mt5.symbols_get()
                for sym in (symbols or []):
                    name = getattr(sym, "name", "")
                    if name.upper().startswith(pair_name.upper()):
                        mt5.symbol_select(name, True)
                        tick = mt5.symbol_info_tick(name)
                        break
            if tick and tick.bid:
                rate = float(tick.bid)
                return rate if pair_name.startswith(quote) else 1.0 / rate
        return None
    except Exception:
        return None
    finally:
        if initialized and mt5 is not None:
            mt5.shutdown()


def contract_size_for(request: AnalysisInput) -> float:
    # Flow ưu tiên:
    # 1. Controller override (symbols đặc biệt lấy từ MT5, forex luôn lấy từ settings 100,000)
    # 2. SYMBOL_CONFIG lookup (chỉ chứa symbol đặc biệt như XAU/USD, XAG/USD, BTC/USD)
    # 3. Fallback mặc định 100,000 (standard forex lot)
    if request.contract_size_override and request.contract_size_override > 0:
        return request.contract_size_override
    return float(SYMBOL_CONFIG.get(request.symbol, {}).get("contract_size", 100000.0))


def contract_size_override_for_symbol(
    symbol: str,
    data_quality: dict[str, Any],
    forex_contract_size: float,
) -> float | None:
    if symbol in SYMBOL_CONFIG:
        broker_contract_size = data_quality.get("contract_size")
        if broker_contract_size:
            try:
                broker_value = float(broker_contract_size)
            except (TypeError, ValueError):
                broker_value = 0.0
            if broker_value > 0:
                return broker_value
        return float(SYMBOL_CONFIG[symbol]["contract_size"])
    return forex_contract_size


def round_lot(value: float, step: float, minimum: float) -> float:
    if value <= 0:
        return 0.0
    step = step or 0.01
    rounded = floor(value / step) * step
    return round(max(minimum, rounded), 2)


def round_price(value: float) -> float:
    return round(value, 5)


# ---------------------------------------------------------------------------
# Phase 6: Expected effective R:R (spread-adjusted)
# ---------------------------------------------------------------------------


def calculate_spread_cost(spread_price: float | int | str | None) -> float:
    """Chuyen spread_price thanh float an toan.

    Tra ve 0.0 neu None, am, hoac khong convert duoc.
    """
    try:
        value = float(spread_price or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return max(value, 0.0)


def calculate_expected_effective_rr(
    direction: str,
    entry: float | None,
    stop_loss: float | None,
    take_profit: float | None,
    spread_price: float | int | str | None = 0.0,
) -> float:
    """Tinh expected effective R:R sau khi tru spread.

    Spread lam tang risk (effective_risk = risk + spread_cost)
    va giam reward (effective_reward = reward - spread_cost).

    Returns
    -------
    float
        Effective R:R, lam tron 4 chu so thap phan.
        Tra 0.0 neu input khong hop le hoac effective_risk <= 0.
    """
    try:
        direction = str(direction).lower()
        entry_val = float(entry) if entry is not None else None
        sl_val = float(stop_loss) if stop_loss is not None else None
        tp_val = float(take_profit) if take_profit is not None else None
    except (TypeError, ValueError):
        return 0.0

    if entry_val is None or sl_val is None or tp_val is None:
        return 0.0

    if direction not in ("buy", "sell"):
        return 0.0

    if direction == "buy":
        risk = abs(entry_val - sl_val)
        reward = abs(tp_val - entry_val)
    else:  # sell
        risk = abs(sl_val - entry_val)
        reward = abs(entry_val - tp_val)

    spread_cost = calculate_spread_cost(spread_price)

    effective_risk = risk + spread_cost
    effective_reward = reward - spread_cost

    if effective_risk <= 0:
        return 0.0

    return round(max(effective_reward / effective_risk, 0.0), 4)
