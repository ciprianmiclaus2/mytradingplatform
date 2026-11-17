"""In-memory market data provider for tests (never calls the network)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.market_data.base import BaseMarketDataProvider, NoPriceDataError, ProviderError
from app.market_data.models import DailyBar, HistoricalPrices, PriceQuote, TickerSearchResult

FIXED_NOW = datetime(2026, 11, 16, 15, 0, tzinfo=UTC)  # Monday


class FakeProvider(BaseMarketDataProvider):
    name = "fake"

    def __init__(self) -> None:
        self.closes: dict[str, dict[date, float]] = {}
        self.quotes: dict[str, PriceQuote | ProviderError] = {}
        self.history_failures: dict[str, ProviderError] = {}
        self.search_results: list[TickerSearchResult] = []
        self.search_error: ProviderError | None = None
        self.history_calls: list[tuple[str, date, date]] = []
        self.quote_calls: list[list[str]] = []
        self.currency = "USD"

    # -- configuration helpers ------------------------------------------------------

    def set_closes(self, ticker: str, closes: dict[date, float]) -> None:
        self.closes[ticker] = dict(closes)

    def set_quote(
        self,
        ticker: str,
        price: float,
        previous_close: float | None = None,
        timestamp: datetime = FIXED_NOW,
        delayed: bool | None = True,
        name: str | None = None,
    ) -> None:
        self.quotes[ticker] = PriceQuote(
            ticker=ticker,
            price=price,
            previous_close=previous_close,
            currency=self.currency,
            timestamp=timestamp,
            trading_date=timestamp.date(),
            provider=self.name,
            delayed=delayed,
            fetched_at=FIXED_NOW,
            name=name,
        )

    # -- provider interface ---------------------------------------------------------------

    def search_ticker(self, query: str, limit: int = 10) -> list[TickerSearchResult]:
        if self.search_error:
            raise self.search_error
        return self.search_results[:limit]

    def get_historical_prices(self, ticker: str, start_date: date, end_date: date) -> HistoricalPrices:
        self.history_calls.append((ticker, start_date, end_date))
        if ticker in self.history_failures:
            raise self.history_failures[ticker]
        bars = [
            DailyBar(
                ticker=ticker,
                trading_date=d,
                close=c,
                adjusted_close=c * 0.99 if c > 0 else c,
                currency=self.currency,
                provider=self.name,
                fetched_at=FIXED_NOW,
            )
            for d, c in sorted(self.closes.get(ticker, {}).items())
            if start_date <= d <= end_date
        ]
        return HistoricalPrices(ticker=ticker, bars=bars)

    def get_current_price(self, ticker: str) -> PriceQuote:
        outcome = self.quotes.get(ticker)
        if outcome is None:
            raise NoPriceDataError(f"No quote available for {ticker}", ticker)
        if isinstance(outcome, ProviderError):
            raise outcome
        return outcome

    def get_current_prices(self, tickers: list[str]) -> dict[str, PriceQuote | ProviderError]:
        self.quote_calls.append(list(tickers))
        return super().get_current_prices(tickers)


class OtherFakeProvider(FakeProvider):
    """A second provider implementation, to show providers are interchangeable."""

    name = "other"
