"""yfinance (Yahoo Finance) market data provider.

All yfinance/pandas structures are converted to application models here.
Yahoo data is never labelled real-time: ``delayed`` is True when Yahoo reports
a delay and None otherwise.
"""

from __future__ import annotations

import logging
import math
import re
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import yfinance as yf
from yfinance.exceptions import YFTickerMissingError

from app.market_data.base import BaseMarketDataProvider, NoPriceDataError, ProviderError
from app.market_data.models import DailyBar, HistoricalPrices, PriceQuote, TickerSearchResult

logger = logging.getLogger(__name__)

# Derivatives are out of scope for V1 (plan §1.1).
EXCLUDED_INSTRUMENT_TYPES = frozenset({"FUTURE", "OPTION"})

_CURL_PREFIX = re.compile(r"^(Failed to perform, )?curl: \(\d+\) ")
_MAX_ERROR_LENGTH = 160


def _brief(exc: BaseException) -> str:
    """A short, user-facing description of a provider exception.

    HTTP client errors can be long and technical (e.g. curl messages with
    documentation links); the full text is logged at DEBUG level instead.
    """
    text = (str(exc).strip().splitlines() or [type(exc).__name__])[0]
    text = _CURL_PREFIX.sub("", text)
    text = text.split(" See https://", 1)[0].strip() or type(exc).__name__
    if len(text) > _MAX_ERROR_LENGTH:
        text = text[: _MAX_ERROR_LENGTH - 1].rstrip() + "…"
    logger.debug("provider error detail", extra={"detail": str(exc)})
    return text


def _http_status(exc: BaseException) -> int | None:
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def _finite(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


class YFinanceProvider(BaseMarketDataProvider):
    name = "yfinance"

    def __init__(self, timeout: float = 30, max_workers: int = 4) -> None:
        self.timeout = timeout
        self.max_workers = max_workers
        # Make yfinance raise instead of logging and returning empty data, so a
        # failed request is never mistaken for "no data" (plan §5.4).
        yf.config.debug.hide_exceptions = False

    # -- search ----------------------------------------------------------------

    def search_ticker(self, query: str, limit: int = 10) -> list[TickerSearchResult]:
        try:
            search = yf.Search(
                query,
                max_results=limit,
                news_count=0,
                lists_count=0,
                include_cb=False,
                recommended=0,
                timeout=self.timeout,
            )
            quotes = search.quotes or []
        except Exception as exc:
            raise ProviderError(f"Ticker search failed: {_brief(exc)}") from exc
        return [r for q in quotes if (r := self._search_result(q)) is not None]

    def _search_result(self, quote: dict[str, Any]) -> TickerSearchResult | None:
        symbol = quote.get("symbol")
        instrument_type = (quote.get("quoteType") or "").upper()
        if not symbol or not instrument_type or instrument_type in EXCLUDED_INSTRUMENT_TYPES:
            return None
        return TickerSearchResult(
            ticker=str(symbol).upper(),
            name=quote.get("longname") or quote.get("shortname") or str(symbol),
            exchange=quote.get("exchDisp") or quote.get("exchange"),
            currency=quote.get("currency"),
            instrument_type=instrument_type,
            provider=self.name,
        )

    # -- history ---------------------------------------------------------------

    def get_historical_prices(self, ticker: str, start_date: date, end_date: date) -> HistoricalPrices:
        if end_date < start_date:
            return HistoricalPrices(ticker=ticker, bars=[])
        t = yf.Ticker(ticker)
        try:
            frame = t.history(
                start=start_date.isoformat(),
                end=(end_date + timedelta(days=1)).isoformat(),  # yfinance end is exclusive
                interval="1d",
                auto_adjust=False,
                actions=False,
                timeout=self.timeout,
            )
        except YFTickerMissingError:
            # Includes YFPricesMissingError / YFTzMissingError: Yahoo answered with no data.
            return HistoricalPrices(ticker=ticker, bars=[])
        except Exception as exc:
            raise ProviderError(f"History request for {ticker} failed: {_brief(exc)}", ticker) from exc

        if frame is None or frame.empty:
            return HistoricalPrices(ticker=ticker, bars=[])
        try:
            currency = (t.get_history_metadata() or {}).get("currency")
        except Exception as exc:
            raise ProviderError(f"History metadata for {ticker} failed: {_brief(exc)}", ticker) from exc
        if not currency:
            raise ProviderError(f"Provider returned no currency for {ticker}", ticker)
        return HistoricalPrices(ticker=ticker, bars=self._bars(ticker, frame, currency, start_date, end_date))

    def _bars(self, ticker: str, frame: Any, currency: str, start: date, end: date) -> list[DailyBar]:
        fetched_at = datetime.now(UTC)
        bars = []
        has_adj = "Adj Close" in frame.columns
        for index, row in frame.iterrows():
            # Daily index is exchange-local midnight; its date is the session date.
            trading_date = index.date() if hasattr(index, "date") else date.fromisoformat(str(index)[:10])
            close = _finite(row.get("Close"))
            if close is None or not start <= trading_date <= end:
                continue
            bars.append(
                DailyBar(
                    ticker=ticker,
                    trading_date=trading_date,
                    close=close,
                    adjusted_close=_finite(row.get("Adj Close")) if has_adj else None,
                    currency=currency,
                    provider=self.name,
                    fetched_at=fetched_at,
                )
            )
        return bars

    # -- current prices ----------------------------------------------------------

    def get_current_price(self, ticker: str) -> PriceQuote:
        try:
            info = yf.Ticker(ticker).get_info() or {}
        except Exception as exc:
            if _http_status(exc) == 404:
                raise NoPriceDataError(f"No quote available for {ticker}", ticker) from exc
            raise ProviderError(f"Quote request for {ticker} failed: {_brief(exc)}", ticker) from exc
        return self._quote(ticker, info)

    def _quote(self, ticker: str, info: dict[str, Any]) -> PriceQuote:
        price = _finite(info.get("regularMarketPrice"))
        if price is None:
            raise NoPriceDataError(f"No quote available for {ticker}", ticker)
        currency = info.get("currency")
        if not currency:
            raise ProviderError(f"Provider returned no currency for {ticker}", ticker)

        fetched_at = datetime.now(UTC)
        market_time = info.get("regularMarketTime")
        timestamp = (
            datetime.fromtimestamp(market_time, UTC) if isinstance(market_time, int | float) else fetched_at
        )
        trading_date = None
        tz_name = info.get("exchangeTimezoneName")
        if tz_name and isinstance(market_time, int | float):
            try:
                trading_date = timestamp.astimezone(ZoneInfo(tz_name)).date()
            except (KeyError, ValueError):
                logger.warning("unknown exchange timezone", extra={"ticker": ticker, "tz": tz_name})

        delay = _finite(info.get("exchangeDataDelayedBy"))
        return PriceQuote(
            ticker=ticker,
            price=price,
            previous_close=_finite(info.get("regularMarketPreviousClose")),
            currency=str(currency),
            timestamp=timestamp,
            trading_date=trading_date,
            provider=self.name,
            delayed=True if delay and delay > 0 else None,
            fetched_at=fetched_at,
        )

    def get_current_prices(self, tickers: list[str]) -> dict[str, PriceQuote | ProviderError]:
        """Fetch quotes concurrently, bounded by the configured timeout overall."""
        if not tickers:
            return {}
        pool = ThreadPoolExecutor(max_workers=min(self.max_workers, len(tickers)))
        try:
            futures = {t: pool.submit(self.get_current_price, t) for t in tickers}
            wait(futures.values(), timeout=self.timeout)
            results: dict[str, PriceQuote | ProviderError] = {}
            for ticker, future in futures.items():
                if not future.done():
                    future.cancel()
                    results[ticker] = ProviderError(f"Quote request for {ticker} timed out", ticker)
                    continue
                exc = future.exception()
                if exc is None:
                    results[ticker] = future.result()
                elif isinstance(exc, ProviderError):
                    results[ticker] = exc
                else:
                    results[ticker] = ProviderError(f"Unexpected provider error: {_brief(exc)}", ticker)
            return results
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
