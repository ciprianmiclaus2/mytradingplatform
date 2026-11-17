"""Global refresh: work out every ticker the dashboard needs, then refresh each once.

The required tickers are every watchlist's tickers, the tickers held in
broker accounts (as of their last SnapTrade refresh), plus symbols the
frontend sends for strategy panes, which live in browser storage. Market data and portfolio services stay
independent; this service is the only place that combines them.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from app.market_data.models import RefreshResult
from app.market_data.service import MarketDataService
from app.portfolio.service import PortfolioService
from app.schemas.errors import ConflictError

logger = logging.getLogger(__name__)


class RefreshInProgressError(ConflictError):
    code = "refresh_in_progress"


class RefreshService:
    def __init__(
        self,
        portfolios: PortfolioService,
        market_data: MarketDataService,
        broker_tickers: Callable[[], list[str]] = list,
    ) -> None:
        self.portfolios = portfolios
        self.market_data = market_data
        self.broker_tickers = broker_tickers
        self._running = threading.Lock()

    def required_tickers(self, extra_tickers: list[str]) -> list[str]:
        """Unique tickers: portfolios, then broker accounts, then extras, in a stable order."""
        seen: dict[str, None] = dict.fromkeys(self.portfolios.all_tickers())
        for ticker in [*self.broker_tickers(), *extra_tickers]:
            seen.setdefault(ticker, None)
        return list(seen)

    def refresh(self, extra_tickers: list[str]) -> RefreshResult:
        """Refresh all required tickers. Only one refresh runs at a time."""
        if not self._running.acquire(blocking=False):
            raise RefreshInProgressError("A refresh is already in progress")
        try:
            tickers = self.required_tickers(extra_tickers)
            logger.info(
                "dashboard refresh",
                extra={"tickers": len(tickers), "extra_tickers": len(extra_tickers)},
            )
            return self.market_data.refresh(tickers)
        finally:
            self._running.release()
