"""Market data provider registry.

Providers are registered explicitly by name. Adding a provider means writing a
``BaseMarketDataProvider`` subclass and adding one entry here; the service and
the rest of the application are unchanged.
"""

from __future__ import annotations

from collections.abc import Callable

from app.market_data.base import BaseMarketDataProvider

ProviderFactory = Callable[[float], BaseMarketDataProvider]


def _yfinance(timeout: float) -> BaseMarketDataProvider:
    from app.market_data.providers.yfinance_provider import YFinanceProvider

    return YFinanceProvider(timeout=timeout)


_PROVIDERS: dict[str, ProviderFactory] = {"yfinance": _yfinance}


def available_providers() -> list[str]:
    return sorted(_PROVIDERS)


def create_provider(name: str, timeout: float) -> BaseMarketDataProvider:
    try:
        factory = _PROVIDERS[name]
    except KeyError:
        raise ValueError(
            f"Unknown market data provider {name!r}; available: {', '.join(available_providers())}"
        ) from None
    return factory(timeout)
