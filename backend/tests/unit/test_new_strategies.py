"""RSI and Moving Average Crossover strategies."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.market_data.models import DailyBar, HistoryResult, HistoryStatus, LatestPrice
from app.strategies.base import ConfigValidationError, StrategyMarketData
from app.strategies.ma_crossover.strategy import MovingAverageCrossoverStrategy
from app.strategies.models import CalculationStatus, Signal
from app.strategies.registry import discover_strategies, strategy_registry
from app.strategies.rsi.strategy import RsiStrategy
from tests.unit.test_indicators import REFERENCE_PRICES, REFERENCE_RSI

NOW = datetime(2026, 11, 16, 15, tzinfo=UTC)
RSI = RsiStrategy()
MA = MovingAverageCrossoverStrategy()


def data(closes: list[float], price: float | None, currency: str = "USD", error: str | None = None) -> StrategyMarketData:
    start = date(2025, 1, 1)
    bars = [DailyBar(ticker="T", trading_date=start + timedelta(days=i), close=c, adjusted_close=c * 0.9,
                     currency=currency, provider="fake", fetched_at=NOW) for i, c in enumerate(closes)]
    history = HistoryResult(ticker="T", status=HistoryStatus.ERROR if error else HistoryStatus.OK, bars=bars, error=error)
    quote = None if price is None else LatestPrice(
        ticker="T", price=price, previous_close=None, currency="USD", timestamp=NOW, trading_date=NOW.date(),
        provider="fake", delayed=True, fetched_at=NOW, daily_change=None, daily_change_pct=None, stale=False)
    return StrategyMarketData(quotes={"T": quote}, history={"T": history})


def run(strategy, closes, price, **config):  # type: ignore[no-untyped-def]
    cfg = strategy.validate_config(config)
    [out] = strategy.calculate(["T"], data(closes, price), cfg)
    return out


# -- RSI ---------------------------------------------------------------------------------------------


def test_rsi_on_reference_data_with_current_price_last() -> None:
    out = run(RSI, REFERENCE_PRICES[:-1], REFERENCE_PRICES[-1])
    assert out.status is CalculationStatus.OK
    assert out.metrics["rsi"] == pytest.approx(REFERENCE_RSI[-1], abs=0.005)
    assert out.signal is None  # 37.77: neither oversold nor overbought


@pytest.mark.parametrize(
    ("closes", "price", "signal"),
    [([10, 9, 8, 7, 6, 5], 4, Signal.BUY), ([4, 5, 6, 7, 8, 9], 10, Signal.SELL)],
)
def test_rsi_signals(closes: list[float], price: float, signal: Signal) -> None:
    assert run(RSI, closes, price, period=3).signal is signal


def test_rsi_levels_are_inclusive_and_configurable() -> None:
    # changes +1, -1, +2 -> RSI 75
    assert run(RSI, [10, 11, 10], 12, period=3, overbought=75).signal is Signal.SELL
    assert run(RSI, [10, 11, 10], 12, period=3, overbought=75.01).signal is None
    assert run(RSI, [10, 11, 10], 12, period=3, oversold=75, overbought=80).signal is Signal.BUY


def test_rsi_uses_regular_close_not_adjusted() -> None:
    out = run(RSI, [10, 11, 10], 12, period=3)
    assert out.metrics["average_gain"] == pytest.approx(1.0)  # adjusted closes (×0.9) would give different values


def test_rsi_statuses() -> None:
    assert run(RSI, [10, 11], 12, period=3).status is CalculationStatus.INSUFFICIENT_DATA
    assert run(RSI, [5, 5, 5], 5, period=3).status is CalculationStatus.INVALID_CALCULATION
    cfg = RSI.validate_config({"period": 3})
    assert RSI.calculate(["T"], data([1, 2, 3], None), cfg)[0].status is CalculationStatus.NO_PRICE
    assert RSI.calculate(["T"], data([1, 2, 3], 4, error="down"), cfg)[0].status is CalculationStatus.DATA_ERROR
    assert RSI.calculate(["T"], data([1, 2, 3], 4, currency="GBp"), cfg)[0].status is CalculationStatus.INVALID_CALCULATION


def test_rsi_warmup_history_requested() -> None:
    assert RSI.required_sessions(RSI.validate_config({})) == 140


@pytest.mark.parametrize(
    ("config", "field"),
    [({"period": 1}, "period"), ({"period": 101}, "period"), ({"oversold": -1}, "oversold"),
     ({"overbought": 101}, "overbought"), ({"oversold": 70, "overbought": 70}, "oversold"),
     ({"period": 14.5}, "period")],
)
def test_rsi_invalid_configuration(config: dict, field: str) -> None:
    with pytest.raises(ConfigValidationError) as info:
        RSI.validate_config(config)
    assert field in info.value.errors


# -- Moving average crossover ---------------------------------------------------------------------------

TREND = {"signal_mode": "Trend"}


def test_ma_defaults_and_history_requirement() -> None:
    cfg = MA.validate_config({})
    assert cfg == {"fast_period": 50, "slow_period": 200, "average_type": "SMA", "signal_mode": "Recent cross",
                   "recent_sessions": 5, "use_current_price": True}
    assert MA.required_sessions(cfg) == 450  # slow + 250 sessions to find the last cross
    assert MA.required_sessions({**cfg, "average_type": "EMA"}) == 600


def test_ma_sma_values_and_trend_mode() -> None:
    out = run(MA, [1, 2, 3, 4, 5], 6, fast_period=2, slow_period=4, **TREND)
    # series 1..6: fast = (5+6)/2 = 5.5, slow = (3+4+5+6)/4 = 4.5
    assert out.metrics["fast_ma"] == 5.5 and out.metrics["slow_ma"] == 4.5
    assert out.metrics["spread_pct"] == pytest.approx(100 / 4.5)
    assert out.metrics["sessions_since_cross"] is None  # always above: no cross in the series
    assert out.signal is Signal.BUY  # trend mode: the side alone decides


def test_ma_downtrend_is_sell_in_trend_mode() -> None:
    assert run(MA, [6, 5, 4, 3, 2], 1, fast_period=2, slow_period=4, **TREND).signal is Signal.SELL


def test_ma_equal_averages_give_no_signal() -> None:
    assert run(MA, [5, 5, 5, 5], 5, fast_period=2, slow_period=4, **TREND).signal is None


# Falls, then rises: fast(2) crosses above slow(4) at the session closing 13.
CROSS_UP = [20, 18, 16, 14, 12, 10, 13, 16, 19, 22]


def test_ma_since_cross_counts_sessions() -> None:
    # Completed sessions only: the last position is the close of 22.
    out = run(MA, CROSS_UP, 30, fast_period=2, slow_period=4, use_current_price=False, **TREND)
    # fast(2)/slow(4) at the close of 13: 11.5 vs 12.25 (below); at 16: 14.5 vs 12.75 (above).
    # The cross is at the close of 16, two sessions before the last close (22).
    assert out.metrics["sessions_since_cross"] == 2.0
    assert out.signal is Signal.BUY


@pytest.mark.parametrize(("window", "signal"), [(1, None), (2, None), (3, Signal.BUY), (10, Signal.BUY)])
def test_ma_recent_cross_mode_signals_only_recent_crosses(window: int, signal: Signal | None) -> None:
    out = run(MA, CROSS_UP, 30, fast_period=2, slow_period=4, use_current_price=False, recent_sessions=window)
    assert out.metrics["sessions_since_cross"] == 2.0
    assert out.signal is signal  # cross 2 sessions ago: inside a window of 3 or more


def test_ma_recent_cross_today_with_current_price() -> None:
    # Completed closes fall; today's price jumps so the fast average crosses above right now.
    out = run(MA, [20, 18, 16, 14, 12], 40, fast_period=2, slow_period=4, recent_sessions=1)
    assert out.metrics["sessions_since_cross"] == 0.0 and out.signal is Signal.BUY
    # The same data without today's price: still a downtrend, no recent cross.
    out = run(MA, [20, 18, 16, 14, 12], 40, fast_period=2, slow_period=4, recent_sessions=1, use_current_price=False)
    assert out.signal is None and out.metrics["fast_ma"] < out.metrics["slow_ma"]


def test_ma_recent_cross_down_is_sell() -> None:
    falling = [10, 12, 14, 16, 18, 20, 17, 14]
    out = run(MA, falling, 11, fast_period=2, slow_period=4)
    assert out.signal is Signal.SELL and out.metrics["sessions_since_cross"] is not None


def test_ma_no_cross_in_history_gives_no_signal_in_recent_mode() -> None:
    assert run(MA, [1, 2, 3, 4, 5], 6, fast_period=2, slow_period=4).signal is None


def test_ma_completed_sessions_only() -> None:
    # Without the current price: series 1..5 -> fast 4.5, slow 3.5. A crash today would not count.
    out = run(MA, [1, 2, 3, 4, 5], 0.5, fast_period=2, slow_period=4, use_current_price=False, **TREND)
    assert (out.metrics["fast_ma"], out.metrics["slow_ma"]) == (4.5, 3.5)
    assert out.signal is Signal.BUY
    assert run(MA, [1, 2, 3, 4, 5], 0.5, fast_period=2, slow_period=4, **TREND).signal is Signal.SELL


def test_ma_ema_and_sma_differ() -> None:
    closes = [100.0] * 30 + [110.0] * 3
    sma_out = run(MA, closes, 110, fast_period=5, slow_period=20, average_type="SMA", **TREND)
    ema_out = run(MA, closes, 110, fast_period=5, slow_period=20, average_type="EMA", **TREND)
    assert ema_out.metrics["slow_ma"] != sma_out.metrics["slow_ma"]
    assert ema_out.signal is Signal.BUY and sma_out.signal is Signal.BUY
    # A perfectly flat history has equal averages (no side), so there is no cross to count.
    assert ema_out.metrics["sessions_since_cross"] is None and sma_out.metrics["sessions_since_cross"] is None


def test_ma_insufficient_history() -> None:
    out = run(MA, [1, 2, 3], 4, fast_period=2, slow_period=4)
    assert out.status is CalculationStatus.INSUFFICIENT_DATA and out.signal is None and out.metrics == {}


@pytest.mark.parametrize(
    ("config", "field"),
    [({"fast_period": 200, "slow_period": 200}, "fast_period"), ({"fast_period": 1}, "fast_period"),
     ({"slow_period": 401}, "slow_period"), ({"average_type": "WMA"}, "average_type"),
     ({"use_current_price": "yes"}, "use_current_price"), ({"signal_mode": "Cross"}, "signal_mode"),
     ({"recent_sessions": 0}, "recent_sessions"), ({"recent_sessions": 251}, "recent_sessions")],
)
def test_ma_invalid_configuration(config: dict, field: str) -> None:
    with pytest.raises(ConfigValidationError) as info:
        MA.validate_config(config)
    assert field in info.value.errors


# -- shared --------------------------------------------------------------------------------------------------


def test_all_strategies_are_discovered_with_explanations() -> None:
    discover_strategies()
    for name in ("mean_reversion", "rsi", "ma_crossover"):
        schema = strategy_registry.implementation(name)().get_config_schema()
        assert len(schema.explanation) > 500
        assert "## Signals" in schema.explanation and "## Things to know" in schema.explanation
        assert schema.explanation == schema.explanation.strip()
