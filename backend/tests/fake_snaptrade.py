"""In-memory SnapTrade API for tests: an httpx transport that verifies request signatures."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any
from urllib.parse import parse_qs

import httpx

from app.brokers.models import SnapTradeCredentials
from app.brokers.snaptrade import SnapTradeClient

BASE_URL = "https://snaptrade.test"


def account(account_id: str, name: str, number: str = "****1234", value: float | None = 1000.0,
            currency: str = "USD") -> dict[str, Any]:
    return {"kind": "investment", "id": account_id, "connection_id": "conn-1", "display_name": name,
            "masked_account_number": number, "status": "open", "is_paper": False, "sync_status": {},
            "net_value": {"amount": value, "currency": currency}}


def stock(symbol: str, units: str, price: str | None, cost: str | None, currency: str = "USD",
          exchange: str | None = "XNAS", kind: str = "stock", raw: str | None = None, **instrument: Any) -> dict[str, Any]:
    return {"instrument": {"kind": kind, "id": f"id-{symbol}", "symbol": symbol, "raw_symbol": raw or symbol,
                           "description": f"{symbol} Inc", "currency": currency, "exchange": exchange, **instrument},
            "units": units, "price": price, "cost_basis": cost, "currency": currency}


class FakeSnapTrade:
    client_id = "test-client"
    consumer_key = "consumer-key-0001-9876"
    user_id = "test-user"
    user_secret = "user-secret-0002-4321"

    def __init__(self, personal: bool = False) -> None:
        # Personal API key: SnapTrade resolves the user from the key; requests must not carry one.
        self.personal = personal
        self.accounts: list[dict[str, Any]] = []
        self.positions: dict[str, list[dict[str, Any]]] = {}
        self.as_of = "2026-11-16T14:30:00.000Z"
        self.failures: dict[str, tuple[int, dict[str, Any], dict[str, str]]] = {}
        self.calls: list[str] = []
        self.transport = httpx.MockTransport(self._handle)

    def credentials(self, **overrides: str) -> dict[str, str]:
        base = {"client_id": self.client_id, "consumer_key": self.consumer_key}
        if not self.personal:
            base |= {"user_id": self.user_id, "user_secret": self.user_secret}
        return {**base, **overrides}

    def factory(self, creds: SnapTradeCredentials) -> SnapTradeClient:
        return SnapTradeClient(creds, base_url=BASE_URL, transport=self.transport)

    def fail(self, path: str, status: int, body: dict[str, Any], headers: dict[str, str] | None = None) -> None:
        self.failures[path] = (status, body, headers or {})

    def _handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        query = request.url.query.decode()
        self.calls.append(path)
        params = {k: v[0] for k, v in parse_qs(query).items()}
        # Independent implementation of SnapTrade's documented signature check.
        payload = json.dumps({"content": None, "path": path, "query": query}, separators=(",", ":"), sort_keys=True)
        expected = base64.b64encode(hmac.new(self.consumer_key.encode(), payload.encode(), hashlib.sha256).digest()).decode()
        if (request.headers.get("Signature") != expected or params.get("clientId") != self.client_id
                or not params.get("timestamp", "").isdigit()):
            return httpx.Response(401, json={"default_detail": "Unable to verify signature sent", "default_code": 1076})
        if self.personal:
            if "userId" in params or "userSecret" in params:
                return httpx.Response(400, json={"detail": "Personal API keys must not send userId or userSecret"})
        elif params.get("userId") != self.user_id or params.get("userSecret") != self.user_secret:
            return httpx.Response(401, json={"detail": "Invalid userID or userSecret provided", "code": "1083"})
        if path in self.failures:
            status, body, headers = self.failures[path]
            return httpx.Response(status, json=body, headers=headers)
        if path == "/accounts/all":
            return httpx.Response(200, json={"results": self.accounts})
        parts = path.strip("/").split("/")
        if len(parts) == 4 and parts[0] == "accounts" and parts[2:] == ["positions", "all"]:
            if parts[1] not in self.positions:
                return httpx.Response(404, json={"default_detail": "Account not found", "default_code": 1011})
            return httpx.Response(200, json={"results": self.positions[parts[1]],
                                             "data_freshness": {"as_of": self.as_of}})
        return httpx.Response(404, json={"detail": "Not found"})
