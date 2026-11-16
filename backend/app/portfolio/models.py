"""Portfolio (named watchlist) models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.market_data.models import normalise_ticker

NAME_MAX = 100
DESCRIPTION_MAX = 500


class PortfolioType(StrEnum):
    WATCHLIST = "watchlist"
    POSITIONS = "positions"


class Portfolio(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    description: str
    type: PortfolioType
    tickers: list[str] = Field(
        description="Watchlist: maintained by the user. Positions: tickers of open positions (read-only)."
    )
    favourites: list[str] = Field(description="Subset of tickers")
    created_at: datetime
    updated_at: datetime


def _clean_name(value: str) -> str:
    name = " ".join(value.split())
    if not name:
        raise ValueError("Name is required")
    if len(name) > NAME_MAX:
        raise ValueError(f"Name must be at most {NAME_MAX} characters")
    return name


class PortfolioCreate(BaseModel):
    name: str
    description: str = Field(default="", max_length=DESCRIPTION_MAX)
    type: PortfolioType = PortfolioType.WATCHLIST

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _clean_name(value)


class PortfolioUpdate(BaseModel):
    name: str | None = None
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return None if value is None else _clean_name(value)


class TickerRequest(BaseModel):
    ticker: str

    @field_validator("ticker")
    @classmethod
    def _ticker(cls, value: str) -> str:
        return normalise_ticker(value)


class QuoteRow(BaseModel):
    """One row of the Portfolio pane. All values are computed by the backend."""

    ticker: str
    favourite: bool
    price: float | None
    currency: str | None
    previous_close: float | None
    daily_change: float | None
    daily_change_pct: float | None
    timestamp: datetime | None = Field(description="Quote time; None if no price is cached")
    delayed: bool | None
    stale: bool
    last_error: str | None


class PortfolioQuotes(BaseModel):
    portfolio_id: str
    rows: list[QuoteRow]
