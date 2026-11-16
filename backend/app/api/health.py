"""Health endpoint."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app import __version__

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    data_schema_version: int
    market_data_provider: str
    server_time: datetime


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        version=__version__,
        environment=settings.app_env.value,
        data_schema_version=request.app.state.data_info.schema_version,
        market_data_provider=settings.market_data_provider,
        server_time=datetime.now(UTC),
    )
