"""Pure indicator calculations shared by strategies. Inputs are oldest first."""

from __future__ import annotations

import math
from collections.abc import Sequence


def sma(values: Sequence[float], period: int) -> float:
    """Simple moving average of the last ``period`` values."""
    if period < 1 or len(values) < period:
        raise ValueError(f"need {period} values, have {len(values)}")
    return math.fsum(values[-period:]) / period


def ema(values: Sequence[float], period: int) -> float:
    """Exponential moving average, smoothing 2 / (period + 1).

    Seeded with the simple average of the first ``period`` values, then
    updated with every later value. More history before the last value
    makes the result less dependent on the starting point.
    """
    if period < 1 or len(values) < period:
        raise ValueError(f"need {period} values, have {len(values)}")
    alpha = 2.0 / (period + 1)
    average = math.fsum(values[:period]) / period
    for value in values[period:]:
        average += alpha * (value - average)
    return average


def wilder_rsi(prices: Sequence[float], period: int) -> tuple[float | None, float, float]:
    """Wilder's Relative Strength Index of the last price.

    Returns ``(rsi, average_gain, average_loss)``. The averages are seeded
    with the simple mean of the first ``period`` price changes, then
    smoothed as ``avg = (avg * (period - 1) + change) / period``.
    ``rsi`` is None when prices did not move at all (RSI is undefined).
    """
    if period < 1 or len(prices) < period + 1:
        raise ValueError(f"need {period + 1} prices, have {len(prices)}")
    changes = [b - a for a, b in zip(prices, prices[1:], strict=False)]
    gains = [max(c, 0.0) for c in changes]
    losses = [max(-c, 0.0) for c in changes]
    avg_gain = math.fsum(gains[:period]) / period
    avg_loss = math.fsum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:], strict=True):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return (100.0 if avg_gain > 0 else None), avg_gain, avg_loss
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs), avg_gain, avg_loss


def sma_series(values: Sequence[float], period: int) -> list[float | None]:
    """SMA at every position (None until ``period`` values are available)."""
    if period < 1:
        raise ValueError("period must be >= 1")
    out: list[float | None] = [None] * len(values)
    window = 0.0
    for i, value in enumerate(values):
        window += value
        if i >= period:
            window -= values[i - period]
        if i >= period - 1:
            out[i] = window / period
    # Re-sum exactly at the end so the latest value matches sma() (no drift from the running sum).
    if len(values) >= period:
        out[-1] = sma(values, period)
    return out


def ema_series(values: Sequence[float], period: int) -> list[float | None]:
    """EMA at every position, seeded like ema() (None before the seed)."""
    if period < 1:
        raise ValueError("period must be >= 1")
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    alpha = 2.0 / (period + 1)
    average = math.fsum(values[:period]) / period
    out[period - 1] = average
    for i in range(period, len(values)):
        average += alpha * (values[i] - average)
        out[i] = average
    return out


def sessions_since_cross(fast: Sequence[float | None], slow: Sequence[float | None]) -> int | None:
    """Positions since ``fast`` last moved to its current side of ``slow``.

    0 means the cross happened at the last position. None when the averages
    are equal at the last position, or no cross is found in the series.
    Positions where the averages are exactly equal do not count as a side.
    """
    def side(i: int) -> int:
        f, s = fast[i], slow[i]
        if f is None or s is None:
            return 2  # undefined
        return (f > s) - (f < s)

    last = len(fast) - 1
    current = side(last) if last >= 0 else 2
    if current in (0, 2):
        return None
    became = last  # the earliest position of the current run
    for i in range(last - 1, -1, -1):
        s = side(i)
        if s == 2:
            return None  # ran out of history before finding the cross
        if s == current:
            became = i
        elif s == -current:
            return last - became
    return None
