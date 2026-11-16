"""Market data endpoints."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, field_validator

from app.api.deps import MarketData
from app.market_data.models import (
    HistoryResult,
    LatestPrice,
    MarketDataStatus,
    RefreshResult,
    TickerSearchResult,
    normalise_ticker,
    normalise_tickers,
)
from app.schemas.errors import AppError

router = APIRouter(prefix="/market-data", tags=["market-data"])

MAX_TICKERS = 200
MAX_HISTORY_DAYS = 366 * 10


def _parse_tickers(raw: str) -> list[str]:
    items = [t for t in raw.split(",") if t.strip()]
    if not items:
        raise AppError("At least one ticker is required")
    if len(items) > MAX_TICKERS:
        raise AppError(f"At most {MAX_TICKERS} tickers per request")
    try:
        return normalise_tickers(items)
    except ValueError as exc:
        raise AppError(str(exc)) from exc


@router.get("/search", response_model=list[TickerSearchResult])
def search(
    service: MarketData,
    q: Annotated[str, Query(min_length=1, max_length=50, description="Symbol or company name")],
    limit: Annotated[int, Query(ge=1, le=25)] = 10,
) -> list[TickerSearchResult]:
    return service.search(q, limit)


class PricesResponse(BaseModel):
    prices: list[LatestPrice]
    missing: list[str] = Field(description="Requested tickers with no cached price yet")


@router.get("/prices", response_model=PricesResponse)
def prices(
    service: MarketData,
    tickers: Annotated[str, Query(description="Comma-separated ticker symbols")],
) -> PricesResponse:
    """Latest cached prices. Does not call the provider; use POST /refresh to update."""
    result = service.get_latest_prices(_parse_tickers(tickers))
    return PricesResponse(
        prices=[p for p in result.values() if p is not None],
        missing=[t for t, p in result.items() if p is None],
    )


@router.get("/history", response_model=HistoryResult)
def history(
    service: MarketData,
    ticker: str,
    start: date | None = None,
    end: date | None = None,
) -> HistoryResult:
    """Completed daily closes, from cache where available. Excludes the current session."""
    try:
        symbol = normalise_ticker(ticker)
    except ValueError as exc:
        raise AppError(str(exc)) from exc
    end = end or datetime.now(UTC).date()
    start = start or end - timedelta(days=365)
    if start > end:
        raise AppError("start must be on or before end")
    if (end - start).days > MAX_HISTORY_DAYS:
        raise AppError("Requested range is too long (maximum 10 years)")
    return service.get_history([symbol], start, end)[symbol]


class RefreshRequest(BaseModel):
    tickers: list[str] = Field(max_length=MAX_TICKERS, description="Tickers to refresh")

    @field_validator("tickers")
    @classmethod
    def _normalise(cls, value: list[str]) -> list[str]:
        return normalise_tickers(value)


@router.post("/refresh", response_model=RefreshResult)
def refresh(service: MarketData, body: RefreshRequest) -> RefreshResult:
    """Fetch the latest prices once per unique ticker. Partial success is reported per ticker."""
    return service.refresh(body.tickers)


@router.get("/status", response_model=MarketDataStatus)
def status(service: MarketData) -> MarketDataStatus:
    return service.status()
