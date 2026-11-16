"""Position business logic (plan §7)."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum

from app.market_data.service import MarketDataService
from app.persistence.backup import BackupManager
from app.portfolio.models import Portfolio, PortfolioType
from app.portfolio.service import PortfolioService
from app.positions.calculations import currency_totals, position_view, to_decimal
from app.positions.models import (
    Position,
    PositionClose,
    PositionCreate,
    PositionsResponse,
    PositionStatus,
    PositionUpdate,
    PositionView,
)
from app.positions.repository import POSITIONS, PositionRepository
from app.schemas.errors import AppError, ConflictError, NotFoundError

logger = logging.getLogger(__name__)

_EIGHT_DP = Decimal("1e-8")
OPEN_FIELDS = {"quantity", "entry_price", "entry_date", "notes"}
CLOSED_FIELDS = {"exit_price", "exit_date", "notes"}


class StatusFilter(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    ALL = "all"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class PositionService:
    def __init__(
        self,
        repository: PositionRepository,
        portfolios: PortfolioService,
        market_data: MarketDataService,
        backups: BackupManager,
        *,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self.repo = repository
        self.portfolios = portfolios
        self.market_data = market_data
        self.backups = backups
        self.clock = clock
        # Positions portfolios derive their tickers from open positions;
        # deleting a portfolio deletes its positions.
        portfolios.position_tickers = self.open_tickers
        portfolios.on_deleted.append(self._delete_portfolio_positions)

    def today(self) -> date:
        return self.clock().astimezone(UTC).date()

    # -- queries -----------------------------------------------------------------

    def open_tickers(self, portfolio_id: str) -> list[str]:
        """Tickers of open positions, in the order they were opened."""
        return [
            p.ticker for p in self.repo.load()
            if p.portfolio_id == portfolio_id and p.status is PositionStatus.OPEN
        ]

    def list(self, portfolio_id: str, status: StatusFilter = StatusFilter.ALL) -> PositionsResponse:
        self._positions_portfolio(portfolio_id)
        positions = [p for p in self.repo.load() if p.portfolio_id == portfolio_id]
        open_tickers = list(dict.fromkeys(p.ticker for p in positions if p.status is PositionStatus.OPEN))
        prices = self.market_data.get_latest_prices(open_tickers) if open_tickers else {}
        shown = [
            p for p in positions
            if status is StatusFilter.ALL or p.status.value.lower() == status.value
        ]
        return PositionsResponse(
            portfolio_id=portfolio_id,
            positions=[position_view(p, prices.get(p.ticker)) for p in shown],
            totals=currency_totals(positions, prices),
        )

    def get(self, position_id: str) -> PositionView:
        position = _find(self.repo.load(), position_id)
        price = None
        if position.status is PositionStatus.OPEN:
            price = self.market_data.get_latest_prices([position.ticker])[position.ticker]
        return position_view(position, price)

    # -- commands -------------------------------------------------------------------

    def create(self, portfolio_id: str, data: PositionCreate) -> PositionView:
        portfolio = self._positions_portfolio(portfolio_id)
        self._check_no_open(self.repo.load(), portfolio, data.ticker)
        # Validates the ticker and fixes the currency (plan §6.4); may call the provider.
        price = self.market_data.ensure_price(data.ticker)
        entry_price = data.entry_price or _quantize(to_decimal(price.price))
        entry_date = data.entry_date or self.today()
        self._check_date(entry_date, "entry_date")
        now = self.clock()
        position = Position(
            id=uuid.uuid4().hex, portfolio_id=portfolio_id, ticker=data.ticker, currency=price.currency,
            quantity=data.quantity, entry_price=entry_price, entry_date=entry_date,
            status=PositionStatus.OPEN, exit_price=None, exit_date=None, notes=data.notes,
            created_at=now, updated_at=now,
        )

        def change(items: list[Position]) -> list[Position]:
            self._check_no_open(items, portfolio, data.ticker)
            return [*items, position]

        self.repo.modify(change)
        logger.info("position created", extra={"position_id": position.id, "ticker": position.ticker,
                                                "portfolio_id": portfolio_id})
        return self.get(position.id)

    def update(self, position_id: str, data: PositionUpdate) -> PositionView:
        fields = data.model_dump(exclude_unset=True)
        for key in ("quantity", "entry_price", "exit_price", "exit_date", "notes"):
            if key in fields and fields[key] is None:
                raise AppError(f"{key} cannot be null")

        def change(items: list[Position]) -> list[Position]:
            current = _find(items, position_id)
            allowed = OPEN_FIELDS if current.status is PositionStatus.OPEN else CLOSED_FIELDS
            invalid = sorted(set(fields) - allowed)
            if invalid:
                article = "an open" if current.status is PositionStatus.OPEN else "a closed"
                raise AppError(f"Cannot change {', '.join(invalid)} on {article} position")
            updated = current.model_copy(update={**fields, "updated_at": self.clock()})
            self._check_dates(updated)
            return [updated if p.id == position_id else p for p in items]

        self.repo.modify(change)
        logger.info("position updated", extra={"position_id": position_id, "fields": sorted(fields)})
        return self.get(position_id)

    def close(self, position_id: str, data: PositionClose) -> PositionView:
        position = _find(self.repo.load(), position_id)
        if position.status is PositionStatus.CLOSED:
            raise ConflictError("Position is already closed")
        exit_price = data.exit_price
        if exit_price is None:
            price = self.market_data.get_latest_prices([position.ticker])[position.ticker]
            if price is None or price.currency != position.currency:
                raise AppError(f"No current price for {position.ticker}; please supply exit_price")
            exit_price = _quantize(to_decimal(price.price))
        exit_date = data.exit_date or self.today()

        def change(items: list[Position]) -> list[Position]:
            current = _find(items, position_id)
            if current.status is PositionStatus.CLOSED:
                raise ConflictError("Position is already closed")
            closed = current.model_copy(update={
                "status": PositionStatus.CLOSED, "exit_price": exit_price, "exit_date": exit_date,
                "updated_at": self.clock(),
            })
            self._check_dates(closed)
            return [closed if p.id == position_id else p for p in items]

        with self.repo.store.lock.hold():
            self.repo.modify(change)
            self.portfolios.prune_favourites(position.portfolio_id)
        logger.info("position closed", extra={"position_id": position_id, "ticker": position.ticker})
        return self.get(position_id)

    def delete(self, position_id: str) -> None:
        with self.repo.store.lock.hold():
            position = _find(self.repo.load(), position_id)
            self.backups.create_backup(f"before-delete-position-{position.ticker}")
            self.repo.modify(lambda items: [p for p in items if p.id != position_id])
            self.portfolios.prune_favourites(position.portfolio_id)
        logger.info("position deleted", extra={"position_id": position_id, "ticker": position.ticker})

    def _delete_portfolio_positions(self, portfolio_id: str) -> None:
        """Hook: called under the lock when a portfolio is deleted (backup already taken)."""
        removed = 0

        def change(items: list[Position]) -> list[Position]:
            nonlocal removed
            kept = [p for p in items if p.portfolio_id != portfolio_id]
            removed = len(items) - len(kept)
            return kept

        if self.repo.store.exists(POSITIONS):
            self.repo.modify(change)
        if removed:
            logger.info("positions deleted with portfolio", extra={"portfolio_id": portfolio_id, "count": removed})

    # -- validation ---------------------------------------------------------------------

    def _positions_portfolio(self, portfolio_id: str) -> Portfolio:
        portfolio = self.portfolios.get(portfolio_id)
        if portfolio.type is not PortfolioType.POSITIONS:
            raise AppError(f"{portfolio.name} is a watchlist; positions belong to positions portfolios")
        return portfolio

    @staticmethod
    def _check_no_open(items: list[Position], portfolio: Portfolio, ticker: str) -> None:
        if any(p.portfolio_id == portfolio.id and p.ticker == ticker and p.status is PositionStatus.OPEN
               for p in items):
            raise ConflictError(
                f"{portfolio.name} already has an open {ticker} position; edit its quantity and entry price instead"
            )

    def _check_date(self, value: date | None, name: str) -> None:
        if value is not None and value > self.today():
            raise AppError(f"{name} cannot be in the future")

    def _check_dates(self, position: Position) -> None:
        self._check_date(position.entry_date, "entry_date")
        self._check_date(position.exit_date, "exit_date")
        if position.entry_date and position.exit_date and position.exit_date < position.entry_date:
            raise AppError("exit_date cannot be before entry_date")


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_EIGHT_DP)


def _find(items: list[Position], position_id: str) -> Position:
    for p in items:
        if p.id == position_id:
            return p
    raise NotFoundError(f"Position {position_id} not found")
