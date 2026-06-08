from __future__ import annotations


def ema(values: list[float], period: int) -> list[float]:
    if period <= 0:
        raise ValueError("period must be greater than 0")
    if not values:
        return []

    multiplier = 2 / (period + 1)
    result = [float(values[0])]
    for value in values[1:]:
        result.append((float(value) - result[-1]) * multiplier + result[-1])
    return result


def rsi(values: list[float], period: int = 14) -> list[float | None]:
    if period <= 0:
        raise ValueError("period must be greater than 0")
    if len(values) < period + 1:
        return [None] * len(values)

    deltas = [float(values[i]) - float(values[i - 1]) for i in range(1, len(values))]
    gains = [max(delta, 0.0) for delta in deltas]
    losses = [abs(min(delta, 0.0)) for delta in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    result: list[float | None] = [None] * period

    def value(gain: float, loss: float) -> float:
        if loss == 0:
            return 100.0
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    result.append(value(avg_gain, avg_loss))
    for i in range(period, len(deltas)):
        avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period
        result.append(value(avg_gain, avg_loss))
    return result


def macd(
    values: list[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> dict[str, list[float]]:
    if fast_period <= 0 or slow_period <= 0 or signal_period <= 0:
        raise ValueError("periods must be greater than 0")
    if fast_period >= slow_period:
        raise ValueError("fast_period must be smaller than slow_period")
    if not values:
        return {"macd": [], "signal": [], "histogram": []}

    fast = ema(values, fast_period)
    slow = ema(values, slow_period)
    macd_line = [fast_value - slow_value for fast_value, slow_value in zip(fast, slow)]
    signal_line = ema(macd_line, signal_period)
    histogram = [macd_value - signal_value for macd_value, signal_value in zip(macd_line, signal_line)]
    return {"macd": macd_line, "signal": signal_line, "histogram": histogram}


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float | None]:
    if period <= 0:
        raise ValueError("period must be greater than 0")
    if not highs or not lows or not closes:
        return []
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("highs, lows and closes must have the same length")

    true_ranges: list[float] = []
    for index, high in enumerate(highs):
        low = lows[index]
        previous_close = closes[index - 1] if index else closes[index]
        true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))

    if len(true_ranges) < period:
        return [None] * len(true_ranges)

    result: list[float | None] = [None] * (period - 1)
    current = sum(true_ranges[:period]) / period
    result.append(current)
    for value in true_ranges[period:]:
        current = ((current * (period - 1)) + value) / period
        result.append(current)
    return result
