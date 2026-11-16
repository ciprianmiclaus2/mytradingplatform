"""Strategy endpoints. Generic: adding a strategy needs no new route."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import Strategies
from app.market_data.models import normalise_ticker
from app.schemas.errors import AppError
from app.strategies.models import SignalHistoryPage, StrategyRunRequest, StrategyRunResult, StrategySchema

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.get("", response_model=list[StrategySchema])
def list_strategies(engine: Strategies) -> list[StrategySchema]:
    """Available strategies with their configuration schemas and output columns."""
    return engine.list()


@router.get("/signals", response_model=SignalHistoryPage)
def signal_history(
    engine: Strategies,
    instance_id: str | None = None,
    strategy: str | None = None,
    ticker: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SignalHistoryPage:
    """Recorded signal transitions, newest first."""
    if ticker is not None:
        try:
            ticker = normalise_ticker(ticker)
        except ValueError as exc:
            raise AppError(str(exc)) from exc
    return engine.signals.history(
        instance_id=instance_id, strategy=strategy, ticker=ticker, limit=limit, offset=offset
    )


@router.get("/{name}/schema", response_model=StrategySchema)
def strategy_schema(engine: Strategies, name: str) -> StrategySchema:
    return engine.schema(name)


@router.post("/{name}/run", response_model=StrategyRunResult)
def run_strategy(engine: Strategies, name: str, body: StrategyRunRequest) -> StrategyRunResult:
    """Execute a strategy on a list of tickers, using cached current prices.

    Pass ``instance_id`` (e.g. the dashboard pane id) to record signal transitions.
    """
    return engine.run(name, body.tickers, body.config, body.instance_id)
