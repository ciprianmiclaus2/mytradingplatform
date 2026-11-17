"""Application-level market data models.

These are the only market data structures the rest of the application sees.
Providers translate their own responses into these models.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-=^&]{0,19}$")


def normalise_ticker(raw: str) -> str:
    """Upper-case and validate a ticker symbol; raises ValueError if invalid."""
    ticker = raw.strip().upper()
    if not _TICKER_RE.match(ticker):
        raise ValueError(f"Invalid ticker symbol {raw!r}")
    return ticker


def normalise_tickers(raw: list[str]) -> list[str]:
    """Normalise and de-duplicate, preserving first-seen order."""
    seen: dict[str, None] = {}
    for item in raw:
        seen.setdefault(normalise_ticker(item), None)
    return list(seen)


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True)


class TickerSearchResult(_Model):
    ticker: str
    name: str
    exchange: str | None
    currency: str | None = Field(description="Not always reported by the provider's search")
    instrument_type: str
    provider: str


class DailyBar(_Model):
    """A completed daily session for one ticker."""

    ticker: str
    trading_date: date
    close: float = Field(description="Regular close (split-adjusted, not dividend-adjusted)")
    adjusted_close: float | None
    currency: str
    provider: str
    fetched_at: datetime


class HistoricalPrices(_Model):
    """Provider response for a historical request. Empty ``bars`` means no data."""

    ticker: str
    bars: list[DailyBar]


class PriceQuote(_Model):
    """Latest available price as reported by the provider."""

    ticker: str
    price: float
    previous_close: float | None = Field(description="Close of the previous regular session")
    currency: str
    timestamp: datetime = Field(description="Time of the quote as reported by the provider (UTC)")
    trading_date: date | None = Field(description="Exchange-local session date of the quote")
    provider: str
    delayed: bool | None = Field(
        description="True if the provider reports a delay; None if unknown. Never claims real-time."
    )
    fetched_at: datetime
    name: str | None = Field(
        default=None, description="Company or fund name, when the provider reports one (kept in its own cache)"
    )


class LatestPrice(PriceQuote):
    """A cached quote enriched for display."""

    daily_change: float | None
    daily_change_pct: float | None
    stale: bool = Field(description="True if the most recent refresh of this ticker failed")
    last_error: str | None = None


class HistoryStatus(StrEnum):
    OK = "OK"
    NO_DATA = "NO_DATA"
    ERROR = "ERROR"


class HistoryResult(_Model):
    ticker: str
    status: HistoryStatus
    bars: list[DailyBar]
    error: str | None = None


class TickerError(_Model):
    ticker: str
    code: str
    message: str


class RefreshOutcome(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class RefreshResult(_Model):
    status: RefreshOutcome
    started_at: datetime
    completed_at: datetime
    tickers_requested: int
    tickers_updated: int
    tickers_failed: int
    errors: list[TickerError]


class TickerRefreshState(_Model):
    last_attempt_at: datetime
    last_success_at: datetime | None
    last_error: str | None


class MarketDataStatus(_Model):
    provider: str
    last_refresh: RefreshResult | None
    last_successful_refresh_at: datetime | None
