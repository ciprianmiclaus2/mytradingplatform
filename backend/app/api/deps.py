"""FastAPI dependencies giving routes access to services (never to storage)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.market_data.service import MarketDataService
from app.portfolio.service import PortfolioService


def get_market_data_service(request: Request) -> MarketDataService:
    return request.app.state.market_data


MarketData = Annotated[MarketDataService, Depends(get_market_data_service)]


def get_portfolio_service(request: Request) -> PortfolioService:
    return request.app.state.portfolios


Portfolios = Annotated[PortfolioService, Depends(get_portfolio_service)]
