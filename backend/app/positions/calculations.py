"""Position valuation and P&L (plan §7.3–7.4). Pure functions, decimal arithmetic."""

from __future__ import annotations

import math
from collections import defaultdict
from decimal import Decimal

from app.market_data.models import LatestPrice
from app.positions.models import CurrencyTotals, Position, PositionStatus, PositionView

HUNDRED = Decimal(100)
_OUT = Decimal("1e-8")


def to_decimal(value: float) -> Decimal:
    """Market prices are float64; convert via their shortest repr, not binary expansion."""
    if not math.isfinite(value):
        raise ValueError("Price must be finite")
    return Decimal(repr(value))


def _out(value: Decimal | None) -> float | None:
    return None if value is None else float(value.quantize(_OUT))


def _pct(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    return None if denominator == 0 else numerator / denominator * HUNDRED


def position_view(position: Position, price: LatestPrice | None) -> PositionView:
    cost_basis = position.quantity * position.entry_price
    view = PositionView(
        id=position.id,
        portfolio_id=position.portfolio_id,
        ticker=position.ticker,
        currency=position.currency,
        status=position.status,
        quantity=float(position.quantity),
        entry_price=float(position.entry_price),
        entry_date=position.entry_date,
        notes=position.notes,
        cost_basis=float(cost_basis),
        created_at=position.created_at,
        updated_at=position.updated_at,
    )
    updates: dict[str, object] = {}
    if position.status is PositionStatus.CLOSED:
        assert position.exit_price is not None
        diff = position.exit_price - position.entry_price
        updates = {
            "exit_price": float(position.exit_price),
            "exit_date": position.exit_date,
            "realised_pnl": _out(position.quantity * diff),
            "realised_pnl_pct": _out(_pct(diff, position.entry_price)),
        }
    elif price is not None and price.currency == position.currency:
        current = to_decimal(price.price)
        market_value = position.quantity * current
        unrealised = market_value - cost_basis
        updates = {
            "current_price": price.price,
            "previous_close": price.previous_close,
            "price_timestamp": price.timestamp,
            "market_value": _out(market_value),
            "unrealised_pnl": _out(unrealised),
            "unrealised_pnl_pct": _out(_pct(unrealised, cost_basis)),
            "stale": price.stale,
        }
        if price.previous_close is not None:
            change = current - to_decimal(price.previous_close)
            updates |= {
                "daily_change": _out(change),
                "daily_change_pct": _out(_pct(change, to_decimal(price.previous_close))),
                "daily_pnl": _out(position.quantity * change),
            }
    return view.model_copy(update=updates)


def currency_totals(positions: list[Position], prices: dict[str, LatestPrice | None]) -> list[CurrencyTotals]:
    """Totals per currency over all positions; currencies are never combined."""
    groups: dict[str, list[Position]] = defaultdict(list)
    for p in positions:
        groups[p.currency].append(p)

    totals = []
    for currency in sorted(groups):
        open_market = Decimal(0)
        open_cost_priced = Decimal(0)
        cost_basis = Decimal(0)
        daily = Decimal(0)
        realised = Decimal(0)
        n_open = n_closed = 0
        priced = daily_known = 0
        for p in groups[currency]:
            if p.status is PositionStatus.CLOSED:
                n_closed += 1
                assert p.exit_price is not None
                realised += p.quantity * (p.exit_price - p.entry_price)
                continue
            n_open += 1
            cost = p.quantity * p.entry_price
            cost_basis += cost
            price = prices.get(p.ticker)
            if price is None or price.currency != currency:
                continue
            priced += 1
            current = to_decimal(price.price)
            open_market += p.quantity * current
            open_cost_priced += cost
            if price.previous_close is not None:
                daily_known += 1
                daily += p.quantity * (current - to_decimal(price.previous_close))

        unrealised = open_market - open_cost_priced if priced else None
        totals.append(
            CurrencyTotals(
                currency=currency,
                open_positions=n_open,
                closed_positions=n_closed,
                market_value=_out(open_market) if priced else None,
                cost_basis=float(cost_basis),
                unrealised_pnl=_out(unrealised),
                unrealised_pnl_pct=_out(_pct(unrealised, open_cost_priced)) if unrealised is not None else None,
                daily_pnl=_out(daily) if daily_known else None,
                realised_pnl=float(realised),
                incomplete=priced < n_open or daily_known < n_open,
            )
        )
    return totals
