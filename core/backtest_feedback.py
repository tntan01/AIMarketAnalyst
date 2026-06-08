from __future__ import annotations

from typing import Any

from core.market_models import Candle


def _compute_h1_atr(candles: list[Candle], period: int = 14) -> float:
    if len(candles) < period + 1:
        return 0.0
    true_ranges: list[float] = []
    for i in range(1, len(candles)):
        high = candles[i].high
        low = candles[i].low
        prev_close = candles[i - 1].close
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(tr)
    if len(true_ranges) < period:
        return 0.0
    return sum(true_ranges[-period:]) / period


def _find_candle_signals(candles: list[Candle], side: str) -> list[dict[str, object]]:
    signals: list[dict[str, object]] = []
    if len(candles) < 4:
        return signals
    for i in range(1, len(candles) - 4):
        prev = candles[i - 1]
        curr = candles[i]
        body = abs(curr.close - curr.open)
        candle_range = max(curr.high - curr.low, 1e-9)
        upper_wick = curr.high - max(curr.open, curr.close)
        lower_wick = min(curr.open, curr.close) - curr.low
        entry_price = curr.close

        if side == "buy":
            bullish = curr.close > curr.open
            engulfing = bullish and curr.close > prev.high and curr.open <= prev.close
            rejection = bullish and lower_wick >= max(body * 0.8, candle_range * 0.25)
            micro_break = curr.close > max(c.high for c in candles[max(0, i - 2) : i])
            if engulfing or rejection or micro_break:
                signals.append({"idx": i, "entry_price": entry_price})
        else:
            bearish = curr.close < curr.open
            engulfing = bearish and curr.close < prev.low and curr.open >= prev.close
            rejection = bearish and upper_wick >= max(body * 0.8, candle_range * 0.25)
            micro_break = curr.close < min(c.low for c in candles[max(0, i - 2) : i])
            if engulfing or rejection or micro_break:
                signals.append({"idx": i, "entry_price": entry_price})
    return signals


def _forward_test(
    candles: list[Candle],
    signal_idx: int,
    entry_price: float,
    side: str,
    atr: float,
    bars: int = 3,
) -> bool:
    end = min(signal_idx + bars + 1, len(candles))
    future = candles[signal_idx + 1 : end]
    if len(future) < 2:
        return False

    if atr <= 0:
        # Fallback: simple close > entry check
        if side == "buy":
            return any(c.close > entry_price for c in future)
        return any(c.close < entry_price for c in future)

    threshold = 0.3 * atr
    max_adverse = 0.5 * atr

    if side == "buy":
        close_wins = sum(1 for c in future if c.close > entry_price + threshold)
        no_breakdown = all(c.low >= entry_price - max_adverse for c in future)
        return close_wins >= 2 and no_breakdown
    else:
        close_wins = sum(1 for c in future if c.close < entry_price - threshold)
        no_breakout = all(c.high <= entry_price + max_adverse for c in future)
        return close_wins >= 2 and no_breakout


def compute_pattern_confidence(
    trigger_type: str,
    side: str,
    h1_candles: list[Candle] | None,
) -> dict[str, Any]:
    if not h1_candles or len(h1_candles) < 10:
        return {
            "sample_size": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "confidence_adjustment": 0.0,
            "adjustment_reason": "Không đủ nến H1 để tìm pattern tương tự.",
        }

    atr = _compute_h1_atr(h1_candles)
    signals = _find_candle_signals(h1_candles, side)
    wins = 0
    losses = 0
    for sig in signals:
        idx = int(sig["idx"])
        entry = float(sig["entry_price"])
        if _forward_test(h1_candles, idx, entry, side, atr):
            wins += 1
        else:
            losses += 1

    sample_size = wins + losses
    if sample_size == 0:
        return {
            "sample_size": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "confidence_adjustment": 0.0,
            "adjustment_reason": f"Không tìm thấy pattern tương tự {trigger_type} trong lịch sử.",
        }

    win_rate = wins / sample_size

    if sample_size < 5:
        adj = 0.0
        reason = f"Chỉ có {sample_size} mẫu — chưa đủ để điều chỉnh confidence."
    elif sample_size >= 10 and win_rate >= 0.65:
        adj = 0.10
        reason = f"{sample_size} mẫu, win_rate={win_rate:.0%} — pattern có tỷ lệ thắng cao trong lịch sử."
    elif sample_size >= 10 and win_rate >= 0.55:
        adj = 0.05
        reason = f"{sample_size} mẫu, win_rate={win_rate:.0%} — pattern có tỷ lệ thắng khá."
    elif sample_size >= 10 and win_rate < 0.40:
        adj = -0.10
        reason = f"{sample_size} mẫu, win_rate={win_rate:.0%} — pattern có tỷ lệ thắng rất thấp."
    elif sample_size >= 5 and win_rate < 0.45:
        adj = -0.05
        reason = f"{sample_size} mẫu, win_rate={win_rate:.0%} — pattern có tỷ lệ thắng thấp."
    else:
        adj = 0.0
        reason = f"{sample_size} mẫu, win_rate={win_rate:.0%} — trung bình, không điều chỉnh."

    return {
        "sample_size": sample_size,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 3),
        "confidence_adjustment": adj,
        "adjustment_reason": reason,
    }
