"""Strategy interface.

A strategy receives normalised market data and a validated configuration and
returns structured results. It must not know about React, API routes,
Parquet, yfinance, dashboard layouts, portfolios or positions.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from app.market_data.models import DailyBar, HistoryResult, LatestPrice
from app.strategies.models import (
    OutputColumn,
    ParameterType,
    StrategyOutput,
    StrategyParameter,
    StrategySchema,
)


class ConfigValidationError(ValueError):
    """Invalid strategy configuration; ``errors`` maps parameter -> message."""

    def __init__(self, errors: dict[str, str]) -> None:
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors = errors


@dataclass(frozen=True)
class StrategyMarketData:
    """Normalised market data supplied by the engine.

    ``closes[ticker]`` holds the completed daily closes strictly before the
    session of the current quote, oldest first, at most the number of
    sessions the strategy asked for.
    """

    quotes: dict[str, LatestPrice | None]
    history: dict[str, HistoryResult] = field(default_factory=dict)

    def quote(self, ticker: str) -> LatestPrice | None:
        return self.quotes.get(ticker)

    def closes(self, ticker: str) -> list[DailyBar]:
        result = self.history.get(ticker)
        return list(result.bars) if result else []

    def history_error(self, ticker: str) -> str | None:
        result = self.history.get(ticker)
        return result.error if result else None


class BaseStrategy(ABC):
    name: ClassVar[str]
    title: ClassVar[str]
    description: ClassVar[str]
    # Longer user-facing explanation shown in the UI (see StrategySchema.explanation).
    explanation: ClassVar[str] = ""
    parameters: ClassVar[tuple[StrategyParameter, ...]] = ()
    outputs: ClassVar[tuple[OutputColumn, ...]] = ()
    # Metric recorded with signal transitions (e.g. "z_score").
    primary_metric: ClassVar[str | None] = None

    def get_config_schema(self) -> StrategySchema:
        return StrategySchema(
            name=self.name,
            title=self.title,
            description=self.description,
            explanation=self.explanation.strip(),
            parameters=list(self.parameters),
            outputs=list(self.outputs),
        )

    def validate_config(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Apply defaults and check every value against the schema, then cross-field rules."""
        errors: dict[str, str] = {}
        known = {p.name: p for p in self.parameters}
        for key in raw:
            if key not in known:
                errors[key] = "unknown parameter"
        config: dict[str, Any] = {}
        for param in self.parameters:
            value = raw.get(param.name, param.default)
            try:
                config[param.name] = coerce_parameter(param, value)
            except ValueError as exc:
                errors[param.name] = str(exc)
        if not errors:
            try:
                self.check_config(config)
            except ConfigValidationError as exc:
                errors.update(exc.errors)
        if errors:
            raise ConfigValidationError(errors)
        return config

    def check_config(self, config: dict[str, Any]) -> None:
        """Override for cross-parameter rules; raise ConfigValidationError."""

    @abstractmethod
    def required_sessions(self, config: dict[str, Any]) -> int:
        """Number of completed daily sessions of history needed (0 if none)."""

    @abstractmethod
    def calculate(
        self, tickers: list[str], market_data: StrategyMarketData, config: dict[str, Any]
    ) -> list[StrategyOutput]:
        """Return one output per ticker. Must not raise for bad data: report a status instead."""


def coerce_parameter(param: StrategyParameter, value: Any) -> Any:
    if param.type is ParameterType.BOOLEAN:
        if not isinstance(value, bool):
            raise ValueError("must be true or false")
        return value
    if param.type is ParameterType.STRING:
        if not isinstance(value, str):
            raise ValueError("must be a string")
        if param.choices is not None and value not in param.choices:
            raise ValueError(f"must be one of {', '.join(param.choices)}")
        return value
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("must be a number")
    if not math.isfinite(value):
        raise ValueError("must be a finite number")
    if param.type is ParameterType.INTEGER:
        if value != int(value):
            raise ValueError("must be an integer")
        value = int(value)
    else:
        value = float(value)
    if param.minimum is not None and value < param.minimum:
        raise ValueError(f"must be at least {param.minimum:g}")
    if param.maximum is not None and value > param.maximum:
        raise ValueError(f"must be at most {param.maximum:g}")
    return value
