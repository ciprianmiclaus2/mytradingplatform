"""Moving average crossover configuration, outputs and user-facing explanation."""

from __future__ import annotations

from app.strategies.models import OutputColumn, OutputFormat, ParameterType, StrategyParameter

FAST_MAX = 250
SLOW_MAX = 400
# Exponential averages are warmed up over this many slow periods of history.
EMA_WARMUP_PERIODS = 3
# How far back (sessions) to look for the last cross.
CROSS_SEARCH_SESSIONS = 250
RECENT_CROSS = "Recent cross"
TREND = "Trend"

PARAMETERS = (
    StrategyParameter(
        name="fast_period",
        type=ParameterType.INTEGER,
        title="Fast average (sessions)",
        description="Length of the short-term moving average",
        default=50,
        minimum=2,
        maximum=FAST_MAX,
    ),
    StrategyParameter(
        name="slow_period",
        type=ParameterType.INTEGER,
        title="Slow average (sessions)",
        description="Length of the long-term moving average. Must be longer than the fast average",
        default=200,
        minimum=3,
        maximum=SLOW_MAX,
    ),
    StrategyParameter(
        name="average_type",
        type=ParameterType.STRING,
        title="Average type",
        description="SMA: simple average, every session weighted equally. EMA: exponential, recent sessions weigh more",
        default="SMA",
        choices=["SMA", "EMA"],
    ),
    StrategyParameter(
        name="signal_mode",
        type=ParameterType.STRING,
        title="Signal on",
        description="Recent cross: signal only when the averages crossed within the window below. "
        "Trend: always BUY or SELL, depending on which average is higher",
        default=RECENT_CROSS,
        choices=[RECENT_CROSS, TREND],
    ),
    StrategyParameter(
        name="recent_sessions",
        type=ParameterType.INTEGER,
        title="Recent cross window (sessions)",
        description="With 'Recent cross': how many of the latest sessions count as recent. 1 = only the latest session",
        default=5,
        minimum=1,
        maximum=CROSS_SEARCH_SESSIONS,
    ),
    StrategyParameter(
        name="use_current_price",
        type=ParameterType.BOOLEAN,
        title="Include current price",
        description="Include today's latest price in both averages. Untick to use completed sessions only, "
        "so signals cannot change during the trading day",
        default=True,
    ),
)

OUTPUTS = (
    OutputColumn(name="fast_ma", title="Fast MA", format=OutputFormat.PRICE,
                 description="Fast moving average"),
    OutputColumn(name="slow_ma", title="Slow MA", format=OutputFormat.PRICE,
                 description="Slow moving average"),
    OutputColumn(name="spread_pct", title="Spread %", format=OutputFormat.PERCENT,
                 description="(fast - slow) / slow × 100. Positive: uptrend"),
    OutputColumn(name="sessions_since_cross", title="Since Cross", format=OutputFormat.INTEGER,
                 description="Sessions since the averages last crossed (0 = the latest session). "
                 f"Blank: no cross in the last {CROSS_SEARCH_SESSIONS} sessions"),
)

EXPLANATION = """
A moving average crossover is a trend-following strategy. It compares a short-term average of the price (the fast average) with a long-term one (the slow average). When the fast average is above the slow one, recent prices are higher than the longer-term norm and the trend is considered up; when it is below, the trend is considered down. It is the opposite philosophy to Mean Reversion and RSI: it bets that a move will continue, not reverse.

The best-known version uses 50- and 200-session averages. The fast average crossing above the slow one is called a "golden cross"; crossing below is a "death cross".

## How it is calculated

- SMA (simple moving average): the plain average of the last N closes.
- EMA (exponential moving average): a weighted average where each session counts 2 ÷ (N + 1) of the new value and older sessions fade out gradually. EMAs react faster to recent moves. They are warmed up over up to three times the slow period of history.
- Spread % = (fast average − slow average) ÷ slow average × 100. It shows how far apart the averages are: a large positive spread is a strong uptrend; a spread near zero means a cross may be close.
- Since Cross: how many sessions ago the fast average moved to its current side of the slow average. 0 means the cross happened in the latest session. It is blank if there was no cross in the last 250 sessions.

## Signals

Every stock's fast average is either above or below its slow average, so the trend alone would give almost every ticker a signal. What matters is the cross itself, so by default the strategy signals recent crosses only:

- Recent cross (default): BUY if the fast average crossed above the slow average within the last N sessions (the Recent cross window, default 5); SELL if it crossed below. Otherwise no signal. A watchlist then shows only the few tickers that have just changed trend.
- Trend: BUY whenever the fast average is above the slow one, SELL whenever it is below. Useful as a trend filter, for example to check the direction before acting on an RSI or Mean Reversion signal.

In both modes, Since Cross and Spread % show how established the trend is.

## Settings

- Fast and Slow average: 50/200 is the classic long-term setting. 20/50 or 10/30 react faster but give more false signals in sideways markets.
- Average type: SMA is the classic choice. EMA reacts sooner to new trends at the cost of more whipsaws.
- Signal on and Recent cross window: see Signals above. A window of 1 shows only crosses in the latest session; 5 is about a trading week; 20 about a month.
- Include current price: when ticked, today's latest price is part of both averages, so a cross can appear and disappear during the day. Untick it to base signals on completed sessions only.

## Things to know

- Moving averages lag: by the time a 50/200 cross happens, much of the move may already be over.
- In sideways markets the averages cross back and forth ("whipsaws"), producing a string of losing signals.
- The slow average needs at least Slow average sessions of history, so recently listed stocks show "Insufficient data". To find the last cross, up to Slow average + 250 sessions are used, so the first run downloads about two years of history per ticker.
- Prices are regular closes (adjusted for splits, not dividends). Over 200 sessions, dividends make the averages slightly lower than a total-return series would.
""".strip()
