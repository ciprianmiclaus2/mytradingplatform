"""Bollinger Bands and MACD strategies."""

from __future__ import annotations

import statistics

import pytest

from app.strategies.base import ConfigValidationError
from app.strategies.bollinger.config import WIDTH_RANK_SESSIONS
from app.strategies.bollinger.strategy import BollingerBandsStrategy
from app.strategies.indicators import macd_series
from app.strategies.macd.strategy import MacdStrategy
from app.strategies.models import CalculationStatus, Signal
from tests.unit.test_new_strategies import data, run

BB = BollingerBandsStrategy()
MACD = MacdStrategy()
CHOPPY = [10.0, 11.0, 10.0, 11.0, 10.0, 11.0, 10.0, 11.0, 10.0]

# -- Bollinger Bands ---------------------------------------------------------------------------------


def test_bollinger_bands_include_current_price() -> None:
    out = run(BB, CHOPPY[:-1], 10.0, period=4)
    window = [11.0, 10.0, 11.0, 10.0]  # last 3 closes + current price
    mean, std = statistics.fmean(window), statistics.pstdev(window)
    assert out.status is CalculationStatus.OK
    assert out.metrics["middle_band"] == pytest.approx(mean)
    assert out.metrics["upper_band"] == pytest.approx(mean + 2 * std)
    assert out.metrics["lower_band"] == pytest.approx(mean - 2 * std)
    assert out.metrics["percent_b"] == pytest.approx((10.0 - (mean - 2 * std)) / (4 * std))
    assert out.metrics["bandwidth"] == pytest.approx(4 * std / mean * 100)
    assert out.signal is None


@pytest.mark.parametrize(
    ("price", "mode", "signal"),
    [(8.0, "Mean reversion", Signal.BUY), (13.0, "Mean reversion", Signal.SELL),
     (8.0, "Breakout", Signal.SELL), (13.0, "Breakout", Signal.BUY), (10.5, "Breakout", None)],
)
def test_bollinger_signals(price: float, mode: str, signal: Signal | None) -> None:
    out = run(BB, CHOPPY, price, period=5, width=1.5, signal_mode=mode)
    assert out.signal is signal
    below, above = out.metrics["percent_b"] < 0, out.metrics["percent_b"] > 1
    assert (below or above) is (signal is not None)


def test_bollinger_width_setting_changes_signal() -> None:
    assert run(BB, CHOPPY, 12.0, period=5, width=1).signal is Signal.SELL
    assert run(BB, CHOPPY, 12.0, period=5, width=3).signal is None


def test_bollinger_completed_sessions_only_ignores_current_price() -> None:
    out = run(BB, CHOPPY, 50.0, period=8, use_current_price=False)
    assert out.metrics["middle_band"] == pytest.approx(statistics.fmean(CHOPPY[-8:]))
    assert out.signal is None  # the price spike is ignored
    assert run(BB, CHOPPY, 50.0, period=8).signal is Signal.SELL


def test_bollinger_short_period_cannot_exceed_the_bands() -> None:
    # The price is in its own window: with n values it is at most (n − 1) / √n deviations from the mean.
    assert run(BB, CHOPPY, 1000.0, period=5).metrics["percent_b"] < 1
    assert run(BB, CHOPPY, 1000.0, period=6).signal is Signal.SELL


def test_bollinger_flat_price_and_short_history() -> None:
    assert run(BB, [5.0, 5.0, 5.0], 5.0, period=4).status is CalculationStatus.INVALID_CALCULATION
    assert run(BB, [5.0, 6.0], 5.0, period=4).status is CalculationStatus.INSUFFICIENT_DATA
    assert run(BB, [5.0, 6.0, 7.0], 5.0, period=4).status is CalculationStatus.OK
    assert run(BB, [5.0, 6.0, 7.0], 5.0, period=4, use_current_price=False).status is CalculationStatus.INSUFFICIENT_DATA
    cfg = BB.validate_config({})
    assert BB.calculate(["T"], data([1.0] * 30, None), cfg)[0].status is CalculationStatus.NO_PRICE


def test_bollinger_width_rank() -> None:
    period = 5
    # Volatile history, then the last sessions calm down: the narrowest bands in the window (a squeeze).
    volatile = [10.0 if i % 2 else 12.0 for i in range(period + WIDTH_RANK_SESSIONS)]
    calm = volatile + [11.0, 11.1, 11.0, 11.1]
    squeeze = run(BB, calm, 11.0, period=period)
    assert squeeze.metrics["width_rank"] == 0.0
    # Calm history, then a volatile spell: the widest in the window.
    quiet = [11.0 if i % 2 else 11.1 for i in range(period + WIDTH_RANK_SESSIONS)]
    burst = run(BB, [*quiet, 9.0, 13.0, 9.0], 13.0, period=period)
    assert burst.metrics["width_rank"] == 100.0
    # Not enough history to rank: blank, but the rest is calculated.
    short = run(BB, CHOPPY, 10.0, period=period)
    assert short.status is CalculationStatus.OK and short.metrics["width_rank"] is None


def test_bollinger_requests_history_for_width_rank() -> None:
    assert BB.required_sessions(BB.validate_config({})) == 20 + WIDTH_RANK_SESSIONS


# -- MACD --------------------------------------------------------------------------------------------

FAST = {"fast_period": 2, "slow_period": 4, "signal_period": 3}


def test_macd_values_match_indicator() -> None:
    closes = [10.0, 11.0, 12.0, 11.5, 12.5, 13.0, 12.0, 12.8]
    out = run(MACD, closes, 13.2, **FAST)
    macd, signal = macd_series([*closes, 13.2], 2, 4, 3)
    assert out.status is CalculationStatus.OK
    assert out.metrics["macd"] == pytest.approx(macd[-1])
    assert out.metrics["signal_line"] == pytest.approx(signal[-1])
    histogram = macd[-1] - signal[-1]  # type: ignore[operator]
    assert out.metrics["histogram"] == pytest.approx(histogram)
    assert out.metrics["histogram_pct"] == pytest.approx(histogram / 13.2 * 100)


def test_macd_trend_mode_follows_side() -> None:
    rising = [10.0 * 1.05**i for i in range(20)]  # accelerating: momentum keeps rising
    falling = list(reversed(rising))
    up = run(MACD, rising, rising[-1] + 2, signal_mode="Trend", **FAST)
    down = run(MACD, falling, falling[-1] - 2, signal_mode="Trend", **FAST)
    assert up.signal is Signal.BUY and up.metrics["histogram"] > 0
    assert down.signal is Signal.SELL and down.metrics["histogram"] < 0


def test_macd_recent_cross_mode() -> None:
    # An accelerating decline, then a sharp turn up in the latest sessions.
    closes = [40.0 - 1.1**i for i in range(20)] + [34.0, 36.0]
    out = run(MACD, closes, 38.0, **FAST)
    since = out.metrics["sessions_since_cross"]
    assert since is not None and since < 3 and out.signal is Signal.BUY
    # Outside the window: no signal, but Since Cross is still reported.
    stale = run(MACD, closes + [38.0, 40.0, 42.0, 44.0], 46.0, recent_sessions=1, **FAST)
    assert stale.signal is None and stale.metrics["sessions_since_cross"] >= 1
    # A steady accelerating trend with no cross in the history: no signal by default.
    steady = run(MACD, [10.0 * 1.05**i for i in range(30)], 10.0 * 1.05**30, **FAST)
    assert steady.metrics["histogram"] > 0
    assert steady.signal is None and steady.metrics["sessions_since_cross"] is None


def test_macd_linear_price_has_no_cross() -> None:
    # With a perfectly linear price the MACD is constant and equals its signal line: no side, no signal.
    out = run(MACD, [10.0 + i * 0.5 for i in range(30)], 25.0, signal_mode="Trend", **FAST)
    assert out.metrics["histogram"] == pytest.approx(0, abs=1e-9) and out.signal is None


def test_macd_recent_cross_down_is_sell() -> None:
    closes = [10.0 * 1.05**i for i in range(20)] + [24.0, 21.0]
    assert run(MACD, closes, 20.0, **FAST).signal is Signal.SELL


def test_macd_history_requirements() -> None:
    assert MACD.required_sessions(MACD.validate_config({})) == 26 * 5 + 250
    # Slow (4) + signal (3) − 1 = 6 prices; the current price can be the last one.
    assert run(MACD, [1.0, 2.0, 3.0, 4.0], 5.0, **FAST).status is CalculationStatus.INSUFFICIENT_DATA
    assert run(MACD, [1.0, 2.0, 3.0, 4.0, 5.0], 6.0, **FAST).status is CalculationStatus.OK
    assert run(MACD, [1.0, 2.0, 3.0, 4.0, 5.0], 6.0, use_current_price=False,
               **FAST).status is CalculationStatus.INSUFFICIENT_DATA
    assert run(MACD, [1.0, 2.0, 3.0, 4.0, 5.0, 6.0], 7.0, use_current_price=False,
               **FAST).status is CalculationStatus.OK


def test_macd_invalid_configuration() -> None:
    with pytest.raises(ConfigValidationError) as exc:
        MACD.validate_config({"fast_period": 26, "slow_period": 26})
    assert "fast_period" in exc.value.errors
