from core.indicators import ema, rsi


def test_ema_returns_series() -> None:
    result = ema([1, 2, 3, 4], 2)
    assert len(result) == 4
    assert result[-1] > result[0]


def test_rsi_short_series_returns_none_values() -> None:
    assert rsi([1, 2, 3], 14) == [None, None, None]
