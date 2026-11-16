"""Position endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import Positions
from app.positions.models import PositionClose, PositionCreate, PositionsResponse, PositionUpdate, PositionView
from app.positions.service import StatusFilter

router = APIRouter(tags=["positions"])


@router.get("/portfolios/{portfolio_id}/positions", response_model=PositionsResponse)
def list_positions(
    service: Positions, portfolio_id: str, status: StatusFilter = StatusFilter.ALL
) -> PositionsResponse:
    """Positions with calculated metrics, plus per-currency totals over the whole portfolio."""
    return service.list(portfolio_id, status)


@router.post(
    "/portfolios/{portfolio_id}/positions",
    response_model=PositionView,
    status_code=status.HTTP_201_CREATED,
)
def create_position(service: Positions, portfolio_id: str, body: PositionCreate) -> PositionView:
    """Open a position. The entry price defaults to the latest available price."""
    return service.create(portfolio_id, body)


@router.get("/positions/{position_id}", response_model=PositionView)
def get_position(service: Positions, position_id: str) -> PositionView:
    return service.get(position_id)


@router.put("/positions/{position_id}", response_model=PositionView)
def update_position(service: Positions, position_id: str, body: PositionUpdate) -> PositionView:
    """Edit in place. Open: quantity, entry_price, entry_date, notes. Closed: exit_price, exit_date, notes."""
    return service.update(position_id, body)


@router.post("/positions/{position_id}/close", response_model=PositionView)
def close_position(service: Positions, position_id: str, body: PositionClose | None = None) -> PositionView:
    """Close the whole position. Exit price defaults to the latest price, exit date to today."""
    return service.close(position_id, body or PositionClose())


@router.delete("/positions/{position_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_position(service: Positions, position_id: str) -> Response:
    """Delete an open or closed position (corrections). A backup is taken first."""
    service.delete(position_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
