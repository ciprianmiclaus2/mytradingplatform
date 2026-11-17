"""FastAPI dependencies giving routes access to services (never to storage)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.market_data.service import MarketDataService
from app.portfolio.service import PortfolioService
from app.brokers.service import BrokerService
from app.refresh.service import RefreshService
from app.strategies.engine import StrategyEngine


def get_market_data_service(request: Request) -> MarketDataService:
    return request.app.state.market_data


MarketData = Annotated[MarketDataService, Depends(get_market_data_service)]


def get_portfolio_service(request: Request) -> PortfolioService:
    return request.app.state.portfolios


Portfolios = Annotated[PortfolioService, Depends(get_portfolio_service)]


def get_broker_service(request: Request) -> BrokerService:
    return request.app.state.brokers


Brokers = Annotated[BrokerService, Depends(get_broker_service)]


def get_strategy_engine(request: Request) -> StrategyEngine:
    return request.app.state.strategies


Strategies = Annotated[StrategyEngine, Depends(get_strategy_engine)]


def get_refresh_service(request: Request) -> RefreshService:
    return request.app.state.refresh


Refresher = Annotated[RefreshService, Depends(get_refresh_service)]
