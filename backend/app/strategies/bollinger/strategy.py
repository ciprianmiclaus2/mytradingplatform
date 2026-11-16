"""Bollinger Bands.

Bands are calculated over the last ``period`` values of the price series
(completed closes, optionally followed by the current price).

    Mean reversion (default): BUY when price <= lower, SELL when price >= upper
    Breakout:                 BUY when price >= upper, SELL when price <= lower
"""

from __future__ import annotations

from typing import Any

from app.strategies.base import BaseStrategy, StrategyMarketData
from app.strategies.bollinger.config import BREAKOUT, EXPLANATION, OUTPUTS, PARAMETERS, WIDTH_RANK_SESSIONS
from app.strategies.indicators import bollinger
from app.strategies.models import CalculationStatus, Signal, StrategyOutput
from app.strategies.registry import register_strategy
from app.strategies.series import price_series


def _bandwidth(values: list[float], period: int, width: float) -> float | None:
    middle, upper, lower, _ = bollinger(values, period, width)
    return (upper - lower) / middle * 100 if middle > 0 else None


def width_rank(series: list[float], period: int, width: float) -> float | None:
    """Percentage of the previous WIDTH_RANK_SESSIONS bandwidths narrower than the latest one."""
    if len(series) < period + WIDTH_RANK_SESSIONS:
        return None
    current = _bandwidth(series, period, width)
    previous = [_bandwidth(series[: len(series) - k], period, width) for k in range(1, WIDTH_RANK_SESSIONS + 1)]
    if current is None or any(w is None for w in previous):
        return None
    narrower = sum(1 for w in previous if w is not None and w < current)
    return narrower / WIDTH_RANK_SESSIONS * 100


@register_strategy
class BollingerBandsStrategy(BaseStrategy):
    name = "bollinger"
    title = "Bollinger Bands"
    description = "Price against volatility bands around a moving average, with squeeze detection"
    explanation = EXPLANATION
    parameters = PARAMETERS
    outputs = OUTPUTS
    primary_metric = "percent_b"

    def required_sessions(self, config: dict[str, Any]) -> int:
        return int(config["period"]) + WIDTH_RANK_SESSIONS

    def calculate(
        self, tickers: list[str], market_data: StrategyMarketData, config: dict[str, Any]
    ) -> list[StrategyOutput]:
        return [self._evaluate(ticker, market_data, config) for ticker in tickers]

    def _evaluate(self, ticker: str, market_data: StrategyMarketData, config: dict[str, Any]) -> StrategyOutput:
        period, width = int(config["period"]), float(config["width"])
        include_current = bool(config["use_current_price"])
        # The bands need ``period`` values; with the current price, one fewer completed close.
        series = price_series(ticker, market_data, minimum_closes=period - 1 if include_current else period,
                              include_current=include_current)
        if isinstance(series, StrategyOutput):
            return series

        middle, upper, lower, std = bollinger(series, period, width)
        price = series[-1]
        metrics: dict[str, float | None] = {"lower_band": lower, "middle_band": middle, "upper_band": upper,
                                            "percent_b": None, "bandwidth": None, "width_rank": None}
        if std == 0:
            return StrategyOutput(ticker=ticker, status=CalculationStatus.INVALID_CALCULATION, metrics=metrics,
                                  message="The price did not move during the period; the bands have no width")
        if middle <= 0:
            return StrategyOutput(ticker=ticker, status=CalculationStatus.INVALID_CALCULATION, metrics=metrics,
                                  message="The middle band is not positive")
        metrics["percent_b"] = (price - lower) / (upper - lower)
        metrics["bandwidth"] = (upper - lower) / middle * 100
        metrics["width_rank"] = width_rank(series, period, width)

        signal = None
        if price <= lower:
            signal = Signal.SELL if config["signal_mode"] == BREAKOUT else Signal.BUY
        elif price >= upper:
            signal = Signal.BUY if config["signal_mode"] == BREAKOUT else Signal.SELL
        return StrategyOutput(ticker=ticker, status=CalculationStatus.OK, signal=signal, metrics=metrics)
