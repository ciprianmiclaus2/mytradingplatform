"""RSI configuration, outputs and user-facing explanation."""

from __future__ import annotations

from app.strategies.models import OutputColumn, OutputFormat, ParameterType, StrategyParameter

PERIOD_MAX = 100
# History used to warm up Wilder's smoothing: this many periods (enough for
# the starting point to stop mattering), but the RSI is still calculated
# when less history exists.
WARMUP_PERIODS = 10

PARAMETERS = (
    StrategyParameter(
        name="period",
        type=ParameterType.INTEGER,
        title="Period (sessions)",
        description="Number of daily price changes averaged. 14 is the standard setting",
        default=14,
        minimum=2,
        maximum=PERIOD_MAX,
    ),
    StrategyParameter(
        name="oversold",
        type=ParameterType.NUMBER,
        title="Oversold level",
        description="BUY when the RSI is at or below this level",
        default=30.0,
        minimum=0,
        maximum=100,
    ),
    StrategyParameter(
        name="overbought",
        type=ParameterType.NUMBER,
        title="Overbought level",
        description="SELL when the RSI is at or above this level",
        default=70.0,
        minimum=0,
        maximum=100,
    ),
)

OUTPUTS = (
    OutputColumn(name="rsi", title="RSI", format=OutputFormat.NUMBER,
                 description="Relative Strength Index, 0 to 100"),
    OutputColumn(name="average_gain", title="Avg Gain", format=OutputFormat.PRICE,
                 description="Smoothed average daily gain"),
    OutputColumn(name="average_loss", title="Avg Loss", format=OutputFormat.PRICE,
                 description="Smoothed average daily loss"),
)

EXPLANATION = """
The Relative Strength Index (RSI), created by J. Welles Wilder in 1978, measures how strongly a price has been rising or falling recently. It runs from 0 to 100. Here it is used as a mean-reversion signal: a stock that has fallen hard and fast is treated as "oversold" and likely to bounce, and one that has risen hard and fast as "overbought" and likely to pull back.

## How it is calculated

- Take the daily price changes: each completed session's close minus the one before, and finally the current price minus the last close.
- Split them into gains (up days) and losses (down days, as positive amounts).
- Average the first Period gains and losses, then smooth each later day in: new average = (previous average × (Period − 1) + today's value) ÷ Period. This is Wilder's smoothing, the standard method used by most charting tools.
- RS = average gain ÷ average loss, and RSI = 100 − 100 ÷ (1 + RS).

An RSI of 50 means gains and losses have been balanced. 100 means there were no losses at all in the smoothed window; 0 means no gains.

## Signals

- BUY when the RSI is at or below the Oversold level (default 30).
- SELL when the RSI is at or above the Overbought level (default 70).
- No signal in between.

A signal describes the current condition, not an instruction to trade. The signal history records when a ticker enters or leaves the oversold or overbought zone.

## Settings

- Period: the number of price changes averaged. A shorter period (e.g. 7) reacts faster and gives more signals; a longer one (e.g. 21) is smoother and gives fewer.
- Oversold and Overbought levels: 30/70 is standard. 20/80 gives fewer, more extreme signals.

## Things to know

- In a strong trend the RSI can stay overbought or oversold for weeks. A BUY in a falling market can keep falling. Many traders only act on BUY signals when the longer-term trend is up (see the Moving Average Crossover strategy).
- The current price is included, so during the trading day the RSI and the signal can change until the session closes.
- Wilder's smoothing depends a little on how much history is used. Up to Period × 10 sessions are used, so the value may differ slightly from other tools, mostly for recently listed stocks.
- Prices are regular closes (adjusted for splits, not dividends). A large dividend can show up as a down day.
""".strip()
