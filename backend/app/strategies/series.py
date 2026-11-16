"""Building a strategy's price series from engine market data, with the standard status checks."""

from __future__ import annotations

from app.strategies.base import StrategyMarketData
from app.strategies.models import CalculationStatus, StrategyOutput


def price_series(
    ticker: str,
    market_data: StrategyMarketData,
    *,
    minimum_closes: int,
    include_current: bool,
) -> list[float] | StrategyOutput:
    """Completed regular closes, oldest first, optionally followed by the current price.

    Returns a non-OK ``StrategyOutput`` instead when the ticker cannot be
    evaluated: no current price, history unavailable, fewer than
    ``minimum_closes`` completed sessions, or a currency mismatch.
    """
    quote = market_data.quote(ticker)
    if quote is None:
        return StrategyOutput(ticker=ticker, status=CalculationStatus.NO_PRICE,
                              message="No current price; refresh market data")
    error = market_data.history_error(ticker)
    if error:
        return StrategyOutput(ticker=ticker, status=CalculationStatus.DATA_ERROR,
                              message=f"Historical prices unavailable: {error}")
    bars = market_data.closes(ticker)
    if len(bars) < minimum_closes:
        return StrategyOutput(ticker=ticker, status=CalculationStatus.INSUFFICIENT_DATA,
                              message=f"Only {len(bars)} of {minimum_closes} previous sessions available")
    if any(bar.currency != quote.currency for bar in bars):
        return StrategyOutput(ticker=ticker, status=CalculationStatus.INVALID_CALCULATION,
                              message="Historical prices and current price are in different currencies")
    closes = [bar.close for bar in bars]
    return [*closes, quote.price] if include_current else closes
