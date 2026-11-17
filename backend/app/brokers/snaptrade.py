"""Minimal SnapTrade API client (read-only): list accounts, list an account's positions.

Requests are signed as documented at https://docs.snaptrade.com/docs/request-signatures:
the query string carries clientId and timestamp, plus userId and userSecret
for Commercial keys (a Personal API key sends no user); the ``Signature``
header is base64(HMAC-SHA256(consumerKey, canonical JSON of {content, path, query})).

The user secret is part of the query string, so request URLs are never
logged or put in error messages (httpx's own request log is silenced).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from app.brokers.models import SnapTradeCredentials
from app.schemas.errors import AppError

logger = logging.getLogger(__name__)
# httpx logs every request URL at INFO; SnapTrade URLs contain the user secret.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

DEFAULT_BASE_URL = "https://api.snaptrade.com"


class SnapTradeError(AppError):
    """SnapTrade could not be reached or returned an error."""

    status_code = 502
    code = "snaptrade_error"


class SnapTradeAuthError(SnapTradeError):
    code = "snaptrade_auth_failed"


class SnapTradeRateLimitedError(SnapTradeError):
    status_code = 429
    code = "snaptrade_rate_limited"


class SnapTradeNotFoundError(SnapTradeError):
    status_code = 404
    code = "snaptrade_not_found"


def sign(consumer_key: str, path: str, query: str, body: Any = None) -> str:
    """The ``Signature`` header for a request (SnapTrade's documented algorithm)."""
    content = None if body is None or body == {} else body
    payload = json.dumps({"content": content, "path": path, "query": query}, separators=(",", ":"), sort_keys=True)
    digest = hmac.new(consumer_key.encode(), payload.encode(), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def _detail(response: httpx.Response) -> str:
    """SnapTrade error bodies use detail/code or default_detail/default_code."""
    try:
        body = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"
    if isinstance(body, dict):
        for key in ("detail", "default_detail", "message"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:300]
    return f"HTTP {response.status_code}"


class SnapTradeClient:
    def __init__(
        self,
        credentials: SnapTradeCredentials,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.credentials = credentials
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.transport = transport
        self.clock = clock

    def list_accounts(self) -> list[dict[str, Any]]:
        """All accounts across the user's connections (GET /accounts/all)."""
        body = self._get("/accounts/all")
        results = body.get("results") if isinstance(body, dict) else None
        if not isinstance(results, list):
            raise SnapTradeError("SnapTrade returned an unexpected account list")
        return [r for r in results if isinstance(r, dict)]

    def account_positions(self, account_id: str) -> tuple[list[dict[str, Any]], str | None]:
        """An account's positions and the time SnapTrade fetched them from the broker."""
        body = self._get(f"/accounts/{quote(account_id, safe='')}/positions/all")
        results = body.get("results") if isinstance(body, dict) else None
        if not isinstance(results, list):
            raise SnapTradeError("SnapTrade returned an unexpected positions list")
        freshness = body.get("data_freshness")
        as_of = freshness.get("as_of") if isinstance(freshness, dict) else None
        return [r for r in results if isinstance(r, dict)], as_of if isinstance(as_of, str) else None

    def _get(self, path: str) -> Any:
        creds = self.credentials
        params = {"clientId": creds.client_id, "timestamp": str(int(self.clock()))}
        if creds.user_id is not None and creds.user_secret is not None:  # Commercial keys only
            params |= {"userId": creds.user_id, "userSecret": creds.user_secret.get_secret_value()}
        query = urlencode(params)
        headers = {
            "Signature": sign(creds.consumer_key.get_secret_value(), path, query),
            "Accept": "application/json",
        }
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                # The URL is built here (not with params=) so the signed query is exactly what is sent.
                response = client.get(f"{self.base_url}{path}?{query}", headers=headers)
        except httpx.TimeoutException as exc:
            raise SnapTradeError("SnapTrade did not respond in time. Try again later.") from exc
        except httpx.HTTPError as exc:
            # Message only: the exception may reference the request URL (with the secret).
            raise SnapTradeError(f"SnapTrade could not be reached ({type(exc).__name__})") from None

        status = response.status_code
        if status == 200:
            try:
                return response.json()
            except ValueError:
                raise SnapTradeError("SnapTrade returned an invalid response") from None
        detail = _detail(response)
        logger.warning("snaptrade request failed", extra={"path": path.split("?")[0], "status": status, "detail": detail})
        if status in (401, 403):
            raise SnapTradeAuthError(f"SnapTrade rejected the request: {detail}. Check the SnapTrade settings.")
        if status == 404:
            raise SnapTradeNotFoundError(f"SnapTrade could not find it: {detail}")
        if status == 429:
            retry = response.headers.get("Retry-After")
            wait = f" Try again in {retry} seconds." if retry and retry.isdigit() else " Try again shortly."
            raise SnapTradeRateLimitedError(f"SnapTrade rate limit reached.{wait}")
        if status == 402:
            raise SnapTradeError(f"The brokerage connection is disabled: {detail}. Reconnect it in SnapTrade.")
        raise SnapTradeError(f"SnapTrade error {status}: {detail}")
