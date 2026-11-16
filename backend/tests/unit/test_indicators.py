from __future__ import annotations

import numpy as np
import pytest

from app.strategies.indicators import ema, ema_series, sessions_since_cross, sma, sma_series, wilder_rsi

# StockCharts ChartSchool RSI worked example (cs-rsi.xls), 14-period Wilder RSI.
REFERENCE_PRICES = [
    44.3389, 44.0902, 44.1497, 43.6124, 44.2778, 44.8264, 45.0955, 45.4245, 45.8433, 46.0826, 45.8931,
    46.0328, 45.614, 46.282, 46.282, 46.0028, 46.0328, 46.4116, 46.2222, 45.6439, 46.2122, 46.2521,
    45.7137, 46.4515, 45.7835, 45.3548, 44.0288, 44.1783, 44.2181, 44.5672, 43.4205, 42.6628, 43.1314,
]
REFERENCE_RSI = [70.53, 66.32, 66.55, 69.41, 66.36, 57.97, 62.93, 63.26, 56.06, 62.38, 54.71, 50.42,
                 39.99, 41.46, 41.87, 45.46, 37.30, 33.08, 37.77]


def test_rsi_matches_published_reference() -> None:
    values = [wilder_rsi(REFERENCE_PRICES[:n], 14)[0] for n in range(15, len(REFERENCE_PRICES) + 1)]
    assert values == pytest.approx(REFERENCE_RSI, abs=0.005)


def test_rsi_first_value_uses_simple_averages() -> None:
    rsi, gain, loss = wilder_rsi([10, 11, 10, 12], 3)  # changes +1, -1, +2
    assert (gain, loss) == pytest.approx((1.0, 1 / 3))
    assert rsi == pytest.approx(75.0)


@pytest.mark.parametrize(("prices", "expected"), [([1, 2, 3, 4, 5], 100.0), ([5, 4, 3, 2, 1], 0.0)])
def test_rsi_extremes(prices: list[float], expected: float) -> None:
    assert wilder_rsi(prices, 2)[0] == expected


def test_rsi_is_symmetric() -> None:
    """Mirroring the price path (gains become losses) mirrors the RSI around 50."""
    up = [10, 11, 10.5, 12, 11, 11.8, 12.4]
    down = [20 - p for p in up]
    assert wilder_rsi(up, 3)[0] + wilder_rsi(down, 3)[0] == pytest.approx(100.0)


def test_rsi_is_undefined_for_a_flat_price() -> None:
    assert wilder_rsi([5, 5, 5, 5], 3)[0] is None


def test_rsi_needs_period_plus_one_prices() -> None:
    with pytest.raises(ValueError):
        wilder_rsi([1, 2, 3], 3)


def test_sma_uses_the_last_values() -> None:
    assert sma([1, 2, 3, 4, 5], 2) == 4.5
    assert sma([1, 2, 3, 4, 5], 5) == 3.0
    with pytest.raises(ValueError):
        sma([1, 2], 3)


def test_ema_seeded_with_sma_then_smoothed() -> None:
    # period 3: alpha 0.5; seed mean(1,2,3)=2; then 4 -> 3, then 8 -> 5.5
    assert ema([1, 2, 3, 4, 8], 3) == pytest.approx(5.5)
    assert ema([1, 2, 3], 3) == pytest.approx(2.0)


def test_ema_matches_pandas_style_recursion_on_random_data() -> None:
    rng = np.random.default_rng(7)
    values = list(100 + rng.normal(0, 1, 300).cumsum())
    alpha = 2 / 21
    expected = float(np.mean(values[:20]))
    for v in values[20:]:
        expected = alpha * v + (1 - alpha) * expected
    assert ema(values, 20) == pytest.approx(expected)


def test_series_match_single_value_functions() -> None:
    rng = np.random.default_rng(3)
    values = list(100 + rng.normal(0, 1, 120).cumsum())
    smas, emas = sma_series(values, 10), ema_series(values, 10)
    assert smas[:9] == [None] * 9 and emas[:9] == [None] * 9
    for i in range(9, len(values)):
        assert smas[i] == pytest.approx(sma(values[: i + 1], 10))
        assert emas[i] == pytest.approx(ema(values[: i + 1], 10))


@pytest.mark.parametrize(
    ("fast", "slow", "expected"),
    [
        ([1, 1, 3, 3], [2, 2, 2, 2], 1),           # crossed above at position 2, last is 3
        ([1, 1, 1, 3], [2, 2, 2, 2], 0),           # crossed in the latest position
        ([3, 1, 1, 1], [2, 2, 2, 2], 2),           # crossed below at position 1
        ([3, 3, 3, 3], [2, 2, 2, 2], None),        # no cross in the series
        ([1, 2, 3, 3], [2, 2, 2, 2], 1),           # an equal position is not a side
        ([1, 3, 3, 2], [2, 2, 2, 2], None),        # equal now: no side, no cross count
        ([None, 1, 3, 3], [None, 2, 2, 2], 1),
        ([None, 3, 3, 3], [None, 2, 2, 2], None),  # history runs out before a cross
        ([], [], None),
    ],
)
def test_sessions_since_cross(fast: list, slow: list, expected: int | None) -> None:
    assert sessions_since_cross(fast, slow) == expected
