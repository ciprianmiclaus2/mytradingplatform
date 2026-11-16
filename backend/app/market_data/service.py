"""MarketDataService: the application's single entry point for market data.

Sits between callers (API, strategies, portfolio/positions) and the provider:
serves cached data, fetches only what is missing, validates and normalises
provider data, persists it, and reports failures explicitly.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

from app.market_data.base import BaseMarketDataProvider, NoPriceDataError, ProviderError
from app.market_data.cache import (
    PRICE_HISTORY_DERIVED,
    CurrentPriceCache,
    HistoricalCache,
    RefreshStatusStore,
)
from app.market_data.models import (
    DailyBar,
    HistoryResult,
    HistoryStatus,
    LatestPrice,
    MarketDataStatus,
    PriceQuote,
    RefreshOutcome,
    RefreshResult,
    TickerError,
    TickerRefreshState,
    TickerSearchResult,
)
from app.persistence.derived import DerivedRegistry
from app.persistence.errors import PersistenceError
from app.persistence.parquet import ParquetStore
from app.schemas.errors import AppError

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]


class MarketDataProviderUnavailable(AppError):
    status_code = 502
    code = "market_data_provider_unavailable"


class InvalidTickerError(AppError):
    status_code = 422
    code = "invalid_ticker"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _valid_price(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and value > 0


class MarketDataService:
    def __init__(
        self,
        provider: BaseMarketDataProvider,
        store: ParquetStore,
        derived: DerivedRegistry,
        *,
        archive_threshold: int,
        clock: Clock = _utcnow,
    ) -> None:
        self.provider = provider
        self.store = store
        self.derived = derived
        self.clock = clock
        self.history_cache = HistoricalCache(store)
        self.current_cache = CurrentPriceCache(store, archive_threshold)
        self.refresh_status = RefreshStatusStore(store)

    # -- search ----------------------------------------------------------------

    def search(self, query: str, limit: int = 10) -> list[TickerSearchResult]:
        try:
            return self.provider.search_ticker(query.strip(), limit)
        except ProviderError as exc:
            logger.warning("ticker search failed", extra={"query": query, "error": str(exc)})
            raise MarketDataProviderUnavailable(f"Ticker search is unavailable: {exc}") from exc

    # -- history -----------------------------------------------------------------

    def last_complete_date(self) -> date:
        """Latest date treated as a completed session for caching.

        Every major exchange's regular session for UTC date D-1 has closed by
        00:00 UTC on D, so dates before today's UTC date are complete. This is
        conservative (a session that closed earlier today is picked up
        tomorrow) and never caches a partial daily bar.
        """
        return self.clock().astimezone(UTC).date() - timedelta(days=1)

    def get_history(self, tickers: list[str], start: date, end: date) -> dict[str, HistoryResult]:
        """Completed daily closes per ticker for [start, end] (inclusive).

        Missing ranges are fetched from the provider once and cached; cached
        ranges are never re-downloaded. Today's (possibly incomplete) session is
        never included.
        """
        end = min(end, self.last_complete_date())
        errors: dict[str, str] = {}
        wrote = False
        for ticker in tickers:
            try:
                wrote |= self._fill_history(ticker, start, end)
            except ProviderError as exc:
                logger.warning("history fetch failed", extra={"ticker": ticker, "error": str(exc)})
                errors[ticker] = str(exc)
        if wrote:
            self._refresh_history_view()

        cached = self.history_cache.read(tickers, start, end)
        results = {}
        for ticker in tickers:
            bars = sorted(cached[ticker], key=lambda b: b.trading_date)
            if ticker in errors:
                results[ticker] = HistoryResult(ticker=ticker, status=HistoryStatus.ERROR, bars=bars, error=errors[ticker])
            elif not bars:
                results[ticker] = HistoryResult(ticker=ticker, status=HistoryStatus.NO_DATA, bars=[])
            else:
                results[ticker] = HistoryResult(ticker=ticker, status=HistoryStatus.OK, bars=bars)
        return results

    def get_closes_before(self, tickers: list[str], before: date, sessions: int) -> dict[str, HistoryResult]:
        """The last ``sessions`` completed closes strictly before ``before``.

        A result with fewer bars than requested means the provider has no more
        data (insufficient history); the caller decides how to report that.
        """
        if sessions < 1:
            raise ValueError("sessions must be >= 1")
        end = before - timedelta(days=1)
        # ~252 sessions per 365 days, plus room for holidays.
        start = end - timedelta(days=math.ceil(sessions * 365 / 252) + 14)
        results = self.get_history(tickers, start, end)
        return {
            t: r.model_copy(update={"bars": r.bars[-sessions:]}) if r.bars else r for t, r in results.items()
        }

    def _fill_history(self, ticker: str, start: date, end: date) -> bool:
        gaps = self.history_cache.missing_ranges(ticker, self.provider.name, start, end)
        if not gaps:
            logger.debug("history cache hit", extra={"ticker": ticker})
            return False
        fetch_start, fetch_end = gaps[0][0], gaps[-1][1]
        logger.info(
            "history cache miss",
            extra={"ticker": ticker, "start": str(fetch_start), "end": str(fetch_end), "gaps": len(gaps)},
        )
        response = self.provider.get_historical_prices(ticker, fetch_start, fetch_end)
        bars = self._validated_bars(ticker, fetch_start, fetch_end, response.bars)
        self.history_cache.store_fetch(ticker, self.provider.name, fetch_start, fetch_end, bars)
        return True

    def _validated_bars(self, ticker: str, start: date, end: date, bars: list[DailyBar]) -> list[DailyBar]:
        valid: dict[date, DailyBar] = {}
        for bar in bars:
            if bar.ticker != ticker or not start <= bar.trading_date <= end:
                raise ProviderError(f"Provider returned unexpected data for {ticker}", ticker)
            adj_ok = bar.adjusted_close is None or _valid_price(bar.adjusted_close)
            if not (_valid_price(bar.close) and adj_ok and bar.currency):
                logger.warning(
                    "invalid historical bar rejected",
                    extra={"ticker": ticker, "date": str(bar.trading_date), "close": bar.close},
                )
                raise ProviderError(f"Provider returned an invalid price for {ticker} on {bar.trading_date}", ticker)
            valid[bar.trading_date] = bar
        return list(valid.values())

    def _refresh_history_view(self) -> None:
        try:
            self.derived.rebuild(self.store, PRICE_HISTORY_DERIVED.name)
        except PersistenceError:
            # The view is rebuildable; the authoritative close files are already saved.
            logger.exception("history view rebuild failed")

    # -- current prices ------------------------------------------------------------

    def get_latest_prices(self, tickers: list[str]) -> dict[str, LatestPrice | None]:
        """Latest cached quote per ticker (no provider call). None if never fetched."""
        quotes = self.current_cache.latest(tickers)
        states = self.refresh_status.ticker_states()
        result: dict[str, LatestPrice | None] = {}
        for ticker in tickers:
            quote = quotes.get(ticker)
            result[ticker] = self._enrich(quote, states.get(ticker)) if quote else None
        return result

    @staticmethod
    def _enrich(quote: PriceQuote, state: TickerRefreshState | None) -> LatestPrice:
        change = pct = None
        if quote.previous_close:
            change = quote.price - quote.previous_close
            pct = change / quote.previous_close * 100
        failed_since = state is not None and state.last_error is not None
        return LatestPrice(
            **quote.model_dump(),
            daily_change=change,
            daily_change_pct=pct,
            stale=failed_since,
            last_error=state.last_error if failed_since else None,
        )

    def _fetch_quotes(self, tickers: list[str]) -> tuple[list[PriceQuote], list[TickerError]]:
        """Ask the provider once per ticker; validate each quote."""
        responses = self.provider.get_current_prices(tickers) if tickers else {}
        quotes: list[PriceQuote] = []
        errors: list[TickerError] = []
        for ticker in tickers:
            outcome = responses.get(ticker) or ProviderError("No response from provider", ticker)
            if isinstance(outcome, PriceQuote):
                if outcome.ticker != ticker or not _valid_price(outcome.price) or not outcome.currency:
                    errors.append(TickerError(ticker=ticker, code="invalid_price", message="Provider returned an invalid price"))
                    continue
                if outcome.previous_close is not None and not _valid_price(outcome.previous_close):
                    outcome = outcome.model_copy(update={"previous_close": None})
                quotes.append(outcome)
            else:
                code = "no_data" if isinstance(outcome, NoPriceDataError) else "provider_error"
                errors.append(TickerError(ticker=ticker, code=code, message=str(outcome)))
        return quotes, errors

    def refresh(self, tickers: list[str]) -> RefreshResult:
        """Fetch the latest price once per unique ticker and update the cache.

        Partial success is normal: a failed ticker keeps its previous valid
        price (marked stale) and does not affect the others.
        """
        unique = list(dict.fromkeys(tickers))
        started = self.clock()
        logger.info("market data refresh started", extra={"tickers": len(unique)})

        quotes, errors = self._fetch_quotes(unique)
        self.current_cache.append(quotes)
        completed = self.clock()

        if not unique or not errors:
            outcome_status = RefreshOutcome.COMPLETED
        elif quotes:
            outcome_status = RefreshOutcome.PARTIAL
        else:
            outcome_status = RefreshOutcome.FAILED
        result = RefreshResult(
            status=outcome_status,
            started_at=started,
            completed_at=completed,
            tickers_requested=len(unique),
            tickers_updated=len(quotes),
            tickers_failed=len(errors),
            errors=errors,
        )
        self._save_status([q.ticker for q in quotes], errors, completed, result)
        log = logger.warning if errors else logger.info
        log(
            "market data refresh completed",
            extra={"status": result.status.value, "updated": len(quotes), "failed": len(errors)},
        )
        return result

    def ensure_price(self, ticker: str) -> LatestPrice:
        """Return a price for ``ticker``, fetching one if none is cached (plan §6.4).

        Raises ``InvalidTickerError`` if the provider has no data for the ticker,
        or ``MarketDataProviderUnavailable`` if it cannot be reached and no
        price is cached. A fetched quote is stored in the current-price cache.
        """
        cached = self.get_latest_prices([ticker])[ticker]
        if cached is not None:
            return cached
        quotes, errors = self._fetch_quotes([ticker])
        if quotes:
            self.current_cache.append(quotes)
        self._save_status([q.ticker for q in quotes], errors, self.clock(), None)
        if errors:
            err = errors[0]
            if err.code == "provider_error":
                raise MarketDataProviderUnavailable(
                    f"Cannot verify {ticker}: market data provider unavailable, please try again ({err.message})"
                )
            raise InvalidTickerError(f"Unknown ticker {ticker}: no price available from {self.provider.name}")
        price = self.get_latest_prices([ticker])[ticker]
        assert price is not None
        return price

    def _save_status(
        self,
        updated: list[str],
        errors: list[TickerError],
        at: datetime,
        result: RefreshResult | None,
    ) -> None:
        """Record per-ticker refresh state; ``result`` also updates the last refresh."""
        with self.store.lock.hold():
            doc = self.refresh_status.load()
            states = {t: TickerRefreshState.model_validate(s) for t, s in (doc.get("tickers") or {}).items()}
            for ticker in updated:
                states[ticker] = TickerRefreshState(last_attempt_at=at, last_success_at=at, last_error=None)
            for err in errors:
                prev = states.get(err.ticker)
                states[err.ticker] = TickerRefreshState(
                    last_attempt_at=at,
                    last_success_at=prev.last_success_at if prev else None,
                    last_error=err.message,
                )
            doc["tickers"] = {t: s.model_dump(mode="json") for t, s in sorted(states.items())}
            if result is not None:
                doc["last_refresh"] = result.model_dump(mode="json")
                if result.tickers_updated:
                    doc["last_successful_refresh_at"] = result.completed_at.isoformat()
            self.refresh_status.save(doc)

    def status(self) -> MarketDataStatus:
        doc = self.refresh_status.load()
        last = doc.get("last_refresh")
        success = doc.get("last_successful_refresh_at")
        return MarketDataStatus(
            provider=self.provider.name,
            last_refresh=RefreshResult.model_validate(last) if last else None,
            last_successful_refresh_at=datetime.fromisoformat(success) if success else None,
        )
