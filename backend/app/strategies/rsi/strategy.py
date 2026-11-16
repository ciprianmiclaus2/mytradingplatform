"""RSI strategy: Wilder's Relative Strength Index as an oversold/overbought signal.

The price series is the completed daily closes before the current session
(regular closes, as in Mean Reversion) followed by the current price.

    BUY  when RSI <= oversold
    SELL when RSI >= overbought
"""

from __future__ import annotations

from typing import Any

from app.strategies.base import BaseStrategy, ConfigValidationError, StrategyMarketData
from app.strategies.indicators import wilder_rsi
from app.strategies.models import CalculationStatus, Signal, StrategyOutput
from app.strategies.registry import register_strategy
from app.strategies.rsi.config import EXPLANATION, OUTPUTS, PARAMETERS, WARMUP_PERIODS
from app.strategies.series import price_series


@register_strategy
class RsiStrategy(BaseStrategy):
    name = "rsi"
    title = "RSI"
    description = "Relative Strength Index: BUY when oversold, SELL when overbought"
    explanation = EXPLANATION
    parameters = PARAMETERS
    outputs = OUTPUTS
    primary_metric = "rsi"

    def check_config(self, config: dict[str, Any]) -> None:
        if config["oversold"] >= config["overbought"]:
            raise ConfigValidationError({"oversold": "must be lower than the overbought level"})

    def required_sessions(self, config: dict[str, Any]) -> int:
        return int(config["period"]) * WARMUP_PERIODS

    def calculate(
        self, tickers: list[str], market_data: StrategyMarketData, config: dict[str, Any]
    ) -> list[StrategyOutput]:
        return [self._evaluate(ticker, market_data, config) for ticker in tickers]

    def _evaluate(self, ticker: str, market_data: StrategyMarketData, config: dict[str, Any]) -> StrategyOutput:
        period = int(config["period"])
        series = price_series(ticker, market_data, minimum_closes=period, include_current=True)
        if isinstance(series, StrategyOutput):
            return series

        rsi, avg_gain, avg_loss = wilder_rsi(series, period)
        metrics = {"rsi": rsi, "average_gain": avg_gain, "average_loss": avg_loss}
        if rsi is None:
            return StrategyOutput(ticker=ticker, status=CalculationStatus.INVALID_CALCULATION, metrics=metrics,
                                  message="The price did not move during the period; RSI is undefined")
        signal = None
        if rsi <= config["oversold"]:
            signal = Signal.BUY
        elif rsi >= config["overbought"]:
            signal = Signal.SELL
        return StrategyOutput(ticker=ticker, status=CalculationStatus.OK, signal=signal, metrics=metrics)
