from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.market_models import Candle

MAX_LOOKBACK_DAYS = 180


@dataclass(frozen=True, slots=True)
class ReplaySetup:
    symbol: str
    side: str
    entry_zone: tuple[float, float]
    stop_loss: float
    take_profit: float
    risk_reward: float
    max_holding_bars: int = 48
    cooldown_bars: int = 5


def replay_plan(symbol: str, scenario: dict[str, Any], candles: list[Candle]) -> dict[str, Any]:
    setup = setup_from_scenario(symbol, scenario)
    if setup is None or len(candles) < 3:
        return empty_replay("Không đủ dữ liệu hoặc chưa có trade plan hợp lệ để replay.")
    trades = simulate_replay(setup, candles)
    summary = summarize_trades(trades)
    return {
        "mode": "plan_replay",
        "symbol": symbol,
        "timeframe": "H1",
        "setup": {
            "side": setup.side,
            "entry_zone": list(setup.entry_zone),
            "stop_loss": setup.stop_loss,
            "take_profit": setup.take_profit,
            "risk_reward": setup.risk_reward,
            "max_holding_bars": setup.max_holding_bars,
            "cooldown_bars": setup.cooldown_bars,
        },
        "summary": summary,
        "by_symbol": {symbol: summary},
        "by_session": summarize_by_session(trades),
        "trades": trades[-30:],
    }


def setup_from_scenario(symbol: str, scenario: dict[str, Any]) -> ReplaySetup | None:
    if not scenario or scenario.get("type") not in {"buy", "sell"}:
        return None
    entry_zone = scenario.get("entry_zone")
    take_profit = scenario.get("take_profit")
    stop_loss = scenario.get("stop_loss")
    if not isinstance(entry_zone, list) or len(entry_zone) != 2 or not take_profit or stop_loss is None:
        return None
    tp1 = take_profit[0] if isinstance(take_profit, list) else take_profit
    risk_reward = parse_risk_reward(scenario.get("risk_reward"))
    return ReplaySetup(
        symbol=symbol,
        side=str(scenario["type"]),
        entry_zone=(float(min(entry_zone)), float(max(entry_zone))),
        stop_loss=float(stop_loss),
        take_profit=float(tp1),
        risk_reward=risk_reward,
    )


def simulate_replay(setup: ReplaySetup, candles: list[Candle]) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    index = 0
    while index < len(candles) - 1:
        candle = candles[index]
        if not touches_entry_zone(candle, setup.entry_zone):
            index += 1
            continue
        entry_price = entry_price_for(setup)
        exit_index, outcome, exit_price, mfe_r, mae_r = resolve_trade(setup, candles, index + 1, entry_price)
        trades.append(
            {
                "symbol": setup.symbol,
                "side": setup.side,
                "entry_time": candle.time.isoformat(),
                "exit_time": candles[exit_index].time.isoformat(),
                "session": trading_session(candle.time),
                "entry_price": round_price(entry_price),
                "exit_price": round_price(exit_price),
                "result_r": round(result_r(setup, entry_price, exit_price), 3) if outcome != "timeout" else 0.0,
                "outcome": outcome,
                "mfe_r": round(mfe_r, 3),
                "mae_r": round(mae_r, 3),
                "holding_bars": exit_index - index,
            }
        )
        index = max(exit_index + setup.cooldown_bars + 1, index + 1)
    return trades


def resolve_trade(
    setup: ReplaySetup,
    candles: list[Candle],
    start_index: int,
    entry_price: float,
) -> tuple[int, str, float, float, float]:
    stop_distance = abs(entry_price - setup.stop_loss)
    mfe_r = 0.0
    mae_r = 0.0
    end_index = min(len(candles) - 1, start_index + setup.max_holding_bars)
    for index in range(start_index, end_index + 1):
        candle = candles[index]
        if setup.side == "buy":
            mfe_r = max(mfe_r, (candle.high - entry_price) / stop_distance)
            mae_r = min(mae_r, (candle.low - entry_price) / stop_distance)
            stop_hit = candle.low <= setup.stop_loss
            target_hit = candle.high >= setup.take_profit
        else:
            mfe_r = max(mfe_r, (entry_price - candle.low) / stop_distance)
            mae_r = min(mae_r, (entry_price - candle.high) / stop_distance)
            stop_hit = candle.high >= setup.stop_loss
            target_hit = candle.low <= setup.take_profit
        if stop_hit and target_hit:
            return index, "loss", setup.stop_loss, mfe_r, mae_r
        if stop_hit:
            return index, "loss", setup.stop_loss, mfe_r, mae_r
        if target_hit:
            return index, "win", setup.take_profit, mfe_r, mae_r
    return end_index, "timeout", candles[end_index].close, mfe_r, mae_r


def summarize_trades(trades: list[dict[str, Any]]) -> dict[str, Any]:
    if not trades:
        return {
            "trade_count": 0,
            "win_rate": 0.0,
            "expectancy_r": 0.0,
            "average_r": 0.0,
            "average_mfe_r": 0.0,
            "average_mae_r": 0.0,
            "max_drawdown_r": 0.0,
        }
    results = [float(item["result_r"]) for item in trades]
    wins = [value for value in results if value > 0]
    return {
        "trade_count": len(trades),
        "win_rate": round(len(wins) / len(trades) * 100, 2),
        "expectancy_r": round(sum(results) / len(results), 3),
        "average_r": round(sum(results) / len(results), 3),
        "average_mfe_r": round(sum(float(item["mfe_r"]) for item in trades) / len(trades), 3),
        "average_mae_r": round(sum(float(item["mae_r"]) for item in trades) / len(trades), 3),
        "max_drawdown_r": round(max_drawdown(results), 3),
    }


def summarize_by_session(trades: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    sessions: dict[str, list[dict[str, Any]]] = {}
    for trade in trades:
        sessions.setdefault(str(trade.get("session", "unknown")), []).append(trade)
    return {session: summarize_trades(rows) for session, rows in sessions.items()}


def touches_entry_zone(candle: Candle, entry_zone: tuple[float, float]) -> bool:
    low, high = entry_zone
    return candle.low <= high and candle.high >= low


def entry_price_for(setup: ReplaySetup) -> float:
    return sum(setup.entry_zone) / 2


def result_r(setup: ReplaySetup, entry_price: float, exit_price: float) -> float:
    stop_distance = abs(entry_price - setup.stop_loss)
    if stop_distance == 0:
        return 0.0
    if setup.side == "buy":
        return (exit_price - entry_price) / stop_distance
    return (entry_price - exit_price) / stop_distance


def max_drawdown(results: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in results:
        equity += value
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return abs(max_dd)


def trading_session(moment: datetime) -> str:
    hour = moment.hour
    if 0 <= hour < 7:
        return "Asia"
    if 7 <= hour < 13:
        return "London"
    if 13 <= hour < 21:
        return "New York"
    return "Late US"


def parse_risk_reward(value: object) -> float:
    if not value:
        return 0.0
    text = str(value)
    if ":" not in text:
        return 0.0
    try:
        return float(text.split(":", 1)[1])
    except ValueError:
        return 0.0


def round_price(value: float) -> float:
    return round(value, 5)


def empty_replay(reason: str) -> dict[str, Any]:
    return {
        "mode": "plan_replay",
        "summary": summarize_trades([]),
        "by_symbol": {},
        "by_session": {},
        "trades": [],
        "reason": reason,
    }
