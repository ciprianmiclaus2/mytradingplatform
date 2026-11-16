from __future__ import annotations

import math
import random
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pytest

from app.market_data.models import DailyBar, HistoryResult, HistoryStatus, LatestPrice
from app.market_data.service import MarketDataService
from app.persistence.derived import derived_registry
from app.persistence.parquet import ParquetStore
from app.strategies.base import ConfigValidationError, StrategyMarketData
from app.strategies.engine import StrategyEngine
from app.strategies.mean_reversion.strategy import MeanReversionStrategy
from app.strategies.models import CalculationStatus, Signal
from app.strategies.registry import StrategyRegistry, discover_strategies, strategy_registry
from app.strategies.signals import SignalStore
from tests.fakes import FIXED_NOW, FakeProvider

NOW = datetime(2026, 11, 16, 15, tzinfo=UTC)
STRATEGY = MeanReversionStrategy()
DEFAULTS = STRATEGY.validate_config({})


def quote(price: float, currency: str = "USD") -> LatestPrice:
    return LatestPrice(ticker="T", price=price, previous_close=None, currency=currency, timestamp=NOW,
                       trading_date=NOW.date(), provider="fake", delayed=True, fetched_at=NOW,
                       daily_change=None, daily_change_pct=None, stale=False)


def history(closes: list[float], currency: str = "USD", adjusted: float | None = None) -> HistoryResult:
    start = date(2026, 1, 1)
    bars = [DailyBar(ticker="T", trading_date=start + timedelta(days=i), close=c,
                     adjusted_close=adjusted if adjusted is not None else c, currency=currency,
                     provider="fake", fetched_at=NOW) for i, c in enumerate(closes)]
    return HistoryResult(ticker="T", status=HistoryStatus.OK, bars=bars)


def evaluate(closes: list[float], price: float, **config):  # type: ignore[no-untyped-def]
    cfg = STRATEGY.validate_config({"lookback_days": len(closes), **config})
    data = StrategyMarketData(quotes={"T": quote(price)}, history={"T": history(closes)})
    [out] = STRATEGY.calculate(["T"], data, cfg)
    return out


# -- calculation on known datasets ------------------------------------------------------------------


def test_known_dataset() -> None:
    out = evaluate([10, 12, 14, 16, 18], 20)
    assert out.status is CalculationStatus.OK
    assert out.metrics["mean"] == 14
    assert out.metrics["standard_deviation"] == pytest.approx(math.sqrt(8))  # population, not sample
    assert out.metrics["z_score"] == pytest.approx(6 / math.sqrt(8))  # 2.1213
    assert out.signal is Signal.SELL


def test_population_not_sample_standard_deviation() -> None:
    out = evaluate([2, 4, 4, 4, 5, 5, 7, 9], 5)
    assert out.metrics["standard_deviation"] == 2.0  # sample std would be 2.138


def test_matches_numpy_on_random_data() -> None:
    rng = random.Random(42)
    for _ in range(25):
        n = rng.randint(2, 60)
        closes = [rng.uniform(5, 500) for _ in range(n)]
        price = rng.uniform(5, 500)
        out = evaluate(closes, price)
        mean, std = np.mean(closes), np.std(closes, ddof=0)
        assert out.metrics["mean"] == pytest.approx(mean, rel=1e-12)
        assert out.metrics["standard_deviation"] == pytest.approx(std, rel=1e-9)
        assert out.metrics["z_score"] == pytest.approx((price - mean) / std, rel=1e-9)


@pytest.mark.parametrize(
    ("price", "signal"),
    [(6.0, Signal.BUY), (5.0, Signal.BUY), (6.0001, None), (10.0, None), (13.9999, None),
     (14.0, Signal.SELL), (20.0, Signal.SELL)],
)
def test_signal_thresholds_are_inclusive(price: float, signal: Signal | None) -> None:
    out = evaluate([8, 12], price)  # mean 10, std 2: Z = -2 at 6, +2 at 14
    assert out.signal is signal


def test_thresholds_are_configurable() -> None:
    closes = [8, 12]
    assert evaluate(closes, 8, buy_threshold=-1.0).signal is Signal.BUY  # Z = -1
    assert evaluate(closes, 8).signal is None  # default -2
    assert evaluate(closes, 13, sell_threshold=1.5).signal is Signal.SELL  # Z = 1.5
    assert evaluate(closes, 13).signal is None


def test_uses_only_the_last_lookback_sessions() -> None:
    cfg = STRATEGY.validate_config({"lookback_days": 3})
    data = StrategyMarketData(quotes={"T": quote(5)}, history={"T": history([1000, 1000, 1, 2, 3])})
    [out] = STRATEGY.calculate(["T"], data, cfg)
    assert out.metrics["mean"] == 2


def test_uses_close_not_adjusted_close() -> None:
    cfg = STRATEGY.validate_config({"lookback_days": 2})
    data = StrategyMarketData(quotes={"T": quote(11)}, history={"T": history([8, 12], adjusted=1.0)})
    [out] = STRATEGY.calculate(["T"], data, cfg)
    assert out.metrics["mean"] == 10


# -- non-OK statuses ------------------------------------------------------------------------------------


def test_insufficient_data_gives_no_signal() -> None:
    cfg = STRATEGY.validate_config({"lookback_days": 20})
    data = StrategyMarketData(quotes={"T": quote(1)}, history={"T": history([100.0] * 5 + [101.0] * 5)})
    [out] = STRATEGY.calculate(["T"], data, cfg)
    assert out.status is CalculationStatus.INSUFFICIENT_DATA
    assert out.signal is None and out.metrics == {}
    assert out.message == "Only 10 of 20 previous sessions available"


def test_zero_standard_deviation_is_invalid() -> None:
    out = evaluate([0.1] * 7, 5)
    assert out.status is CalculationStatus.INVALID_CALCULATION
    assert out.signal is None and out.metrics["z_score"] is None
    assert "Standard deviation is zero" in (out.message or "")


def test_no_quote() -> None:
    cfg = STRATEGY.validate_config({})
    [out] = STRATEGY.calculate(["T"], StrategyMarketData(quotes={"T": None}), cfg)
    assert out.status is CalculationStatus.NO_PRICE


def test_history_error() -> None:
    cfg = STRATEGY.validate_config({})
    failed = HistoryResult(ticker="T", status=HistoryStatus.ERROR, bars=[], error="Yahoo down")
    [out] = STRATEGY.calculate(["T"], StrategyMarketData(quotes={"T": quote(1)}, history={"T": failed}), cfg)
    assert out.status is CalculationStatus.DATA_ERROR and "Yahoo down" in (out.message or "")


def test_currency_mismatch_is_invalid() -> None:
    cfg = STRATEGY.validate_config({"lookback_days": 2})
    data = StrategyMarketData(quotes={"T": quote(1, currency="GBP")}, history={"T": history([1, 2], currency="GBp")})
    [out] = STRATEGY.calculate(["T"], data, cfg)
    assert out.status is CalculationStatus.INVALID_CALCULATION


# -- configuration --------------------------------------------------------------------------------------------


def test_default_configuration_and_schema() -> None:
    assert DEFAULTS == {"lookback_days": 20, "buy_threshold": -2.0, "sell_threshold": 2.0}
    schema = STRATEGY.get_config_schema()
    assert schema.name == "mean_reversion"
    lookback = schema.parameters[0]
    assert (lookback.type, lookback.default, lookback.minimum) == ("integer", 20, 2)
    assert [o.name for o in schema.outputs] == ["mean", "standard_deviation", "z_score"]


@pytest.mark.parametrize(
    ("config", "field"),
    [({"lookback_days": 1}, "lookback_days"), ({"lookback_days": 501}, "lookback_days"),
     ({"lookback_days": 20.5}, "lookback_days"), ({"buy_threshold": "low"}, "buy_threshold"),
     ({"buy_threshold": 2.0, "sell_threshold": 2.0}, "buy_threshold"),
     ({"buy_threshold": 1.0, "sell_threshold": -1.0}, "buy_threshold"), ({"window": 5}, "window")],
)
def test_invalid_configuration(config: dict, field: str) -> None:
    with pytest.raises(ConfigValidationError) as info:
        STRATEGY.validate_config(config)
    assert field in info.value.errors


def test_registered_through_discovery() -> None:
    discover_strategies()
    assert strategy_registry.implementation("mean_reversion") is MeanReversionStrategy


# -- end to end through the engine ------------------------------------------------------------------------------


def sessions(end: date, count: int) -> list[date]:
    days, day = [], end
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day -= timedelta(days=1)
    return sorted(days)


@pytest.fixture
def provider() -> FakeProvider:
    p = FakeProvider()
    previous = sessions(FIXED_NOW.date() - timedelta(days=1), 30)  # 30 completed sessions before Monday
    # Alternating 98/102: mean 100, population std 2 for any even window.
    closes = {d: (98.0 if i % 2 == 0 else 102.0) for i, d in enumerate(previous)}
    closes[FIXED_NOW.date()] = 5000.0  # today's incomplete session: must never be used
    p.set_closes("AAA", closes)
    p.set_closes("NEW", dict(list(closes.items())[-6:-1]))  # only 5 completed sessions
    p.set_quote("AAA", 95.0, previous_close=97.0)
    p.set_quote("NEW", 95.0, previous_close=97.0)
    return p


@pytest.fixture
def clock() -> dict:
    return {"now": FIXED_NOW}


@pytest.fixture
def market(store: ParquetStore, provider: FakeProvider, clock: dict) -> MarketDataService:
    svc = MarketDataService(provider, store, derived_registry, archive_threshold=1000, clock=lambda: clock["now"])
    svc.refresh(["AAA", "NEW"])
    return svc


@pytest.fixture
def engine(store: ParquetStore, market: MarketDataService, clock: dict) -> StrategyEngine:
    registry = StrategyRegistry()
    registry.register(MeanReversionStrategy)
    return StrategyEngine(registry, market, SignalStore(store), clock=lambda: clock["now"])


def run(engine: StrategyEngine, tickers: list[str], instance: str | None = "pane-1", **config):  # type: ignore[no-untyped-def]
    return {r.ticker: r for r in engine.run("mean_reversion", tickers, config, instance_id=instance).results}


def test_engine_excludes_current_session(engine: StrategyEngine) -> None:
    aaa = run(engine, ["AAA"], None)["AAA"]
    assert aaa.metrics["mean"] == 100.0 and aaa.metrics["standard_deviation"] == 2.0  # 5000 not included
    assert aaa.metrics["z_score"] == -2.5 and aaa.signal is Signal.BUY
    assert aaa.current_price == 95.0 and aaa.daily_change == -2.0


def test_engine_lookback_is_configurable(engine: StrategyEngine) -> None:
    four = run(engine, ["AAA"], None, lookback_days=4)["AAA"]
    assert (four.metrics["mean"], four.metrics["standard_deviation"]) == (100.0, 2.0)
    three = run(engine, ["AAA"], None, lookback_days=3)["AAA"]  # last three closes: 102, 98, 102
    assert three.metrics["mean"] == pytest.approx(302 / 3)
    assert three.metrics["standard_deviation"] == pytest.approx(np.std([102, 98, 102]))
    assert three.metrics["z_score"] != four.metrics["z_score"]


def test_engine_insufficient_history_no_false_signal(engine: StrategyEngine) -> None:
    new = run(engine, ["NEW"])["NEW"]
    assert new.status is CalculationStatus.INSUFFICIENT_DATA and new.signal is None
    assert new.is_new_signal is False
    assert engine.signals.history(instance_id="pane-1").total == 0


def test_engine_signal_transitions(engine: StrategyEngine, market: MarketDataService, provider: FakeProvider,
                                   clock: dict) -> None:
    first = run(engine, ["AAA"])["AAA"]  # existing condition produces a signal immediately
    assert first.signal is Signal.BUY and first.is_new_signal is True

    clock["now"] += timedelta(minutes=5)
    second = run(engine, ["AAA"])["AAA"]
    assert second.signal is Signal.BUY and second.is_new_signal is False

    # Price returns between the thresholds: signal becomes NONE.
    clock["now"] += timedelta(minutes=5)
    provider.set_quote("AAA", 100.5, previous_close=97.0, timestamp=clock["now"])
    market.refresh(["AAA"])
    third = run(engine, ["AAA"])["AAA"]
    assert third.signal is None and third.is_new_signal is True and third.previous_signal is Signal.BUY

    clock["now"] += timedelta(minutes=5)
    provider.set_quote("AAA", 105.0, previous_close=97.0, timestamp=clock["now"])
    market.refresh(["AAA"])
    fourth = run(engine, ["AAA"])["AAA"]
    assert fourth.signal is Signal.SELL and fourth.metrics["z_score"] == 2.5

    events = engine.signals.history(instance_id="pane-1").items
    assert [(e.previous_signal, e.new_signal) for e in reversed(events)] == [
        (None, Signal.BUY), (Signal.BUY, None), (None, Signal.SELL)]
    assert events[0].metric_name == "z_score" and events[0].metric_value == 2.5
    assert events[0].current_price == 105.0
