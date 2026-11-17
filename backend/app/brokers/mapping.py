"""Turning SnapTrade instruments into stored positions and market data tickers."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.brokers.models import BrokerPosition
from app.market_data.models import normalise_ticker

# Instrument kinds priced through market data (as exchange-listed securities).
LISTED_KINDS = frozenset({"stock", "etf", "adr", "cef", "preferred_stock", "mutualfund"})

# Exchange (ISO 10383 MIC) -> Yahoo Finance ticker suffix. US venues have none.
US_MICS = frozenset({"XNAS", "XNYS", "ARCX", "BATS", "XASE", "IEXG", "OTCM", "XOTC", "PINX", "OOTC", "EDGX", "BATY"})
MIC_SUFFIX = {
    "XTSE": ".TO", "XTSX": ".V", "NEOE": ".NE", "XCNQ": ".CN",
    "XLON": ".L", "XDUB": ".IR", "XPAR": ".PA", "XAMS": ".AS", "XBRU": ".BR", "XLIS": ".LS",
    "XETR": ".DE", "XFRA": ".F", "XSWX": ".SW", "XMIL": ".MI", "XMAD": ".MC", "XWBO": ".VI",
    "XSTO": ".ST", "XCSE": ".CO", "XOSL": ".OL", "XHEL": ".HE",
    "XASX": ".AX", "XNZE": ".NZ", "XHKG": ".HK", "XTKS": ".T", "XSES": ".SI", "XKRX": ".KS",
    "XBOM": ".BO", "XNSE": ".NS", "XJSE": ".JO", "BVMF": ".SA", "XMEX": ".MX",
}


def decimal_or_none(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def market_ticker(instrument: dict[str, Any]) -> str | None:
    """Best-effort Yahoo Finance ticker for an instrument; None if it cannot be priced that way."""
    kind = _text(instrument.get("kind")) or ""
    raw = _text(instrument.get("raw_symbol")) or _text(instrument.get("symbol"))
    if raw is None:
        return None
    candidate: str | None = None
    if kind == "crypto":
        currency = _text(instrument.get("currency"))
        candidate = f"{raw}-{currency}" if currency else None
    elif kind in LISTED_KINDS:
        mic = (_text(instrument.get("exchange")) or "").upper()
        base = raw.split(".")[0] if mic in MIC_SUFFIX and raw.endswith(MIC_SUFFIX[mic]) else raw
        if mic in MIC_SUFFIX:
            candidate = base.replace(".", "-") + MIC_SUFFIX[mic]
        elif mic in US_MICS or (not mic and _text(instrument.get("currency")) in (None, "USD")):
            candidate = base.replace(".", "-")  # BRK.B -> BRK-B
        else:
            symbol = _text(instrument.get("symbol"))
            candidate = symbol if symbol and symbol != raw else None  # already suffixed by SnapTrade
    if candidate is None:
        return None
    try:
        return normalise_ticker(candidate)
    except ValueError:
        return None


def to_position(account_id: str, item: dict[str, Any]) -> BrokerPosition | None:
    """A stored position from one SnapTrade AccountPosition; None if it has no instrument or units."""
    instrument = item.get("instrument")
    units = decimal_or_none(item.get("units"))
    if not isinstance(instrument, dict) or units is None:
        return None
    symbol = _text(instrument.get("symbol")) or _text(instrument.get("raw_symbol")) or "?"
    multiplier = decimal_or_none(instrument.get("multiplier"))
    return BrokerPosition(
        account_id=account_id,
        symbol=symbol[:100],
        ticker=market_ticker(instrument),
        description=(_text(instrument.get("description")) or "")[:300] or None,
        kind=_text(instrument.get("kind")) or "other",
        units=units,
        price=decimal_or_none(item.get("price")),
        cost_basis=decimal_or_none(item.get("cost_basis")),
        multiplier=multiplier if multiplier and multiplier > 0 else Decimal(1),
        currency=(_text(item.get("currency")) or _text(instrument.get("currency")) or None),
        cash_equivalent=item.get("cash_equivalent") is True,
    )
