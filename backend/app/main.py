"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import brokers, health, market_data, portfolios, strategies
from app.config import Settings, get_settings
from app.datasets import load_dataset_modules
from app.market_data.base import BaseMarketDataProvider
from app.market_data.providers.registry import create_provider
from app.market_data.service import MarketDataService
from app.logging_config import configure_logging
from app.persistence import open_persistence
from app.portfolio.repository import PortfolioRepository
from app.portfolio.service import PortfolioService
from app.brokers.credentials import CredentialStore
from app.brokers.repository import BrokerRepository
from app.brokers.service import BrokerService, ClientFactory
from app.brokers.snaptrade import SnapTradeClient
from app.refresh.service import RefreshService
from app.strategies.engine import StrategyEngine
from app.strategies.registry import StrategyRegistry, discover_strategies, strategy_registry
from app.strategies.signals import SignalStore
from app.schemas.errors import register_error_handlers

logger = logging.getLogger(__name__)

API_PREFIX = "/api"


def create_app(
    settings: Settings | None = None,
    *,
    provider: BaseMarketDataProvider | None = None,
    registry: StrategyRegistry | None = None,
    snaptrade: ClientFactory | None = None,
) -> FastAPI:
    """Build the app. ``provider``, ``registry`` (strategies) and ``snaptrade`` (client factory) override the defaults (tests)."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        load_dataset_modules()
        persistence = open_persistence(
            settings.data_dir,
            lock_timeout=settings.persistence_lock_timeout,
            backup_retention=settings.backup_retention_count,
            backup_on_startup=settings.backup_on_startup,
        )
        app.state.persistence = persistence
        app.state.data_info = persistence.info
        app.state.market_data = MarketDataService(
            provider or create_provider(settings.market_data_provider, settings.market_data_timeout),
            persistence.store,
            persistence.derived,
            archive_threshold=settings.current_price_archive_threshold,
        )
        app.state.portfolios = PortfolioService(
            PortfolioRepository(persistence.store), app.state.market_data, persistence.backups
        )
        app.state.portfolios.remove_legacy_positions_lists()
        app.state.portfolios.ensure_defaults()
        app.state.brokers = BrokerService(
            BrokerRepository(persistence.store),
            CredentialStore(settings.data_dir),
            app.state.market_data,
            snaptrade or (lambda creds: SnapTradeClient(
                creds, base_url=settings.snaptrade_base_url, timeout=settings.snaptrade_timeout)),
        )
        app.state.refresh = RefreshService(app.state.portfolios, app.state.market_data, app.state.brokers.all_tickers)
        if registry is None:
            discover_strategies()
        app.state.strategies = StrategyEngine(
            registry or strategy_registry, app.state.market_data, SignalStore(persistence.store)
        )
        logger.info(
            "application startup",
            extra={
                "version": __version__,
                "env": settings.app_env.value,
                "data_dir": str(settings.data_dir),
                "provider": settings.market_data_provider,
            },
        )
        yield
        logger.info("application shutdown")

    app = FastAPI(
        title="My Trading Platform API",
        version=__version__,
        lifespan=lifespan,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)

    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(market_data.router, prefix=API_PREFIX)
    app.include_router(portfolios.router, prefix=API_PREFIX)
    app.include_router(brokers.router, prefix=API_PREFIX)
    app.include_router(strategies.router, prefix=API_PREFIX)
    return app


def _build_default_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    return create_app(settings)


app = _build_default_app()
