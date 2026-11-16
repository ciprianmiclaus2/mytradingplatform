"""Moving average crossover.

Trend side: fast MA above slow MA = up, below = down. ``sessions_since_cross``
counts sessions since the fast MA moved to its current side.

    Recent cross (default): BUY/SELL by side only if the cross is within
                            ``recent_sessions`` sessions; otherwise no signal
    Trend:                  BUY while up, SELL while down
"""

from __future__ import annotations

from typing import Any

from app.strategies.base import BaseStrategy, ConfigValidationError, StrategyMarketData
from app.strategies.indicators import ema_series, sessions_since_cross, sma_series
from app.strategies.ma_crossover.config import (
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
class MovingAverageCrossoverStrategy(BaseStrategy):
    name = "ma_crossover"
    title = "Moving Average Crossover"
    description = "Trend following: signals when a fast moving average crosses a slow one"
    explanation = EXPLANATION
    parameters = PARAMETERS
    outputs = OUTPUTS
    primary_metric = "spread_pct"

    def check_config(self, config: dict[str, Any]) -> None:
        if config["fast_period"] >= config["slow_period"]:
            raise ConfigValidationError({"fast_period": "must be shorter than the slow average"})

    def required_sessions(self, config: dict[str, Any]) -> int:
        # Enough history for the slow average plus the search for the last cross.
        slow = int(config["slow_period"])
        needed = slow + CROSS_SEARCH_SESSIONS
        return max(needed, slow * EMA_WARMUP_PERIODS) if config["average_type"] == "EMA" else needed

    def calculate(
        self, tickers: list[str], market_data: StrategyMarketData, config: dict[str, Any]
    ) -> list[StrategyOutput]:
        return [self._evaluate(ticker, market_data, config) for ticker in tickers]

    def _evaluate(self, ticker: str, market_data: StrategyMarketData, config: dict[str, Any]) -> StrategyOutput:
        fast_n, slow_n = int(config["fast_period"]), int(config["slow_period"])
        series = price_series(ticker, market_data, minimum_closes=slow_n,
                              include_current=bool(config["use_current_price"]))
        if isinstance(series, StrategyOutput):
            return series

        series_fn = ema_series if config["average_type"] == "EMA" else sma_series
        fast_series, slow_series = series_fn(series, fast_n), series_fn(series, slow_n)
        fast, slow = fast_series[-1], slow_series[-1]
        assert fast is not None and slow is not None  # guaranteed by minimum_closes
        if slow <= 0:
            return StrategyOutput(ticker=ticker, status=CalculationStatus.INVALID_CALCULATION,
                                  metrics={"fast_ma": fast, "slow_ma": slow, "spread_pct": None,
                                           "sessions_since_cross": None},
                                  message="The slow average is not positive")
        spread = (fast - slow) / slow * 100
        since = sessions_since_cross(fast_series, slow_series)
        side = Signal.BUY if fast > slow else Signal.SELL if fast < slow else None
        if config["signal_mode"] == TREND:
            signal = side
        else:
            signal = side if since is not None and since < int(config["recent_sessions"]) else None
        return StrategyOutput(
            ticker=ticker, status=CalculationStatus.OK, signal=signal,
            metrics={"fast_ma": fast, "slow_ma": slow, "spread_pct": spread,
                     "sessions_since_cross": float(since) if since is not None else None},
        )
