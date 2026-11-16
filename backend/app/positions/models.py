"""Position models.

Positions are informational records (plan §7): quantity and entry price of a
held ticker, and exit price/date once closed. Stored values are exact
decimals; values returned for display are plain JSON numbers.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.market_data.models import normalise_ticker

NOTES_MAX = 1000

# Matches the stored decimal128(20, 8): up to 12 integer digits, 8 decimals.
PositiveDecimal = Annotated[Decimal, Field(gt=0, max_digits=20, decimal_places=8)]


class PositionStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class Position(BaseModel):
    """Stored position record."""

    model_config = ConfigDict(frozen=True)

    id: str
    portfolio_id: str
    ticker: str
    currency: str
    quantity: Decimal
    entry_price: Decimal
    entry_date: date | None
    status: PositionStatus
    exit_price: Decimal | None
    exit_date: date | None
    notes: str
    created_at: datetime
    updated_at: datetime


# -- requests ----------------------------------------------------------------------


class PositionCreate(BaseModel):
    ticker: str
    quantity: PositiveDecimal
    entry_price: PositiveDecimal | None = Field(
        default=None, description="Defaults to the latest available price"
    )
    entry_date: date | None = Field(default=None, description="Defaults to today")
    notes: str = Field(default="", max_length=NOTES_MAX)

    @field_validator("ticker")
    @classmethod
    def _ticker(cls, value: str) -> str:
        return normalise_ticker(value)


class PositionUpdate(BaseModel):
    """Only the fields sent are changed.

    Open positions: quantity, entry_price, entry_date, notes.
    Closed positions: exit_price, exit_date, notes.
    """

    quantity: PositiveDecimal | None = None
    entry_price: PositiveDecimal | None = None
    entry_date: date | None = None
    exit_price: PositiveDecimal | None = None
    exit_date: date | None = None
    notes: str | None = Field(default=None, max_length=NOTES_MAX)


class PositionClose(BaseModel):
    exit_price: PositiveDecimal | None = Field(default=None, description="Defaults to the latest available price")
    exit_date: date | None = Field(default=None, description="Defaults to today")


# -- responses ----------------------------------------------------------------------


class PositionView(BaseModel):
    """A position with backend-calculated metrics.

    Open positions fill the market fields (null when no price is cached);
    closed positions fill the exit/realised fields.
    """

    id: str
    portfolio_id: str
    ticker: str
    currency: str
    status: PositionStatus
    quantity: float
    entry_price: float
    entry_date: date | None
    notes: str
    cost_basis: float
    # open
    current_price: float | None = None
    previous_close: float | None = None
    price_timestamp: datetime | None = None
    market_value: float | None = None
    unrealised_pnl: float | None = None
    unrealised_pnl_pct: float | None = None
    daily_change: float | None = None
    daily_change_pct: float | None = None
    daily_pnl: float | None = None
    stale: bool = False
    # closed
    exit_price: float | None = None
    exit_date: date | None = None
    realised_pnl: float | None = None
    realised_pnl_pct: float | None = None
    created_at: datetime
    updated_at: datetime


class CurrencyTotals(BaseModel):
    """Totals for one currency. Currencies are never combined."""

    currency: str
    open_positions: int
    closed_positions: int
    market_value: float | None
    cost_basis: float
    unrealised_pnl: float | None
    unrealised_pnl_pct: float | None
    daily_pnl: float | None
    realised_pnl: float
    incomplete: bool = Field(
        description="True if some open positions have no current price or previous close, "
        "so market totals exclude them"
    )


class PositionsResponse(BaseModel):
    portfolio_id: str
    positions: list[PositionView]
    totals: list[CurrencyTotals] = Field(description="Over all positions in the portfolio, per currency")
