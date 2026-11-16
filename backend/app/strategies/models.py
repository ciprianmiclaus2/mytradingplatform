"""Strategy configuration schemas and standard result models (JSON-serialisable)."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.market_data.models import normalise_tickers

INSTANCE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
MAX_TICKERS = 200


# -- configuration schema ---------------------------------------------------------


class ParameterType(StrEnum):
    INTEGER = "integer"
    NUMBER = "number"
    STRING = "string"
    BOOLEAN = "boolean"


class StrategyParameter(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    type: ParameterType
    title: str
    description: str = ""
    default: int | float | str | bool
    minimum: float | None = None
    maximum: float | None = None
    choices: list[str] | None = Field(default=None, description="Allowed values (string parameters)")


class OutputFormat(StrEnum):
    PRICE = "price"
    NUMBER = "number"
    PERCENT = "percent"
    INTEGER = "integer"
    TEXT = "text"


class OutputColumn(BaseModel):
    """A strategy-specific result column, so the frontend can render results generically."""

    model_config = ConfigDict(frozen=True)

    name: str
    title: str
    format: OutputFormat = OutputFormat.NUMBER
    description: str = ""


class StrategySchema(BaseModel):
    name: str
    title: str
    description: str
    explanation: str = Field(
        default="",
        description="User-facing explanation. Plain text: paragraphs separated by blank lines, "
        "'## ' starts a heading, '- ' starts a bullet",
    )
    parameters: list[StrategyParameter]
    outputs: list[OutputColumn] = Field(description="Strategy-specific metric columns, in display order")


# -- results ------------------------------------------------------------------------


class Signal(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class CalculationStatus(StrEnum):
    OK = "OK"
    NO_PRICE = "NO_PRICE"  # no current price cached for the ticker
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID_CALCULATION = "INVALID_CALCULATION"
    DATA_ERROR = "DATA_ERROR"  # market data could not be retrieved


class StrategyOutput(BaseModel):
    """What a strategy returns per ticker. The engine adds price and signal-history fields."""

    ticker: str
    status: CalculationStatus
    signal: Signal | None = None
    metrics: dict[str, float | None] = Field(default_factory=dict)
    message: str | None = None


class TickerResult(BaseModel):
    ticker: str
    status: CalculationStatus
    signal: Signal | None = Field(description="Current condition, not a trade instruction. Null = no signal")
    message: str | None
    current_price: float | None
    currency: str | None
    daily_change: float | None
    daily_change_pct: float | None
    price_timestamp: datetime | None
    stale: bool
    metrics: dict[str, float | None]
    # Signal history (only when the run has an instance_id).
    previous_signal: Signal | None = None
    signal_changed_at: datetime | None = Field(
        default=None, description="When the current signal state began (first recorded transition)"
    )
    is_new_signal: bool = Field(default=False, description="The signal state changed in this run")


class StrategyRunResult(BaseModel):
    strategy: str
    instance_id: str | None
    config: dict[str, Any] = Field(description="Validated configuration, defaults applied")
    calculated_at: datetime
    results: list[TickerResult]


class StrategyRunRequest(BaseModel):
    tickers: list[str] = Field(max_length=MAX_TICKERS)
    config: dict[str, Any] = Field(default_factory=dict)
    instance_id: str | None = Field(
        default=None, description="Stable id of the strategy instance (e.g. dashboard pane); enables signal history"
    )

    @field_validator("tickers")
    @classmethod
    def _tickers(cls, value: list[str]) -> list[str]:
        return normalise_tickers(value)

    @field_validator("instance_id")
    @classmethod
    def _instance(cls, value: str | None) -> str | None:
        if value is not None and not INSTANCE_ID_RE.match(value):
            raise ValueError("instance_id must be 1-64 characters: letters, digits, '_' or '-'")
        return value


class SignalEvent(BaseModel):
    id: str
    instance_id: str
    strategy: str
    ticker: str
    previous_signal: Signal | None
    new_signal: Signal | None
    metric_name: str | None
    metric_value: float | None
    current_price: float | None
    timestamp: datetime


class SignalHistoryPage(BaseModel):
    items: list[SignalEvent]
    total: int
    limit: int
    offset: int
