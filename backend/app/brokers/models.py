"""Broker (SnapTrade) models: credentials, accounts and positions."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

FIELD_MAX = 200


class SnapTradeCredentials(BaseModel):
    """SnapTrade API credentials. Secrets never leave the backend.

    A Personal API key (one person's own accounts) is just the client ID and
    consumer key: SnapTrade resolves the user from the key, and requests must
    not carry a user. Commercial keys add the registered user's ID and secret.
    """

    model_config = ConfigDict(frozen=True)

    client_id: str = Field(min_length=1, max_length=FIELD_MAX)
    consumer_key: SecretStr = Field(min_length=1, max_length=FIELD_MAX)
    user_id: str | None = Field(default=None, max_length=FIELD_MAX)
    user_secret: SecretStr | None = Field(default=None, max_length=FIELD_MAX)

    @field_validator("client_id", "consumer_key", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("user_id", "user_secret", mode="before")
    @classmethod
    def _strip_optional(cls, value: object) -> object:
        """Blank user fields mean "no user" (a Personal API key)."""
        if isinstance(value, str):
            return value.strip() or None
        return value

    @model_validator(mode="after")
    def _user_pair(self) -> SnapTradeCredentials:
        if (self.user_id is None) != (self.user_secret is None):
            raise ValueError("Enter both the user ID and the user secret, or neither (Personal API key)")
        return self

    @property
    def personal(self) -> bool:
        """True for a Personal API key: no SnapTrade user is sent with requests."""
        return self.user_id is None


class SnapTradeStatus(BaseModel):
    """What the UI may know about the stored credentials (never the secrets)."""

    configured: bool
    personal: bool | None = Field(default=None, description="Personal API key (no SnapTrade user); None when not set up")
    client_id: str | None = None
    user_id: str | None = None
    consumer_key_hint: str | None = Field(default=None, description="Last 4 characters")
    user_secret_hint: str | None = Field(default=None, description="Last 4 characters")


class BrokerAccount(BaseModel):
    """An account as last listed by SnapTrade."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    number: str = Field(description="Masked account number, e.g. ****8443")
    status: str | None
    kind: str
    net_value: float | None
    net_value_currency: str | None
    listed_at: datetime = Field(description="When this account was last seen in the account list")
    positions_refreshed_at: datetime | None = Field(default=None, description="Last successful positions refresh")
    data_as_of: datetime | None = Field(default=None, description="When SnapTrade fetched the data from the broker")


class BrokerPosition(BaseModel):
    """A position as stored after a refresh."""

    model_config = ConfigDict(frozen=True)

    account_id: str
    symbol: str = Field(description="The broker's symbol")
    ticker: str | None = Field(description="Market data ticker, when the instrument could be mapped")
    description: str | None
    kind: str
    units: Decimal
    price: Decimal | None = Field(description="Broker price per unit at the refresh")
    cost_basis: Decimal | None = Field(description="Average purchase price per unit")
    multiplier: Decimal = Field(description="Contract multiplier (options); 1 otherwise")
    currency: str | None
    cash_equivalent: bool


class BrokerAccountView(BrokerAccount):
    tickers: list[str] = Field(description="Market data tickers held at the last refresh")


class BrokerAccounts(BaseModel):
    configured: bool
    accounts: list[BrokerAccountView]
    accounts_refreshed_at: datetime | None


class BrokerPositionView(BaseModel):
    """One row of the broker positions pane. Values are computed by the backend."""

    symbol: str
    ticker: str | None
    description: str | None
    kind: str
    currency: str | None
    quantity: float
    average_cost: float | None
    cost_basis: float | None = Field(description="Total cost: quantity × average cost × multiplier")
    current_price: float | None
    price_source: str | None = Field(description="'market' (live quote), 'broker' (price at the last refresh) or None")
    price_timestamp: datetime | None
    previous_close: float | None = None
    market_value: float | None = None
    daily_change: float | None = None
    daily_change_pct: float | None = None
    daily_pnl: float | None = None
    unrealised_pnl: float | None = None
    unrealised_pnl_pct: float | None = None
    stale: bool = False


class BrokerCurrencyTotals(BaseModel):
    """Totals over one account's positions in one currency (currencies are never combined)."""

    currency: str
    positions: int
    market_value: float | None
    cost_basis: float | None
    unrealised_pnl: float | None
    unrealised_pnl_pct: float | None
    daily_pnl: float | None
    incomplete: bool = Field(description="Some positions lack a price, cost or daily change and are left out")


class BrokerPositionsResponse(BaseModel):
    account: BrokerAccount
    positions: list[BrokerPositionView]
    totals: list[BrokerCurrencyTotals]


class AccountRefreshError(BaseModel):
    account_id: str
    account_name: str
    message: str


class BrokerRefreshResult(BaseModel):
    accounts: list[BrokerAccountView]
    errors: list[AccountRefreshError]
    accounts_refreshed_at: datetime
