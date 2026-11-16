from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.market_data.base import ProviderError
from app.market_data.cache import CURRENT_PRICES
from app.market_data.service import InvalidTickerError, MarketDataProviderUnavailable, MarketDataService
from app.persistence.backup import BackupManager
from app.persistence.derived import derived_registry
from app.persistence.parquet import ParquetStore
from app.portfolio.models import PortfolioCreate, PortfolioType
from app.portfolio.repository import PortfolioRepository
from app.portfolio.service import PortfolioService
from app.positions.models import PositionClose, PositionCreate, PositionStatus, PositionUpdate
from app.positions.repository import POSITIONS, PositionRepository
from app.positions.service import PositionService, StatusFilter
from app.schemas.errors import AppError, ConflictError, NotFoundError
from tests.fakes import FIXED_NOW, FakeProvider

TODAY = FIXED_NOW.date()


@pytest.fixture
def provider() -> FakeProvider:
    p = FakeProvider()
    p.set_quote("AAPL", 215.42, previous_close=218.10)
    p.set_quote("MSFT", 410.0, previous_close=400.0)
    return p


@pytest.fixture
def market(store: ParquetStore, provider: FakeProvider) -> MarketDataService:
    return MarketDataService(provider, store, derived_registry, archive_threshold=1000, clock=lambda: FIXED_NOW)


@pytest.fixture
def backups(store: ParquetStore) -> BackupManager:
    return BackupManager(store.data_dir, store.lock, retention=20)


@pytest.fixture
def portfolios(store: ParquetStore, market: MarketDataService, backups: BackupManager) -> PortfolioService:
    svc = PortfolioService(PortfolioRepository(store), market, backups, clock=lambda: FIXED_NOW)
    svc.ensure_defaults()
    return svc


@pytest.fixture
def service(store: ParquetStore, portfolios: PortfolioService, market: MarketDataService,
            backups: BackupManager) -> PositionService:
    return PositionService(PositionRepository(store), portfolios, market, backups, clock=lambda: FIXED_NOW)


@pytest.fixture
def pid(portfolios: PortfolioService) -> str:
    return portfolios.list(PortfolioType.POSITIONS)[0].id


def create(service: PositionService, pid: str, ticker: str = "AAPL", qty: str = "10", **kw) -> str:  # type: ignore[no-untyped-def]
    return service.create(pid, PositionCreate(ticker=ticker, quantity=Decimal(qty), **kw)).id


# -- create -----------------------------------------------------------------------------------


def test_create_with_defaults(service: PositionService, pid: str) -> None:
    view = service.create(pid, PositionCreate(ticker="aapl", quantity=Decimal("10")))
    assert view.ticker == "AAPL" and view.status is PositionStatus.OPEN
    assert view.entry_price == 215.42  # latest available price
    assert view.entry_date == TODAY and view.currency == "USD"
    assert view.market_value == 2154.2 and view.unrealised_pnl == 0
    assert view.daily_pnl == pytest.approx(-26.8)


def test_create_with_explicit_values(service: PositionService, pid: str) -> None:
    view = service.create(pid, PositionCreate(ticker="AAPL", quantity=Decimal("2.5"), entry_price=Decimal("200"),
                                              entry_date=date(2026, 3, 1), notes="core"))
    assert (view.quantity, view.entry_price, view.entry_date, view.notes) == (2.5, 200, date(2026, 3, 1), "core")
    assert view.unrealised_pnl == pytest.approx(38.55)


def test_create_validates_ticker(service: PositionService, pid: str, provider: FakeProvider) -> None:
    with pytest.raises(InvalidTickerError):
        create(service, pid, "ZZZZ")
    provider.quotes["NVDA"] = ProviderError("down")
    with pytest.raises(MarketDataProviderUnavailable):
        create(service, pid, "NVDA", entry_price=Decimal("100"))
    assert service.list(pid).positions == []


def test_only_one_open_position_per_ticker(service: PositionService, pid: str, portfolios: PortfolioService) -> None:
    create(service, pid)
    with pytest.raises(ConflictError, match="already has an open AAPL position"):
        create(service, pid)
    other = portfolios.create(PortfolioCreate(name="ISA", type=PortfolioType.POSITIONS)).id
    create(service, other)  # same ticker in another positions portfolio is fine


def test_positions_only_in_positions_portfolios(service: PositionService, portfolios: PortfolioService) -> None:
    watch = portfolios.list(PortfolioType.WATCHLIST)[0].id
    with pytest.raises(AppError, match="is a watchlist"):
        create(service, watch)
    with pytest.raises(NotFoundError):
        create(service, "nope")


@pytest.mark.parametrize(
    "kwargs",
    [{"quantity": Decimal(0)}, {"quantity": Decimal(-1)}, {"quantity": Decimal("1.123456789")},
     {"quantity": Decimal(1), "entry_price": Decimal(0)}, {"quantity": Decimal("1e13")}],
)
def test_invalid_values_rejected(kwargs) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValidationError):
        PositionCreate(ticker="AAPL", **kwargs)


def test_future_entry_date_rejected(service: PositionService, pid: str) -> None:
    with pytest.raises(AppError, match="entry_date cannot be in the future"):
        create(service, pid, entry_date=TODAY + timedelta(days=1))


def test_explicit_entry_price_is_kept(service: PositionService, pid: str) -> None:
    view = service.create(pid, PositionCreate(ticker="MSFT", quantity=Decimal(1), entry_price=Decimal("399.5")))
    assert view.entry_price == 399.5


# -- portfolio integration ------------------------------------------------------------------------


def test_portfolio_tickers_follow_open_positions(service: PositionService, pid: str,
                                                 portfolios: PortfolioService) -> None:
    a = create(service, pid, "AAPL")
    create(service, pid, "MSFT")
    assert portfolios.get(pid).tickers == ["AAPL", "MSFT"]
    portfolios.add_favourite(pid, "AAPL")

    service.close(a, PositionClose())

    assert portfolios.get(pid).tickers == ["MSFT"]
    assert portfolios.get(pid).favourites == []  # pruned when the position closed
    assert "AAPL" not in portfolios.all_tickers()


def test_deleting_portfolio_deletes_its_positions(service: PositionService, portfolios: PortfolioService,
                                                  store: ParquetStore) -> None:
    isa = portfolios.create(PortfolioCreate(name="ISA", type=PortfolioType.POSITIONS)).id
    main = portfolios.list(PortfolioType.POSITIONS)[0].id
    create(service, isa, "AAPL")
    keep = create(service, main, "MSFT")

    portfolios.delete(isa)

    assert [r["id"] for r in store.read(POSITIONS).to_pylist()] == [keep]


# -- edit ----------------------------------------------------------------------------------------------


def test_edit_open_position_in_place(service: PositionService, pid: str) -> None:
    position_id = create(service, pid, entry_price=Decimal("200"))
    view = service.update(position_id, PositionUpdate(quantity=Decimal("20"), entry_price=Decimal("210"),
                                                      notes="added more"))
    assert (view.quantity, view.entry_price, view.notes) == (20, 210, "added more")
    assert view.cost_basis == 4200


def test_edit_can_clear_entry_date(service: PositionService, pid: str) -> None:
    position_id = create(service, pid)
    assert service.update(position_id, PositionUpdate(entry_date=None)).entry_date is None


def test_edit_rejects_wrong_fields_for_status(service: PositionService, pid: str) -> None:
    position_id = create(service, pid)
    with pytest.raises(AppError, match="Cannot change exit_price on an open position"):
        service.update(position_id, PositionUpdate(exit_price=Decimal(1)))
    service.close(position_id, PositionClose(exit_price=Decimal("230")))
    with pytest.raises(AppError, match="Cannot change quantity on a closed position"):
        service.update(position_id, PositionUpdate(quantity=Decimal(1)))
    view = service.update(position_id, PositionUpdate(exit_price=Decimal("231"), notes="fixed"))
    assert view.exit_price == 231 and view.notes == "fixed"


def test_edit_rejects_nulls_for_required_fields(service: PositionService, pid: str) -> None:
    position_id = create(service, pid)
    with pytest.raises(AppError, match="quantity cannot be null"):
        service.update(position_id, PositionUpdate(quantity=None))


def test_edit_rejects_exit_before_entry(service: PositionService, pid: str) -> None:
    position_id = create(service, pid, entry_date=date(2026, 6, 1))
    service.close(position_id, PositionClose(exit_date=date(2026, 7, 1)))
    with pytest.raises(AppError, match="exit_date cannot be before entry_date"):
        service.update(position_id, PositionUpdate(exit_date=date(2026, 5, 1)))


# -- close ----------------------------------------------------------------------------------------------


def test_close_with_defaults(service: PositionService, pid: str) -> None:
    position_id = create(service, pid, entry_price=Decimal("200"))
    view = service.close(position_id, PositionClose())
    assert view.status is PositionStatus.CLOSED
    assert view.exit_price == 215.42 and view.exit_date == TODAY
    assert view.realised_pnl == pytest.approx(154.2)
    with pytest.raises(ConflictError, match="already closed"):
        service.close(position_id, PositionClose())


def test_close_without_price_requires_exit_price(service: PositionService, pid: str, store: ParquetStore,
                                                 market: MarketDataService, provider: FakeProvider) -> None:
    position_id = create(service, pid)
    store.delete(CURRENT_PRICES)  # no cached price any more
    with pytest.raises(AppError, match="please supply exit_price"):
        service.close(position_id, PositionClose())
    assert service.close(position_id, PositionClose(exit_price=Decimal("220"))).realised_pnl == pytest.approx(45.8)


def test_reopen_after_close(service: PositionService, pid: str) -> None:
    first = create(service, pid)
    service.close(first, PositionClose())
    second = create(service, pid, qty="3")
    listing = service.list(pid)
    assert {p.id: p.status for p in listing.positions} == {first: PositionStatus.CLOSED, second: PositionStatus.OPEN}


# -- delete ----------------------------------------------------------------------------------------------


def test_delete_takes_backup(service: PositionService, pid: str, backups: BackupManager,
                             portfolios: PortfolioService) -> None:
    position_id = create(service, pid)
    portfolios.add_favourite(pid, "AAPL")
    service.delete(position_id)
    with pytest.raises(NotFoundError):
        service.get(position_id)
    assert any("before-delete-position-aapl" in b.name for b in backups.list_backups())
    assert portfolios.get(pid).favourites == []


def test_delete_closed_position(service: PositionService, pid: str) -> None:
    position_id = create(service, pid)
    service.close(position_id, PositionClose())
    service.delete(position_id)
    assert service.list(pid).positions == []


# -- listing --------------------------------------------------------------------------------------------


def test_list_filters_and_totals(service: PositionService, pid: str) -> None:
    a = create(service, pid, "AAPL", entry_price=Decimal("200"))
    create(service, pid, "MSFT", qty="2", entry_price=Decimal("400"))
    service.close(a, PositionClose(exit_price=Decimal("220")))

    everything = service.list(pid)
    assert len(everything.positions) == 2
    assert [p.ticker for p in service.list(pid, StatusFilter.OPEN).positions] == ["MSFT"]
    assert [p.ticker for p in service.list(pid, StatusFilter.CLOSED).positions] == ["AAPL"]
    # Totals always cover the whole portfolio, regardless of the filter.
    [usd] = service.list(pid, StatusFilter.OPEN).totals
    assert usd.realised_pnl == 200 and usd.market_value == 820 and usd.unrealised_pnl == 20
    assert usd.daily_pnl == 20


def test_stale_price_is_flagged(service: PositionService, pid: str, market: MarketDataService,
                                provider: FakeProvider) -> None:
    create(service, pid)
    provider.quotes["AAPL"] = ProviderError("down")
    market.refresh(["AAPL"])
    [view] = service.list(pid).positions
    assert view.stale is True and view.current_price == 215.42


def test_decimals_stored_exactly(service: PositionService, pid: str, store: ParquetStore) -> None:
    create(service, pid, qty="0.12345678", entry_price=Decimal("123.45678901"))
    row = store.read(POSITIONS).to_pylist()[0]
    assert row["quantity"] == Decimal("0.12345678") and row["entry_price"] == Decimal("123.45678901")
