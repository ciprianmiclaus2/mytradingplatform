"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import health
from app.config import Settings, get_settings
from app.logging_config import configure_logging
from app.persistence.data_dirs import initialise_data_dirs
from app.schemas.errors import register_error_handlers

logger = logging.getLogger(__name__)

API_PREFIX = "/api"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.data_info = initialise_data_dirs(settings.data_dir)
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
    return app


def _build_default_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    return create_app(settings)


app = _build_default_app()
