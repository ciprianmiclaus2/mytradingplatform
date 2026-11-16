from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.market_data.base import ProviderError
from app.market_data.service import InvalidTickerError, MarketDataProviderUnavailable, MarketDataService
from app.persistence.backup import BackupManager
from app.persistence.derived import derived_registry
from app.persistence.parquet import ParquetStore
from app.portfolio.models import PortfolioCreate, PortfolioType, PortfolioUpdate, TickerRequest
from app.portfolio.repository import PORTFOLIOS, PortfolioRepository
from app.portfolio.service import PortfolioService
from app.schemas.errors import AppError, ConflictError, NotFoundError
from tests.fakes import FIXED_NOW, FakeProvider


@pytest.fixture
def provider() -> FakeProvider:
    p = FakeProvider()
    for ticker, price in {"AAPL": 215.0, "MSFT": 410.0, "NVDA": 140.0}.items():
        p.set_quote(ticker, price, previous_close=price - 1)
    return p


@pytest.fixture
def market(store: ParquetStore, provider: FakeProvider) -> MarketDataService:
    return MarketDataService(provider, store, derived_registry, archive_threshold=1000, clock=lambda: FIXED_NOW)


@pytest.fixture
def backups(store: ParquetStore) -> BackupManager:
    return BackupManager(store.data_dir, store.lock, retention=10)


@pytest.fixture
def service(store: ParquetStore, market: MarketDataService, backups: BackupManager) -> PortfolioService:
    svc = PortfolioService(PortfolioRepository(store), market, backups, clock=lambda: FIXED_NOW)
    svc.ensure_defaults()
    return svc


def watchlist(service: PortfolioService, name: str = "Tech") -> str:
    return service.create(PortfolioCreate(name=name)).id


# -- defaults ----------------------------------------------------------------------------


def test_defaults_created_on_first_startup_only(service: PortfolioService) -> None:
    assert [(p.name, p.type) for p in service.list()] == [
        ("Main Portfolio", PortfolioType.WATCHLIST),
        ("Main Positions", PortfolioType.POSITIONS),
    ]
    assert service.ensure_defaults() == []  # second startup
    main = service.list(PortfolioType.WATCHLIST)[0]
    service.delete(main.id)
    assert service.ensure_defaults() == []  # not recreated after a deliberate delete
    assert len(service.list()) == 1


def test_list_filters_by_type(service: PortfolioService) -> None:
    watchlist(service)
    assert [p.name for p in service.list(PortfolioType.WATCHLIST)] == ["Main Portfolio", "Tech"]
    assert [p.name for p in service.list(PortfolioType.POSITIONS)] == ["Main Positions"]


# -- create / update / delete ----------------------------------------------------------------


def test_create_and_get(service: PortfolioService) -> None:
    p = service.create(PortfolioCreate(name="  Long   term ", description="Buy and hold", type="positions"))
    got = service.get(p.id)
    assert got.name == "Long term" and got.description == "Buy and hold"
    assert got.type is PortfolioType.POSITIONS and got.tickers == [] and got.favourites == []
    assert got.created_at == FIXED_NOW


@pytest.mark.parametrize("name", ["main portfolio", "MAIN PORTFOLIO", " Main  Portfolio "])
def test_names_unique_case_insensitive(service: PortfolioService, name: str) -> None:
    with pytest.raises(ConflictError, match="already exists"):
        service.create(PortfolioCreate(name=name))


@pytest.mark.parametrize("name", ["", "   ", "x" * 101])
def test_invalid_names_rejected(name: str) -> None:
    with pytest.raises(ValidationError):
        PortfolioCreate(name=name)


def test_update_name_and_description(service: PortfolioService) -> None:
    pid = watchlist(service)
    updated = service.update(pid, PortfolioUpdate(name="Technology", description="d"))
    assert (updated.name, updated.description) == ("Technology", "d")
    assert service.update(pid, PortfolioUpdate(name="technology")).name == "technology"  # own name, new case
    with pytest.raises(ConflictError):
        service.update(pid, PortfolioUpdate(name="Main Positions"))
    with pytest.raises(NotFoundError):
        service.update("nope", PortfolioUpdate(name="x"))


def test_type_cannot_change() -> None:
    assert "type" not in PortfolioUpdate.model_fields


def test_delete_takes_backup_and_runs_hooks(service: PortfolioService, backups: BackupManager) -> None:
    pid = watchlist(service)
    deleted: list[str] = []
    service.on_deleted.append(deleted.append)

    service.delete(pid)

    assert deleted == [pid]
    assert pid not in [p.id for p in service.list()]
    assert any("before-delete-portfolio-tech" in b.name for b in backups.list_backups())
    with pytest.raises(NotFoundError):
        service.get(pid)


def test_last_portfolio_cannot_be_deleted(service: PortfolioService) -> None:
    first, second = service.list()
    service.delete(first.id)
    with pytest.raises(ConflictError, match="last remaining"):
        service.delete(second.id)


# -- tickers -----------------------------------------------------------------------------------


def test_add_ticker_validates_and_caches_price(service: PortfolioService, market: MarketDataService,
                                               provider: FakeProvider) -> None:
    pid = watchlist(service)
    p = service.add_ticker(pid, "AAPL")
    assert p.tickers == ["AAPL"]
    assert market.get_latest_prices(["AAPL"])["AAPL"].price == 215.0  # type: ignore[union-attr]
    service.add_ticker(pid, "MSFT")
    assert service.get(pid).tickers == ["AAPL", "MSFT"]  # insertion order kept


def test_add_ticker_uses_cached_price_without_provider_call(service: PortfolioService, market: MarketDataService,
                                                            provider: FakeProvider) -> None:
    market.refresh(["AAPL"])
    provider.quotes["AAPL"] = ProviderError("down")  # provider now failing
    calls = len(provider.quote_calls)
    service.add_ticker(watchlist(service), "AAPL")
    assert len(provider.quote_calls) == calls


def test_add_unknown_ticker_rejected(service: PortfolioService) -> None:
    pid = watchlist(service)
    with pytest.raises(InvalidTickerError, match="Unknown ticker ZZZZ"):
        service.add_ticker(pid, "ZZZZ")
    assert service.get(pid).tickers == []


def test_add_ticker_when_provider_down(service: PortfolioService, provider: FakeProvider) -> None:
    provider.quotes["AAPL"] = ProviderError("timeout")
    pid = watchlist(service)
    with pytest.raises(MarketDataProviderUnavailable, match="try again"):
        service.add_ticker(pid, "AAPL")
    assert service.get(pid).tickers == []


def test_duplicate_ticker_rejected(service: PortfolioService) -> None:
    pid = watchlist(service)
    service.add_ticker(pid, "AAPL")
    with pytest.raises(ConflictError, match="already in Tech"):
        service.add_ticker(pid, "AAPL")


def test_same_ticker_in_multiple_portfolios(service: PortfolioService) -> None:
    a, b = watchlist(service, "A"), watchlist(service, "B")
    service.add_ticker(a, "AAPL")
    service.add_ticker(b, "AAPL")
    assert service.get(a).tickers == service.get(b).tickers == ["AAPL"]
    assert service.all_tickers() == ["AAPL"]


def test_ticker_symbols_are_normalised() -> None:
    assert TickerRequest(ticker=" aapl ").ticker == "AAPL"
    with pytest.raises(ValidationError):
        TickerRequest(ticker="not a ticker")


def test_remove_ticker_also_removes_favourite(service: PortfolioService) -> None:
    pid = watchlist(service)
    service.add_ticker(pid, "AAPL")
    service.add_ticker(pid, "MSFT")
    service.add_favourite(pid, "AAPL")
    p = service.remove_ticker(pid, "AAPL")
    assert p.tickers == ["MSFT"] and p.favourites == []
    with pytest.raises(NotFoundError):
        service.remove_ticker(pid, "AAPL")


def test_positions_portfolio_tickers_are_read_only(service: PortfolioService) -> None:
    positions = service.list(PortfolioType.POSITIONS)[0]
    with pytest.raises(AppError, match="positions portfolio"):
        service.add_ticker(positions.id, "AAPL")
    with pytest.raises(AppError, match="positions portfolio"):
        service.remove_ticker(positions.id, "AAPL")


def test_positions_portfolio_tickers_come_from_positions(service: PortfolioService) -> None:
    positions = service.list(PortfolioType.POSITIONS)[0]
    service.position_tickers = lambda pid: ["NVDA"] if pid == positions.id else []
    assert service.get(positions.id).tickers == ["NVDA"]
    service.add_favourite(positions.id, "NVDA")
    assert service.get(positions.id).favourites == ["NVDA"]
    assert "NVDA" in service.all_tickers()

    service.position_tickers = lambda pid: []  # position closed
    service.prune_favourites(positions.id)
    assert service.get(positions.id).favourites == []


# -- favourites --------------------------------------------------------------------------------


def test_favourites_are_subset_and_idempotent(service: PortfolioService) -> None:
    pid = watchlist(service)
    service.add_ticker(pid, "AAPL")
    with pytest.raises(AppError, match="only its tickers can be favourites"):
        service.add_favourite(pid, "MSFT")
    service.add_favourite(pid, "AAPL")
    assert service.add_favourite(pid, "AAPL").favourites == ["AAPL"]
    assert service.remove_favourite(pid, "AAPL").favourites == []
    assert service.remove_favourite(pid, "AAPL").favourites == []


# -- quotes ---------------------------------------------------------------------------------------


def test_quotes_rows(service: PortfolioService, market: MarketDataService, provider: FakeProvider) -> None:
    pid = watchlist(service)
    service.add_ticker(pid, "AAPL")
    service.add_ticker(pid, "MSFT")
    service.add_favourite(pid, "MSFT")
    provider.quotes["MSFT"] = ProviderError("down")
    market.refresh(["AAPL", "MSFT"])

    rows = {r.ticker: r for r in service.quotes(pid).rows}

    assert rows["AAPL"].price == 215.0 and rows["AAPL"].daily_change == 1.0
    assert rows["AAPL"].stale is False and rows["AAPL"].favourite is False
    assert rows["MSFT"].price == 410.0 and rows["MSFT"].stale is True and rows["MSFT"].favourite is True


def test_quotes_for_empty_portfolio(service: PortfolioService) -> None:
    assert service.quotes(watchlist(service)).rows == []


# -- persistence ---------------------------------------------------------------------------------------


def test_portfolios_survive_restart(store: ParquetStore, service: PortfolioService, market: MarketDataService,
                                    backups: BackupManager) -> None:
    pid = watchlist(service)
    service.add_ticker(pid, "AAPL")
    service.add_favourite(pid, "AAPL")

    reopened = PortfolioService(PortfolioRepository(store), market, backups)
    assert reopened.ensure_defaults() == []
    assert reopened.get(pid).tickers == ["AAPL"] and reopened.get(pid).favourites == ["AAPL"]
    assert store.read(PORTFOLIOS).schema.field("tickers").type.value_type.equals("string")


def test_failed_change_leaves_file_untouched(store: ParquetStore, service: PortfolioService) -> None:
    path: Path = store.resolve(PORTFOLIOS.path)  # type: ignore[arg-type]
    before = path.read_bytes()
    with pytest.raises(ConflictError):
        service.create(PortfolioCreate(name="Main Portfolio"))
    assert path.read_bytes() == before
