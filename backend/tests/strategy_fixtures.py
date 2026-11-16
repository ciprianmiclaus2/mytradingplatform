"""Strategies used only by tests."""

from __future__ import annotations

from typing import Any

from app.strategies.base import BaseStrategy, ConfigValidationError, StrategyMarketData
from app.strategies.models import (
    CalculationStatus,
    OutputColumn,
    OutputFormat,
    ParameterType,
    Signal,
    StrategyOutput,
    StrategyParameter,
)


class LevelStrategy(BaseStrategy):
    """BUY below ``level``, SELL above ``level + band``; needs ``lookback`` closes."""

    name = "level_test"
    title = "Level (test)"
    description = "Test strategy comparing price with a fixed level"
    parameters = (
        StrategyParameter(name="lookback", type=ParameterType.INTEGER, title="Lookback", default=3,
                          minimum=1, maximum=50, description="Sessions of history required"),
        StrategyParameter(name="level", type=ParameterType.NUMBER, title="Level", default=100.0),
        StrategyParameter(name="band", type=ParameterType.NUMBER, title="Band", default=10.0, minimum=0),
        StrategyParameter(name="mode", type=ParameterType.STRING, title="Mode", default="normal",
                          choices=["normal", "inverted"]),
        StrategyParameter(name="enabled", type=ParameterType.BOOLEAN, title="Enabled", default=True),
    )
    outputs = (
        OutputColumn(name="average", title="Average", format=OutputFormat.PRICE),
        OutputColumn(name="distance", title="Distance", format=OutputFormat.NUMBER),
    )
    primary_metric = "distance"

    def check_config(self, config: dict[str, Any]) -> None:
        if config["mode"] == "inverted" and config["band"] == 0:
            raise ConfigValidationError({"band": "must be positive in inverted mode"})

    def required_sessions(self, config: dict[str, Any]) -> int:
        return config["lookback"]

    def calculate(self, tickers: list[str], market_data: StrategyMarketData,
                  config: dict[str, Any]) -> list[StrategyOutput]:
        out = []
        for ticker in tickers:
            quote = market_data.quote(ticker)
            if quote is None:
                out.append(StrategyOutput(ticker=ticker, status=CalculationStatus.NO_PRICE))
                continue
            if market_data.history_error(ticker):
                out.append(StrategyOutput(ticker=ticker, status=CalculationStatus.DATA_ERROR,
                                          message=market_data.history_error(ticker)))
                continue
            closes = market_data.closes(ticker)
            if len(closes) < config["lookback"]:
                out.append(StrategyOutput(ticker=ticker, status=CalculationStatus.INSUFFICIENT_DATA,
                                          message=f"{len(closes)} of {config['lookback']} sessions"))
                continue
            distance = quote.price - config["level"]
            signal = None
            if quote.price < config["level"]:
                signal = Signal.BUY
            elif quote.price > config["level"] + config["band"]:
                signal = Signal.SELL
            out.append(StrategyOutput(
                ticker=ticker, status=CalculationStatus.OK, signal=signal,
                metrics={"average": sum(c.close for c in closes) / len(closes), "distance": distance},
            ))
        return out


class BrokenStrategy(BaseStrategy):
    name = "broken_test"
    title = "Broken"
    description = "Always raises"

    def required_sessions(self, config: dict[str, Any]) -> int:
        return 0

    def calculate(self, tickers, market_data, config):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")


class SloppyStrategy(BaseStrategy):
    """Returns a signal with a non-OK status, an unknown ticker, and skips tickers."""

    name = "sloppy_test"
    title = "Sloppy"
    description = "Misbehaving output"

    def required_sessions(self, config: dict[str, Any]) -> int:
        return 0

    def calculate(self, tickers, market_data, config):  # type: ignore[no-untyped-def]
        return [
            StrategyOutput(ticker=tickers[0], status=CalculationStatus.INSUFFICIENT_DATA, signal=Signal.BUY),
            StrategyOutput(ticker="NOT_ASKED", status=CalculationStatus.OK, signal=Signal.SELL),
        ]
