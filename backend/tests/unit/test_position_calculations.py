from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.market_data.models import LatestPrice
from app.positions.calculations import currency_totals, position_view, to_decimal
from app.positions.models import Position, PositionStatus

NOW = datetime(2026, 11, 16, 15, tzinfo=UTC)


def pos(ticker: str, qty: str, entry: str, *, currency: str = "USD", exit: str | None = None,
        pid: str = "p") -> Position:
    return Position(
        id=f"{ticker}-{exit or 'open'}", portfolio_id=pid, ticker=ticker, currency=currency,
        quantity=Decimal(qty), entry_price=Decimal(entry), entry_date=date(2026, 1, 2),
        status=PositionStatus.CLOSED if exit else PositionStatus.OPEN,
        exit_price=Decimal(exit) if exit else None, exit_date=date(2026, 11, 1) if exit else None,
        notes="", created_at=NOW, updated_at=NOW,
    )


def price(ticker: str, value: float, prev: float | None, currency: str = "USD", stale: bool = False) -> LatestPrice:
    change = value - prev if prev else None
    return LatestPrice(
        ticker=ticker, price=value, previous_close=prev, currency=currency, timestamp=NOW,
        trading_date=NOW.date(), provider="fake", delayed=True, fetched_at=NOW,
        daily_change=change, daily_change_pct=None, stale=stale,
    )


def test_to_decimal_uses_shortest_repr() -> None:
    assert to_decimal(0.1) == Decimal("0.1")
    assert to_decimal(356.2699890136719) == Decimal("356.2699890136719")
    with pytest.raises(ValueError):
        to_decimal(float("nan"))


def test_open_position_metrics() -> None:
    # Plan example values: 20 @ 210, price 215.42, previous close 218.10
    view = position_view(pos("AAPL", "20", "210"), price("AAPL", 215.42, 218.10))
    assert view.cost_basis == 4200
    assert view.market_value == 4308.4
    assert view.unrealised_pnl == 108.4
    assert view.unrealised_pnl_pct == pytest.approx(2.58095238)
    assert view.daily_change == -2.68
    assert view.daily_change_pct == pytest.approx(-1.22879413)
    assert view.daily_pnl == -53.6
    assert view.realised_pnl is None and view.exit_price is None


def test_decimal_arithmetic_avoids_float_error() -> None:
    view = position_view(pos("X", "3", "0.1"), price("X", 0.3, 0.2))
    assert view.cost_basis == pytest.approx(0.3) and view.unrealised_pnl == 0.6
    assert view.daily_pnl == 0.3  # 3 * (0.3 - 0.2) exactly, not 0.29999999999999993


def test_open_position_without_price_has_null_metrics() -> None:
    view = position_view(pos("AAPL", "10", "200"), None)
    assert view.cost_basis == 2000
    assert view.current_price is view.market_value is view.unrealised_pnl is view.daily_pnl is None


def test_missing_previous_close_only_nulls_daily_fields() -> None:
    view = position_view(pos("AAPL", "10", "200"), price("AAPL", 210, None))
    assert view.unrealised_pnl == 100
    assert view.daily_change is None and view.daily_pnl is None


def test_price_in_other_currency_is_not_used() -> None:
    view = position_view(pos("VOD.L", "100", "110", currency="GBp"), price("VOD.L", 1.18, 1.17, currency="GBP"))
    assert view.market_value is None


def test_stale_flag_passes_through() -> None:
    assert position_view(pos("AAPL", "1", "1"), price("AAPL", 2, 1, stale=True)).stale is True


def test_closed_position_realised_pnl() -> None:
    # Plan example: 5 sold at 230 with entry 210 -> realised 100
    view = position_view(pos("AAPL", "5", "210", exit="230"), price("AAPL", 999, 998))
    assert view.realised_pnl == 100
    assert view.realised_pnl_pct == pytest.approx(9.52380952)
    assert view.exit_price == 230 and view.exit_date == date(2026, 11, 1)
    assert view.market_value is None  # closed positions are not marked to market


def test_closed_position_loss() -> None:
    view = position_view(pos("AAPL", "2.5", "100", exit="80"), None)
    assert view.realised_pnl == -50 and view.realised_pnl_pct == -20


def test_totals_per_currency_never_mixed() -> None:
    positions = [
        pos("AAPL", "10", "200"),
        pos("MSFT", "5", "400"),
        pos("TSLA", "2", "300", exit="250"),
        pos("VOD.L", "1000", "100", currency="GBp"),
    ]
    prices = {"AAPL": price("AAPL", 210, 205), "MSFT": price("MSFT", 390, 400),
              "VOD.L": price("VOD.L", 118.1, 117, currency="GBp")}

    totals = {t.currency: t for t in currency_totals(positions, prices)}

    assert list(totals) == ["GBp", "USD"]
    usd = totals["USD"]
    assert (usd.open_positions, usd.closed_positions) == (2, 1)
    assert usd.cost_basis == 4000 and usd.market_value == 4050
    assert usd.unrealised_pnl == 50 and usd.unrealised_pnl_pct == 1.25
    assert usd.daily_pnl == 50 - 50  # +5*10 and -10*5
    assert usd.realised_pnl == -100
    assert usd.incomplete is False
    gbp = totals["GBp"]
    assert gbp.market_value == 118100 and gbp.unrealised_pnl == 18100 and gbp.realised_pnl == 0


def test_totals_flag_incomplete_when_prices_missing() -> None:
    positions = [pos("AAPL", "10", "200"), pos("NEW", "1", "50")]
    totals = currency_totals(positions, {"AAPL": price("AAPL", 210, None)})[0]
    assert totals.incomplete is True
    assert totals.cost_basis == 2050  # cost basis is always known
    assert totals.market_value == 2100 and totals.unrealised_pnl == 100  # priced positions only
    assert totals.daily_pnl is None


def test_totals_with_only_closed_positions() -> None:
    totals = currency_totals([pos("AAPL", "1", "10", exit="15")], {})[0]
    assert totals.market_value is None and totals.unrealised_pnl is None
    assert totals.realised_pnl == 5 and totals.incomplete is False


def test_no_positions_no_totals() -> None:
    assert currency_totals([], {}) == []
