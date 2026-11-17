"""Portfolio (named watchlist) business logic."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from app.market_data.service import MarketDataService
from app.persistence.backup import BackupManager
from app.portfolio.models import (
    Portfolio,
    PortfolioCreate,
    PortfolioQuotes,
    PortfolioType,
    PortfolioUpdate,
    QuoteRow,
    RETIRED_POSITIONS_TYPE,
)
from app.portfolio.repository import PortfolioRepository
from app.schemas.errors import AppError, ConflictError, NotFoundError

logger = logging.getLogger(__name__)

DEFAULT_PORTFOLIOS = (("Main Portfolio", PortfolioType.WATCHLIST),)

# Called (under the data lock) after a portfolio is deleted, to remove dependent data.
PortfolioDeleted = Callable[[str], None]


def _utcnow() -> datetime:
    return datetime.now(UTC)


class PortfolioService:
    def __init__(
        self,
        repository: PortfolioRepository,
        market_data: MarketDataService,
        backups: BackupManager,
        *,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self.repo = repository
        self.market_data = market_data
        self.backups = backups
        self.clock = clock
        self.on_deleted: list[PortfolioDeleted] = []

    # -- setup -----------------------------------------------------------------

    def ensure_defaults(self) -> list[Portfolio]:
        """Create the default portfolios on first startup only (no portfolios file yet)."""
        if self.repo.exists():
            return []
        now = self.clock()
        created = [
            Portfolio(id=_new_id(), name=name, description="", type=kind, tickers=[], favourites=[],
                      created_at=now, updated_at=now)
            for name, kind in DEFAULT_PORTFOLIOS
        ]
        self.repo.save(created)
        logger.info("default portfolios created", extra={"portfolios": [p.name for p in created]})
        return created

    def remove_legacy_positions_lists(self) -> list[str]:
        """Remove manual positions lists (replaced by broker accounts). A backup is taken first."""
        if not self.repo.exists():
            return []
        with self.repo.store.lock.hold():
            if not self.repo.drop_type_needed(RETIRED_POSITIONS_TYPE):
                return []
            self.backups.create_backup("before-remove-positions-lists")
            removed = self.repo.drop_type(RETIRED_POSITIONS_TYPE)
        logger.warning("positions lists removed (replaced by broker accounts)", extra={"portfolios": removed})
        return removed

    # -- queries ---------------------------------------------------------------

    def list(self, type: PortfolioType | None = None) -> list[Portfolio]:
        return [p for p in self.repo.load() if type is None or p.type == type]

    def get(self, portfolio_id: str) -> Portfolio:
        return _find(self.repo.load(), portfolio_id)

    def all_tickers(self) -> list[str]:
        """Unique tickers across every portfolio (for market data refresh)."""
        seen: dict[str, None] = {}
        for p in self.list():
            for t in p.tickers:
                seen.setdefault(t, None)
        return list(seen)

    def quotes(self, portfolio_id: str) -> PortfolioQuotes:
        portfolio = self.get(portfolio_id)
        prices = self.market_data.get_latest_prices(portfolio.tickers) if portfolio.tickers else {}
        favourites = set(portfolio.favourites)
        rows = []
        for ticker in portfolio.tickers:
            p = prices.get(ticker)
            rows.append(
                QuoteRow(
                    ticker=ticker,
                    name=p.name if p else None,
                    favourite=ticker in favourites,
                    price=p.price if p else None,
                    currency=p.currency if p else None,
                    previous_close=p.previous_close if p else None,
                    daily_change=p.daily_change if p else None,
                    daily_change_pct=p.daily_change_pct if p else None,
                    timestamp=p.timestamp if p else None,
                    delayed=p.delayed if p else None,
                    stale=p.stale if p else False,
                    last_error=p.last_error if p else None,
                )
            )
        return PortfolioQuotes(portfolio_id=portfolio.id, rows=rows)

    # -- portfolio CRUD ----------------------------------------------------------

    def create(self, data: PortfolioCreate) -> Portfolio:
        now = self.clock()
        portfolio = Portfolio(
            id=_new_id(), name=data.name, description=data.description, type=data.type,
            tickers=[], favourites=[], created_at=now, updated_at=now,
        )

        def change(items: list[Portfolio]) -> list[Portfolio]:
            _check_name_free(items, data.name)
            return [*items, portfolio]

        self.repo.modify(change)
        logger.info("portfolio created", extra={"portfolio_id": portfolio.id, "type": portfolio.type.value})
        return portfolio

    def update(self, portfolio_id: str, data: PortfolioUpdate) -> Portfolio:
        updates = data.model_dump(exclude_none=True)

        def change(items: list[Portfolio]) -> list[Portfolio]:
            current = _find(items, portfolio_id)
            if "name" in updates:
                _check_name_free(items, updates["name"], exclude=portfolio_id)
            return _replace(items, current.model_copy(update={**updates, "updated_at": self.clock()}))

        self.repo.modify(change)
        logger.info("portfolio updated", extra={"portfolio_id": portfolio_id, "fields": sorted(updates)})
        return self.get(portfolio_id)

    def delete(self, portfolio_id: str) -> None:
        with self.repo.store.lock.hold():
            items = self.repo.load()
            target = _find(items, portfolio_id)
            if len(items) == 1:
                raise ConflictError("The last remaining portfolio cannot be deleted")
            self.backups.create_backup(f"before-delete-portfolio-{target.name}")

            self.repo.modify(lambda current: [p for p in current if p.id != portfolio_id])
            for hook in self.on_deleted:
                hook(portfolio_id)
        logger.info("portfolio deleted", extra={"portfolio_id": portfolio_id, "portfolio_name": target.name})

    # -- tickers & favourites --------------------------------------------------------

    def add_ticker(self, portfolio_id: str, ticker: str) -> Portfolio:
        portfolio = self.get(portfolio_id)
        _require_watchlist(portfolio)
        if ticker in portfolio.tickers:
            raise ConflictError(f"{ticker} is already in {portfolio.name}")
        # Validate outside the lock: this may call the provider (plan §6.4).
        self.market_data.ensure_price(ticker)

        def change(items: list[Portfolio]) -> list[Portfolio]:
            current = _find(items, portfolio_id)
            if ticker in current.tickers:
                raise ConflictError(f"{ticker} is already in {current.name}")
            return _replace(items, current.model_copy(
                update={"tickers": [*current.tickers, ticker], "updated_at": self.clock()}))

        self.repo.modify(change)
        logger.info("ticker added", extra={"portfolio_id": portfolio_id, "ticker": ticker})
        return self.get(portfolio_id)

    def remove_ticker(self, portfolio_id: str, ticker: str) -> Portfolio:
        def change(items: list[Portfolio]) -> list[Portfolio]:
            current = _find(items, portfolio_id)
            _require_watchlist(current)
            if ticker not in current.tickers:
                raise NotFoundError(f"{ticker} is not in {current.name}")
            return _replace(items, current.model_copy(update={
                "tickers": [t for t in current.tickers if t != ticker],
                "favourites": [t for t in current.favourites if t != ticker],
                "updated_at": self.clock(),
            }))

        self.repo.modify(change)
        logger.info("ticker removed", extra={"portfolio_id": portfolio_id, "ticker": ticker})
        return self.get(portfolio_id)

    def add_favourite(self, portfolio_id: str, ticker: str) -> Portfolio:
        tickers = self.get(portfolio_id).tickers

        def change(items: list[Portfolio]) -> list[Portfolio]:
            current = _find(items, portfolio_id)
            if ticker not in tickers:
                raise AppError(f"{ticker} is not in {current.name}; only its tickers can be favourites")
            if ticker in current.favourites:
                return items
            return _replace(items, current.model_copy(
                update={"favourites": [*current.favourites, ticker], "updated_at": self.clock()}))

        self.repo.modify(change)
        return self.get(portfolio_id)

    def remove_favourite(self, portfolio_id: str, ticker: str) -> Portfolio:
        def change(items: list[Portfolio]) -> list[Portfolio]:
            current = _find(items, portfolio_id)
            if ticker not in current.favourites:
                return items
            return _replace(items, current.model_copy(update={
                "favourites": [t for t in current.favourites if t != ticker], "updated_at": self.clock()}))

        self.repo.modify(change)
        return self.get(portfolio_id)

    def prune_favourites(self, portfolio_id: str) -> None:
        """Drop favourites that are no longer tickers."""
        valid = set(self.get(portfolio_id).tickers)

        def change(items: list[Portfolio]) -> list[Portfolio]:
            current = _find(items, portfolio_id)
            kept = [t for t in current.favourites if t in valid]
            if kept == current.favourites:
                return items
            return _replace(items, current.model_copy(update={"favourites": kept, "updated_at": self.clock()}))

        self.repo.modify(change)


def _new_id() -> str:
    return uuid.uuid4().hex


def _find(items: list[Portfolio], portfolio_id: str) -> Portfolio:
    for p in items:
        if p.id == portfolio_id:
            return p
    raise NotFoundError(f"Portfolio {portfolio_id} not found")


def _replace(items: list[Portfolio], updated: Portfolio) -> list[Portfolio]:
    return [updated if p.id == updated.id else p for p in items]


def _check_name_free(items: list[Portfolio], name: str, exclude: str | None = None) -> None:
    folded = name.casefold()
    if any(p.name.casefold() == folded and p.id != exclude for p in items):
        raise ConflictError(f"A portfolio named {name!r} already exists")


def _require_watchlist(portfolio: Portfolio) -> None:
    if portfolio.type is not PortfolioType.WATCHLIST:
        raise AppError(f"{portfolio.name} is not a watchlist")
