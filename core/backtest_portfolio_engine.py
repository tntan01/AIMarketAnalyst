"""Chronological portfolio replay for independently generated symbol trades."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from core.system_backtest_engine import BacktestResult, BacktestTrade, summarize_backtest_trades


PORTFOLIO_REPLAY_VERSION = "backtest-portfolio-clock-v1"


@dataclass(frozen=True, slots=True)
class PortfolioReplayLimits:
    max_open_risk_pct: float = 3.0
    max_symbol_risk_pct: float = 2.0
    max_currency_exposure_pct: float = 2.0
    max_correlated_risk_pct: float = 2.0
    max_concurrent_positions: int = 5


def replay_portfolio(
    results: list[BacktestResult],
    *,
    initial_balance: float,
    limits: PortfolioReplayLimits,
) -> dict[str, Any]:
    """Merge all entries/exits on one clock and apply portfolio guards."""

    candidates: list[tuple[str, BacktestTrade]] = []
    for result in results:
        for trade in result.trades:
            candidates.append((_trade_id(trade, len(candidates)), trade))
    events: list[tuple[datetime, int, str, BacktestTrade]] = []
    for trade_id, trade in candidates:
        events.append((_moment(trade.entry_time), 1, trade_id, trade))
        if trade.exit_time:
            events.append((_moment(trade.exit_time), 0, trade_id, trade))
    events.sort(key=lambda row: (row[0], row[1], row[2]))

    accepted_ids: set[str] = set()
    active: dict[str, dict[str, Any]] = {}
    accepted: list[BacktestTrade] = []
    rejected: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []
    balance = float(initial_balance)

    for moment, event_kind, trade_id, trade in events:
        if event_kind == 0:
            if active.pop(trade_id, None) is None or trade_id not in accepted_ids:
                continue
            balance += float(trade.net_pnl_account or 0.0)
            equity_curve.append({
                "time": moment.isoformat(), "balance": round(balance, 4),
                "event": "EXIT", "symbol": trade.symbol, "trade_id": trade_id,
            })
            continue

        candidate = _exposure(trade, initial_balance)
        projected = [*active.values(), candidate]
        blocks = _guard_blocks(projected, candidate, limits)
        if blocks:
            rejected.append({
                "trade_id": trade_id, "symbol": trade.symbol,
                "side": trade.side, "entry_time": trade.entry_time,
                "risk_pct": candidate["risk_pct"], "block_codes": blocks,
            })
            continue
        active[trade_id] = candidate
        accepted_ids.add(trade_id)
        accepted.append(trade)
        equity_curve.append({
            "time": moment.isoformat(), "balance": round(balance, 4),
            "event": "ENTRY", "symbol": trade.symbol, "trade_id": trade_id,
            "open_risk_pct": round(sum(item["risk_pct"] for item in active.values()), 4),
            "open_positions": len(active),
        })

    per_symbol: dict[str, dict[str, Any]] = {}
    for result in results:
        rows = [trade for trade in accepted if trade.symbol == result.request.symbol]
        per_symbol[result.request.symbol] = {
            "candidate_summary": result.summary,
            "portfolio_summary": summarize_backtest_trades(rows),
            "candidate_trades": len(result.trades),
            "accepted_trades": len(rows),
            "rejected_trades": sum(row["symbol"] == result.request.symbol for row in rejected),
        }
    return {
        "version": PORTFOLIO_REPLAY_VERSION,
        "initial_balance": round(float(initial_balance), 4),
        "final_balance": round(balance, 4),
        "limits": asdict(limits),
        "summary": summarize_backtest_trades(accepted),
        "candidate_trades": len(candidates),
        "accepted_trades": len(accepted),
        "rejected_trades": len(rejected),
        "trades": [asdict(trade) for trade in accepted],
        "rejections": rejected,
        "equity_curve": equity_curve,
        "per_symbol": per_symbol,
    }


def _guard_blocks(exposures: list[dict[str, Any]], candidate: dict[str, Any], limits: PortfolioReplayLimits) -> list[str]:
    blocks: list[str] = []
    if len(exposures) > max(1, int(limits.max_concurrent_positions)):
        blocks.append("MAX_CONCURRENT_POSITIONS_EXCEEDED")
    if sum(item["risk_pct"] for item in exposures) > limits.max_open_risk_pct:
        blocks.append("PORTFOLIO_RISK_EXCEEDED")
    if sum(item["risk_pct"] for item in exposures if item["symbol"] == candidate["symbol"]) > limits.max_symbol_risk_pct:
        blocks.append("SYMBOL_RISK_EXCEEDED")
    currency = _currency_exposure(exposures)
    if any(max(side.values()) > limits.max_currency_exposure_pct for side in currency.values()):
        blocks.append("CURRENCY_EXPOSURE_EXCEEDED")
    candidate_currencies = set(candidate["currencies"])
    correlated = sum(item["risk_pct"] for item in exposures if candidate_currencies.intersection(item["currencies"]))
    if correlated > limits.max_correlated_risk_pct:
        blocks.append("CORRELATED_RISK_EXCEEDED")
    return blocks


def _exposure(trade: BacktestTrade, initial_balance: float) -> dict[str, Any]:
    normalized = "".join(char for char in trade.symbol.upper() if char.isalpha())
    base, quote = (normalized[:3], normalized[3:6]) if len(normalized) >= 6 else (normalized, "")
    side = str(trade.side).lower()
    amount = float(trade.planned_risk_account or trade.target_risk_account or 0.0)
    risk_pct = amount / float(initial_balance) * 100.0 if initial_balance > 0 and amount > 0 else 0.0
    return {
        "symbol": trade.symbol, "side": side, "risk_pct": round(risk_pct, 6),
        "currencies": tuple(currency for currency in (base, quote) if currency),
        "directions": {
            base: "long" if side == "buy" else "short",
            quote: "short" if side == "buy" else "long",
        },
    }


def _currency_exposure(exposures: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for item in exposures:
        for currency, direction in item["directions"].items():
            bucket = result.setdefault(currency, {"long": 0.0, "short": 0.0})
            bucket[direction] += float(item["risk_pct"])
    return result


def _trade_id(trade: BacktestTrade, ordinal: int) -> str:
    return str(trade.candidate_id or f"{trade.symbol}:{trade.entry_time}:{ordinal}")


def _moment(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
