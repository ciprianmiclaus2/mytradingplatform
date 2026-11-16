"""Market data provider interface.

Providers translate a vendor API into the application models in
``app.market_data.models``. Vendor-specific structures must not escape a
provider implementation.

Error contract (plan §5.4) — callers must be able to distinguish:

* data retrieved            -> a populated result;
* no data for the request   -> ``HistoricalPrices(bars=[])`` or ``NoPriceDataError``;
* provider request failed   -> ``ProviderError``. Never an empty result.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from app.market_data.models import HistoricalPrices, PriceQuote, TickerSearchResult


class ProviderError(Exception):
    """The provider request failed (network, timeout, rate limit, bad response)."""

    code = "provider_error"

    def __init__(self, message: str, ticker: str | None = None) -> None:
        super().__init__(message)
        self.ticker = ticker


class NoPriceDataError(ProviderError):
    """The provider answered, but has no price for this instrument (e.g. unknown ticker)."""

    code = "no_data"


class BaseMarketDataProvider(ABC):
    name: str

    @abstractmethod
    def search_ticker(self, query: str, limit: int = 10) -> list[TickerSearchResult]: ...

    @abstractmethod
    def get_historical_prices(self, ticker: str, start_date: date, end_date: date) -> HistoricalPrices:
        """Daily bars with ``start_date <= trading_date <= end_date`` (both inclusive)."""

    @abstractmethod
    def get_current_price(self, ticker: str) -> PriceQuote: ...

    def get_current_prices(self, tickers: list[str]) -> dict[str, PriceQuote | ProviderError]:
        """Quotes per ticker; a failure for one ticker never affects the others."""
        results: dict[str, PriceQuote | ProviderError] = {}
        for ticker in tickers:
            try:
                results[ticker] = self.get_current_price(ticker)
            except ProviderError as exc:
                results[ticker] = exc
            except Exception as exc:  # defensive: a provider bug is a provider failure
                results[ticker] = ProviderError(f"Unexpected provider error: {exc}", ticker)
        return results
