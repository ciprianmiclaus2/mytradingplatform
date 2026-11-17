"""Broker (SnapTrade) endpoints: settings, accounts, positions and refresh."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import Brokers
from app.brokers.models import (
    BrokerAccounts,
    BrokerPositionsResponse,
    BrokerRefreshResult,
    SnapTradeCredentials,
    SnapTradeStatus,
)

router = APIRouter(prefix="/brokers", tags=["brokers"])


@router.get("/snaptrade/settings", response_model=SnapTradeStatus)
def get_settings(service: Brokers) -> SnapTradeStatus:
    """Whether SnapTrade is set up. Secrets are never returned, only their last 4 characters."""
    return service.status()


@router.put("/snaptrade/settings", response_model=BrokerRefreshResult)
def save_settings(service: Brokers, body: SnapTradeCredentials) -> BrokerRefreshResult:
    """Check the credentials with SnapTrade, save them, and load every account's positions.

    Personal API key: client_id and consumer_key only. Commercial key: also user_id and user_secret.
    Nothing is saved if SnapTrade rejects the credentials.
    """
    return service.configure(body)


@router.delete("/snaptrade/settings", status_code=status.HTTP_204_NO_CONTENT)
def delete_settings(service: Brokers) -> Response:
    """Forget the SnapTrade credentials and all cached accounts and positions."""
    service.disconnect()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/accounts", response_model=BrokerAccounts)
def list_accounts(service: Brokers) -> BrokerAccounts:
    """Accounts as of the last refresh (no SnapTrade call)."""
    return service.accounts()


@router.post("/refresh", response_model=BrokerRefreshResult)
def refresh_all(service: Brokers) -> BrokerRefreshResult:
    """List the accounts, then fetch the positions of each account."""
    return service.refresh_all()


@router.get("/accounts/{account_id}/positions", response_model=BrokerPositionsResponse)
def get_positions(service: Brokers, account_id: str) -> BrokerPositionsResponse:
    """Positions as of the last refresh, valued with the latest market prices (no SnapTrade call)."""
    return service.positions(account_id)


@router.post("/accounts/{account_id}/refresh", response_model=BrokerPositionsResponse)
def refresh_account(service: Brokers, account_id: str) -> BrokerPositionsResponse:
    """List the accounts, then fetch this account's positions from SnapTrade."""
    return service.refresh_account(account_id)
