"""Portfolio endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import Portfolios
from app.market_data.models import normalise_ticker
from app.portfolio.models import (
    Portfolio,
    PortfolioCreate,
    PortfolioQuotes,
    PortfolioType,
    PortfolioUpdate,
    TickerRequest,
)
from app.schemas.errors import AppError

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


def _ticker(raw: str) -> str:
    try:
        return normalise_ticker(raw)
    except ValueError as exc:
        raise AppError(str(exc)) from exc


@router.get("", response_model=list[Portfolio])
def list_portfolios(service: Portfolios, type: PortfolioType | None = None) -> list[Portfolio]:
    return service.list(type)


@router.post("", response_model=Portfolio, status_code=status.HTTP_201_CREATED)
def create_portfolio(service: Portfolios, body: PortfolioCreate) -> Portfolio:
    return service.create(body)


@router.get("/{portfolio_id}", response_model=Portfolio)
def get_portfolio(service: Portfolios, portfolio_id: str) -> Portfolio:
    return service.get(portfolio_id)


@router.put("/{portfolio_id}", response_model=Portfolio)
def update_portfolio(service: Portfolios, portfolio_id: str, body: PortfolioUpdate) -> Portfolio:
    return service.update(portfolio_id, body)


@router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_portfolio(service: Portfolios, portfolio_id: str) -> Response:
    """Delete a portfolio (and, for positions portfolios, its positions). A backup is taken first."""
    service.delete(portfolio_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{portfolio_id}/tickers", response_model=Portfolio, status_code=status.HTTP_201_CREATED)
def add_ticker(service: Portfolios, portfolio_id: str, body: TickerRequest) -> Portfolio:
    """Add a ticker to a watchlist. The ticker is verified with the market data provider."""
    return service.add_ticker(portfolio_id, body.ticker)


@router.delete("/{portfolio_id}/tickers/{ticker}", response_model=Portfolio)
def remove_ticker(service: Portfolios, portfolio_id: str, ticker: str) -> Portfolio:
    return service.remove_ticker(portfolio_id, _ticker(ticker))


@router.put("/{portfolio_id}/favourites/{ticker}", response_model=Portfolio)
def add_favourite(service: Portfolios, portfolio_id: str, ticker: str) -> Portfolio:
    return service.add_favourite(portfolio_id, _ticker(ticker))


@router.delete("/{portfolio_id}/favourites/{ticker}", response_model=Portfolio)
def remove_favourite(service: Portfolios, portfolio_id: str, ticker: str) -> Portfolio:
    return service.remove_favourite(portfolio_id, _ticker(ticker))


@router.get("/{portfolio_id}/quotes", response_model=PortfolioQuotes)
def portfolio_quotes(service: Portfolios, portfolio_id: str) -> PortfolioQuotes:
    """Rows for the Portfolio pane, from cached prices (no provider call)."""
    return service.quotes(portfolio_id)
