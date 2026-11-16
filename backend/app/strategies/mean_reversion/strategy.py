"""Mean Reversion strategy (plan §9).

For each ticker, over the previous ``lookback_days`` completed sessions
(the current, possibly incomplete session is excluded by the engine):

    mean = average of the regular daily closes
    std  = population standard deviation of those closes
    Z    = (current price - mean) / std

    BUY  when Z <= buy_threshold
    SELL when Z >= sell_threshold
    no signal otherwise

Regular ``close`` prices are used (split-adjusted by the provider, not
dividend-adjusted) so history is comparable with the latest quoted price.
"""

from __future__ import annotations

import math
import statistics
from typing import Any

from app.strategies.base import BaseStrategy, ConfigValidationError, StrategyMarketData
from app.strategies.mean_reversion.config import EXPLANATION, OUTPUTS, PARAMETERS
from app.strategies.models import CalculationStatus, Signal, StrategyOutput
from app.strategies.registry import register_strategy


@register_strategy
class MeanReversionStrategy(BaseStrategy):
    name = "mean_reversion"
    title = "Mean Reversion"
    description = "Z-score of the latest price against the mean and population standard deviation of previous closes"
    explanation = EXPLANATION
    parameters = PARAMETERS
    outputs = OUTPUTS
    primary_metric = "z_score"

    def check_config(self, config: dict[str, Any]) -> None:
        if config["buy_threshold"] >= config["sell_threshold"]:
            raise ConfigValidationError({"buy_threshold": "must be lower than sell_threshold"})

    def required_sessions(self, config: dict[str, Any]) -> int:
        return int(config["lookback_days"])

    def calculate(
        self, tickers: list[str], market_data: StrategyMarketData, config: dict[str, Any]
    ) -> list[StrategyOutput]:
        return [self._evaluate(ticker, market_data, config) for ticker in tickers]

    def _evaluate(self, ticker: str, market_data: StrategyMarketData, config: dict[str, Any]) -> StrategyOutput:
        lookback = int(config["lookback_days"])
        quote = market_data.quote(ticker)
        if quote is None:
            return StrategyOutput(ticker=ticker, status=CalculationStatus.NO_PRICE,
                                  message="No current price; refresh market data")

        error = market_data.history_error(ticker)
        if error:
            return StrategyOutput(ticker=ticker, status=CalculationStatus.DATA_ERROR,
                                  message=f"Historical prices unavailable: {error}")

        bars = market_data.closes(ticker)[-lookback:]
        if len(bars) < lookback:
            return StrategyOutput(
                ticker=ticker, status=CalculationStatus.INSUFFICIENT_DATA,
                message=f"Only {len(bars)} of {lookback} previous sessions available",
            )
        if any(bar.currency != quote.currency for bar in bars):
            return StrategyOutput(
                ticker=ticker, status=CalculationStatus.INVALID_CALCULATION,
                message="Historical prices and current price are in different currencies",
            )

        closes = [bar.close for bar in bars]
        mean = statistics.fmean(closes)
        std = statistics.pstdev(closes)
        if std == 0 or not math.isfinite(std):
            return StrategyOutput(
                ticker=ticker, status=CalculationStatus.INVALID_CALCULATION,
                metrics={"mean": mean, "standard_deviation": std, "z_score": None},
                message="Standard deviation is zero; z-score is undefined",
            )

        z = (quote.price - mean) / std
        signal = None
        if z <= config["buy_threshold"]:
            signal = Signal.BUY
        elif z >= config["sell_threshold"]:
            signal = Signal.SELL
        return StrategyOutput(
            ticker=ticker, status=CalculationStatus.OK, signal=signal,
            metrics={"mean": mean, "standard_deviation": std, "z_score": z},
        )
