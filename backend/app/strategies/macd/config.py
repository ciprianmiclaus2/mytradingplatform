"""MACD configuration, outputs and user-facing explanation."""

from __future__ import annotations

from app.strategies.ma_crossover.config import CROSS_SEARCH_SESSIONS, RECENT_CROSS, TREND
from app.strategies.models import OutputColumn, OutputFormat, ParameterType, StrategyParameter

__all__ = ["CROSS_SEARCH_SESSIONS", "EMA_WARMUP_PERIODS", "EXPLANATION", "OUTPUTS", "PARAMETERS", "RECENT_CROSS",
           "TREND"]

# The exponential averages are warmed up over this many slow periods of history.
EMA_WARMUP_PERIODS = 5

PARAMETERS = (
    StrategyParameter(
        name="fast_period",
        type=ParameterType.INTEGER,
        title="Fast EMA (sessions)",
        description="Length of the short exponential moving average. 12 is the standard setting",
        default=12,
        minimum=2,
        maximum=100,
    ),
    StrategyParameter(
        name="slow_period",
        type=ParameterType.INTEGER,
        title="Slow EMA (sessions)",
        description="Length of the long exponential moving average. Must be longer than the fast EMA. "
        "26 is the standard setting",
        default=26,
        minimum=3,
        maximum=200,
    ),
    StrategyParameter(
        name="signal_period",
        type=ParameterType.INTEGER,
        title="Signal line (sessions)",
        description="Length of the exponential average of the MACD line. 9 is the standard setting",
        default=9,
        minimum=2,
        maximum=50,
    ),
    StrategyParameter(
        name="signal_mode",
        type=ParameterType.STRING,
        title="Signal on",
        description="Recent cross: signal only when the MACD line crossed its signal line within the window below. "
        "Trend: always BUY or SELL, depending on which line is higher",
        default=RECENT_CROSS,
        choices=[RECENT_CROSS, TREND],
    ),
    StrategyParameter(
        name="recent_sessions",
        type=ParameterType.INTEGER,
        title="Recent cross window (sessions)",
        description="With 'Recent cross': how many of the latest sessions count as recent. 1 = only the latest session",
        default=3,
        minimum=1,
        maximum=CROSS_SEARCH_SESSIONS,
    ),
    StrategyParameter(
        name="use_current_price",
        type=ParameterType.BOOLEAN,
        title="Include current price",
        description="Include today's latest price in the averages. Untick to use completed sessions only, "
        "so signals cannot change during the trading day",
        default=True,
    ),
)

OUTPUTS = (
    OutputColumn(name="macd", title="MACD", format=OutputFormat.PRICE,
                 description="Fast EMA − slow EMA, in price units. Positive: short-term prices above long-term"),
    OutputColumn(name="signal_line", title="Signal Line", format=OutputFormat.PRICE,
                 description="Exponential average of the MACD line"),
    OutputColumn(name="histogram", title="Histogram", format=OutputFormat.PRICE,
                 description="MACD − signal line. Positive: momentum rising; its size shows how strongly"),
    OutputColumn(name="histogram_pct", title="Histogram %", format=OutputFormat.PERCENT,
                 description="Histogram as a percentage of the price, comparable across tickers"),
    OutputColumn(name="sessions_since_cross", title="Since Cross", format=OutputFormat.INTEGER,
                 description="Sessions since the MACD line last crossed its signal line (0 = the latest session). "
                 f"Blank: no cross in the last {CROSS_SEARCH_SESSIONS} sessions"),
)

EXPLANATION = """
MACD (Moving Average Convergence Divergence), created by Gerald Appel in the late 1970s, is one of the most widely used momentum indicators. It tracks the gap between a fast and a slow moving average of the price, and signals when that gap starts to grow or shrink. It reacts much sooner than a 50/200 moving average crossover, so it suits swing trading over days to weeks rather than long-term trends.

## How it is calculated

- MACD line = 12-session EMA − 26-session EMA (exponential moving averages, where recent sessions weigh more). It is positive when short-term prices are above the longer-term average, and grows while that gap widens.
- Signal line = 9-session EMA of the MACD line: a smoothed, slower copy of it.
- Histogram = MACD line − signal line. It is positive when the MACD line is above its signal line, meaning momentum is improving.
- Histogram % = histogram ÷ price × 100. MACD values are in price units, so a $500 stock has much larger values than a $20 one; Histogram % makes tickers comparable when sorting a watchlist.
- Since Cross: how many sessions ago the MACD line moved to its current side of the signal line. 0 means the latest session. Blank if there was no cross in the last 250 sessions.

## Signals

The classic signal is the MACD line crossing its signal line:

- Recent cross (default): BUY if the MACD line crossed above the signal line within the last N sessions (the Recent cross window, default 3); SELL if it crossed below. Otherwise no signal.
- Trend: BUY whenever the MACD line is above the signal line, SELL whenever it is below. Every ticker then has a signal, so this suits a momentum overview rather than alerts.

The MACD line's position relative to zero adds context: a BUY cross below zero happens while the longer trend is still down (an early, riskier turn); one above zero confirms an existing uptrend.

## Settings

- Fast, Slow and Signal line: 12/26/9 is the standard almost everywhere. Shorter settings such as 5/35/5 react faster but give more false signals.
- Signal on and Recent cross window: see Signals above. MACD lines cross much more often than 50/200 averages, so a short window (1 to 3 sessions) keeps the list focused on fresh signals.
- Include current price: when ticked, today's latest price is part of the averages, so a cross can appear and disappear during the day. Untick it to base signals on completed sessions only.

## Things to know

- In sideways markets the lines cross back and forth frequently, giving a string of false signals. A common filter is to only take BUY signals when the longer-term trend is up (see the Moving Average Crossover strategy).
- Exponential averages depend slightly on how much history is used. Up to five times the slow period of history plus 250 sessions for the cross search is used, so values can differ slightly from other tools, mostly for recently listed stocks.
- At least Slow EMA + Signal line − 1 prices are needed; stocks with less show "Insufficient data".
- Prices are regular closes (adjusted for splits, not dividends).
""".strip()
