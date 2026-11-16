"""MACD: the MACD line (fast EMA − slow EMA) against its signal line.

``sessions_since_cross`` counts sessions since the MACD line moved to its
current side of the signal line.

    Recent cross (default): BUY/SELL by side only if the cross is within
                            ``recent_sessions`` sessions; otherwise no signal
    Trend:                  BUY while MACD > signal line, SELL while below
"""

from __future__ import annotations

from typing import Any

from app.strategies.base import BaseStrategy, ConfigValidationError, StrategyMarketData
from app.strategies.indicators import macd_series, sessions_since_cross
from app.strategies.macd.config import (
    CROSS_SEARCH_SESSIONS,
    EMA_WARMUP_PERIODS,
    EXPLANATION,
    OUTPUTS,
    PARAMETERS,
    TREND,
)
from app.strategies.models import CalculationStatus, Signal, StrategyOutput
from app.strategies.registry import register_strategy
from app.strategies.series import price_series


@register_strategy
class MacdStrategy(BaseStrategy):
    name = "macd"
    title = "MACD"
    description = "Momentum: signals when the MACD line crosses its signal line"
    explanation = EXPLANATION
    parameters = PARAMETERS
    outputs = OUTPUTS
    primary_metric = "histogram_pct"

    def check_config(self, config: dict[str, Any]) -> None:
        if config["fast_period"] >= config["slow_period"]:
            raise ConfigValidationError({"fast_period": "must be shorter than the slow EMA"})

    def required_sessions(self, config: dict[str, Any]) -> int:
        slow, signal = int(config["slow_period"]), int(config["signal_period"])
        return max(slow * EMA_WARMUP_PERIODS, slow + signal) + CROSS_SEARCH_SESSIONS

    def calculate(
        self, tickers: list[str], market_data: StrategyMarketData, config: dict[str, Any]
    ) -> list[StrategyOutput]:
        return [self._evaluate(ticker, market_data, config) for ticker in tickers]

    def _evaluate(self, ticker: str, market_data: StrategyMarketData, config: dict[str, Any]) -> StrategyOutput:
        fast_n, slow_n, signal_n = int(config["fast_period"]), int(config["slow_period"]), int(config["signal_period"])
        # The signal line first exists after slow + signal − 1 values; the current price can be the last one.
        include_current = bool(config["use_current_price"])
        needed = slow_n + signal_n - 1
        series = price_series(ticker, market_data, minimum_closes=needed - 1 if include_current else needed,
                              include_current=include_current)
        if isinstance(series, StrategyOutput):
            return series

        macd_line, signal_line = macd_series(series, fast_n, slow_n, signal_n)
        macd, sig = macd_line[-1], signal_line[-1]
        assert macd is not None and sig is not None  # guaranteed by minimum_closes
        price = series[-1]
        histogram = macd - sig
        since = sessions_since_cross(macd_line, signal_line)
        metrics = {
            "macd": macd, "signal_line": sig, "histogram": histogram,
            "histogram_pct": histogram / price * 100 if price > 0 else None,
            "sessions_since_cross": float(since) if since is not None else None,
        }
        if price <= 0:
            return StrategyOutput(ticker=ticker, status=CalculationStatus.INVALID_CALCULATION, metrics=metrics,
                                  message="The price is not positive")
        side = Signal.BUY if macd > sig else Signal.SELL if macd < sig else None
        if config["signal_mode"] == TREND:
            signal = side
        else:
            signal = side if since is not None and since < int(config["recent_sessions"]) else None
        return StrategyOutput(ticker=ticker, status=CalculationStatus.OK, signal=signal, metrics=metrics)
