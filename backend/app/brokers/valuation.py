"""Valuation of broker positions with live market prices (pure functions, decimal arithmetic).

The price is the live market quote when the position maps to a ticker with a
quote in the position's currency; otherwise the broker's price at the last
refresh. Daily change needs a live quote.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from app.brokers.models import BrokerCurrencyTotals, BrokerPosition, BrokerPositionView
from app.market_data.models import LatestPrice

HUNDRED = Decimal(100)
_OUT = Decimal("1e-8")


def _dec(value: float) -> Decimal:
    if not math.isfinite(value):
        raise ValueError("Price must be finite")
    return Decimal(repr(value))


def _out(value: Decimal | None) -> float | None:
    return None if value is None else float(value.quantize(_OUT))


def _pct(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    return None if denominator == 0 else numerator / abs(denominator) * HUNDRED


# Quote currencies in minor units (Yahoo quotes London in pence) -> (major currency, units per major unit).
MINOR_UNITS = {"GBp": ("GBP", 100), "GBX": ("GBP", 100), "ZAc": ("ZAR", 100), "ZAC": ("ZAR", 100), "ILA": ("ILS", 100)}


def live_quote(position: BrokerPosition, prices: dict[str, LatestPrice | None]) -> LatestPrice | None:
    """The market quote in the position's currency, or None if there is none (or it cannot be converted).

    Brokers report London stocks in pounds while market data quotes them in
    pence; such quotes are converted to the major unit.
    """
    quote = prices.get(position.ticker) if position.ticker else None
    if quote is None or position.currency is None:
        return None
    if quote.currency == position.currency:
        return quote
    major, factor = MINOR_UNITS.get(quote.currency, (None, 1))
    if major != position.currency:
        return None
    return quote.model_copy(update={
        "currency": major,
        "price": quote.price / factor,
        "previous_close": quote.previous_close / factor if quote.previous_close is not None else None,
        "daily_change": quote.daily_change / factor if quote.daily_change is not None else None,
    })


def position_view(position: BrokerPosition, quote: LatestPrice | None, as_of: datetime | None = None) -> BrokerPositionView:
    """``as_of``: when the broker price was fetched (shown when no live quote is used)."""
    size = position.units * position.multiplier
    cost = size * position.cost_basis if position.cost_basis is not None else None
    if quote is not None:
        price: Decimal | None = _dec(quote.price)
        source = "market"
    else:
        price = position.price
        source = "broker" if price is not None else None
    market_value = size * price if price is not None else None
    unrealised = market_value - cost if market_value is not None and cost is not None else None
    view = BrokerPositionView(
        symbol=position.symbol,
        ticker=position.ticker,
        description=position.description,
        kind=position.kind,
        currency=position.currency,
        quantity=float(position.units),
        average_cost=_out(position.cost_basis),
        cost_basis=_out(cost),
        current_price=_out(price),
        price_source=source,
        price_timestamp=quote.timestamp if quote is not None else as_of,
        market_value=_out(market_value),
        unrealised_pnl=_out(unrealised),
        unrealised_pnl_pct=_out(_pct(unrealised, cost)) if unrealised is not None and cost is not None else None,
        stale=quote.stale if quote is not None else False,
    )
    if quote is not None and quote.previous_close is not None and price is not None:
        change = price - _dec(quote.previous_close)
        view = view.model_copy(update={
            "previous_close": quote.previous_close,
            "daily_change": _out(change),
            "daily_change_pct": _out(_pct(change, _dec(quote.previous_close))),
            "daily_pnl": _out(size * change),
        })
    return view


def currency_totals(views: list[BrokerPositionView]) -> list[BrokerCurrencyTotals]:
    """Per-currency totals; positions without a currency are not totalled."""
    groups: dict[str, list[BrokerPositionView]] = defaultdict(list)
    for v in views:
        if v.currency:
            groups[v.currency].append(v)
    totals = []
    for currency in sorted(groups):
        rows = groups[currency]
        valued = [r for r in rows if r.market_value is not None]
        with_pnl = [r for r in rows if r.unrealised_pnl is not None and r.cost_basis is not None]
        daily = [r for r in rows if r.daily_pnl is not None]
        market = sum((Decimal(repr(r.market_value)) for r in valued), Decimal(0))
        cost = sum((Decimal(repr(r.cost_basis)) for r in with_pnl), Decimal(0))  # type: ignore[arg-type]
        pnl = sum((Decimal(repr(r.unrealised_pnl)) for r in with_pnl), Decimal(0))
        totals.append(BrokerCurrencyTotals(
            currency=currency,
            positions=len(rows),
            market_value=_out(market) if valued else None,
            cost_basis=_out(cost) if with_pnl else None,
            unrealised_pnl=_out(pnl) if with_pnl else None,
            unrealised_pnl_pct=_out(_pct(pnl, cost)) if with_pnl else None,
            daily_pnl=_out(sum((Decimal(repr(r.daily_pnl)) for r in daily), Decimal(0))) if daily else None,
            incomplete=len(valued) < len(rows) or len(with_pnl) < len(rows) or len(daily) < len(rows),
        ))
    return totals
