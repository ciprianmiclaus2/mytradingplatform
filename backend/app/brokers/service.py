"""Broker positions through SnapTrade: settings, refresh (accounts, then positions per account), valuation."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.brokers.credentials import CredentialStore
from app.brokers.mapping import to_position
from app.brokers.models import (
    AccountRefreshError,
    BrokerAccount,
    BrokerAccounts,
    BrokerAccountView,
    BrokerPosition,
    BrokerPositionsResponse,
    BrokerRefreshResult,
    SnapTradeCredentials,
    SnapTradeStatus,
)
from app.brokers.repository import BrokerRepository
from app.brokers.snaptrade import SnapTradeAuthError, SnapTradeClient, SnapTradeError
from app.brokers.valuation import currency_totals, live_quote, position_view
from app.market_data.service import MarketDataService
from app.schemas.errors import AppError, ConflictError, NotFoundError

logger = logging.getLogger(__name__)

ClientFactory = Callable[[SnapTradeCredentials], SnapTradeClient]
_STORE_PLACES = Decimal("1e-10")


class SnapTradeNotConfiguredError(AppError):
    status_code = 409
    code = "snaptrade_not_configured"


class SnapTradeCredentialsRejectedError(AppError):
    status_code = 422
    code = "snaptrade_credentials_rejected"


class BrokerRefreshInProgressError(ConflictError):
    code = "broker_refresh_in_progress"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _to_account(item: dict[str, Any], now: datetime, previous: BrokerAccount | None) -> BrokerAccount | None:
    account_id = _text(item.get("id"))
    if account_id is None:
        return None
    number = _text(item.get("masked_account_number")) or _text(item.get("number")) or ""
    kind = _text(item.get("kind")) or "investment"
    name = _text(item.get("display_name")) or _text(item.get("name")) or (f"{kind.title()} {number}".strip())
    net = item.get("net_value") if isinstance(item.get("net_value"), dict) else {}
    amount = net.get("amount")
    try:
        net_value = float(amount) if amount is not None else None
    except (TypeError, ValueError):
        net_value = None
    return BrokerAccount(
        id=account_id,
        name=name[:200],
        number=number[:50],
        status=_text(item.get("status")),
        kind=kind,
        net_value=net_value,
        net_value_currency=_text(net.get("currency")),
        listed_at=now,
        positions_refreshed_at=previous.positions_refreshed_at if previous else None,
        data_as_of=previous.data_as_of if previous else None,
    )


def _for_storage(position: BrokerPosition) -> BrokerPosition:
    q = _STORE_PLACES
    return position.model_copy(update={
        "units": position.units.quantize(q),
        "price": position.price.quantize(q) if position.price is not None else None,
        "cost_basis": position.cost_basis.quantize(q) if position.cost_basis is not None else None,
        "multiplier": position.multiplier.quantize(q),
    })


class BrokerService:
    def __init__(
        self,
        repository: BrokerRepository,
        credentials: CredentialStore,
        market_data: MarketDataService,
        client_factory: ClientFactory,
        *,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self.repo = repository
        self.credentials = credentials
        self.market_data = market_data
        self.client_factory = client_factory
        self.clock = clock
        self._refreshing = threading.Lock()

    # -- settings ------------------------------------------------------------------

    def status(self) -> SnapTradeStatus:
        return self.credentials.status()

    def configure(self, credentials: SnapTradeCredentials) -> BrokerRefreshResult:
        """Check the credentials by listing accounts, save them, then load every account's positions."""
        with self._exclusive():
            client = self.client_factory(credentials)
            try:
                listed = client.list_accounts()  # nothing is saved if this fails
            except SnapTradeAuthError as exc:
                raise SnapTradeCredentialsRejectedError(
                    exc.message.replace("Check the SnapTrade settings.", "Check the values you entered.")) from exc
            self.credentials.save(credentials)
            self.repo.clear()
            return self._refresh_all(client, listed)

    def disconnect(self) -> None:
        """Remove the stored credentials and all cached broker data."""
        with self._exclusive():
            self.credentials.delete()
            self.repo.clear()

    # -- queries -------------------------------------------------------------------

    def accounts(self) -> BrokerAccounts:
        configured = self.credentials.load() is not None
        return BrokerAccounts(
            configured=configured,
            accounts=self._account_views() if configured else [],
            accounts_refreshed_at=self.repo.accounts_refreshed_at() if configured else None,
        )

    def all_tickers(self) -> list[str]:
        """Market data tickers held across all accounts (for the dashboard refresh)."""
        seen: dict[str, None] = {}
        for p in self.repo.positions():
            if p.ticker:
                seen.setdefault(p.ticker, None)
        return list(seen)

    def positions(self, account_id: str) -> BrokerPositionsResponse:
        account = self._account(account_id)
        stored = self.repo.positions(account_id)
        tickers = sorted({p.ticker for p in stored if p.ticker})
        prices = self.market_data.get_latest_prices(tickers) if tickers else {}
        views = [position_view(p, live_quote(p, prices), account.data_as_of) for p in stored]
        return BrokerPositionsResponse(account=account, positions=views, totals=currency_totals(views))

    # -- refresh -------------------------------------------------------------------

    def refresh_all(self) -> BrokerRefreshResult:
        """List the accounts, then fetch each account's positions."""
        with self._exclusive():
            client = self._client()
            return self._refresh_all(client, client.list_accounts())

    def refresh_account(self, account_id: str) -> BrokerPositionsResponse:
        """List the accounts (to keep account details current), then fetch this account's positions."""
        with self._exclusive():
            client = self._client()
            accounts = self._store_accounts(client.list_accounts())
            if not any(a.id == account_id for a in accounts):
                raise NotFoundError("This account is no longer listed by SnapTrade")
            self._refresh_positions(client, account_id)
        return self.positions(account_id)

    # -- internals -----------------------------------------------------------------

    def _refresh_all(self, client: SnapTradeClient, listed: list[dict[str, Any]]) -> BrokerRefreshResult:
        accounts = self._store_accounts(listed)
        errors: list[AccountRefreshError] = []
        for account in accounts:
            try:
                self._refresh_positions(client, account.id)
            except SnapTradeError as exc:
                errors.append(AccountRefreshError(account_id=account.id, account_name=account.name, message=exc.message))
        logger.info("broker refresh", extra={"accounts": len(accounts), "failed": len(errors)})
        return BrokerRefreshResult(
            accounts=self._account_views(), errors=errors, accounts_refreshed_at=self.repo.accounts_refreshed_at() or self.clock()
        )

    def _store_accounts(self, listed: list[dict[str, Any]]) -> list[BrokerAccount]:
        now = self.clock()
        previous = {a.id: a for a in self.repo.accounts()}
        accounts = [a for item in listed if (a := _to_account(item, now, previous.get(_text(item.get("id")) or ""))) is not None]
        unique = list({a.id: a for a in accounts}.values())
        self.repo.modify_accounts(lambda _: unique)
        gone = set(previous) - {a.id for a in unique}
        if gone:
            self.repo.replace_positions(gone, [])
            logger.info("broker accounts no longer listed", extra={"accounts": len(gone)})
        self.repo.set_accounts_refreshed_at(now)
        return unique

    def _refresh_positions(self, client: SnapTradeClient, account_id: str) -> None:
        items, as_of = client.account_positions(account_id)
        positions = [_for_storage(p) for item in items if (p := to_position(account_id, item)) is not None]
        self.repo.replace_positions({account_id}, positions)
        now = self.clock()

        def stamp(accounts: list[BrokerAccount]) -> list[BrokerAccount]:
            return [
                a.model_copy(update={"positions_refreshed_at": now, "data_as_of": _parse_time(as_of)}) if a.id == account_id else a
                for a in accounts
            ]

        self.repo.modify_accounts(stamp)
        logger.info("broker positions refreshed", extra={"account_id": account_id, "positions": len(positions),
                                                         "skipped": len(items) - len(positions)})

    def _account_views(self) -> list[BrokerAccountView]:
        tickers: dict[str, dict[str, None]] = {}
        for p in self.repo.positions():
            if p.ticker:
                tickers.setdefault(p.account_id, {}).setdefault(p.ticker, None)
        return [
            BrokerAccountView(**a.model_dump(), tickers=list(tickers.get(a.id, {})))
            for a in sorted(self.repo.accounts(), key=lambda a: (a.name.casefold(), a.number))
        ]

    def _account(self, account_id: str) -> BrokerAccount:
        if self.credentials.load() is None:
            raise SnapTradeNotConfiguredError("SnapTrade is not set up")
        for a in self.repo.accounts():
            if a.id == account_id:
                return a
        raise NotFoundError("This account is not listed. Refresh, or choose another account.")

    def _client(self) -> SnapTradeClient:
        creds = self.credentials.load()
        if creds is None:
            raise SnapTradeNotConfiguredError("SnapTrade is not set up")
        return self.client_factory(creds)

    @contextmanager
    def _exclusive(self) -> Iterator[None]:
        """One SnapTrade operation at a time (refreshes, settings changes)."""
        if not self._refreshing.acquire(blocking=False):
            raise BrokerRefreshInProgressError("A SnapTrade refresh is already running")
        try:
            yield
        finally:
            self._refreshing.release()
