"""Bollinger Bands configuration, outputs and user-facing explanation."""

from __future__ import annotations

from app.strategies.models import OutputColumn, OutputFormat, ParameterType, StrategyParameter

PERIOD_MAX = 250
# Sessions of band width the current width is ranked against (about six months).
WIDTH_RANK_SESSIONS = 125
MEAN_REVERSION = "Mean reversion"
BREAKOUT = "Breakout"

PARAMETERS = (
    StrategyParameter(
        name="period",
        type=ParameterType.INTEGER,
        title="Period (sessions)",
        description="Length of the middle band (a simple moving average). 20 is the standard setting",
        default=20,
        minimum=2,
        maximum=PERIOD_MAX,
    ),
    StrategyParameter(
        name="width",
        type=ParameterType.NUMBER,
        title="Band width (standard deviations)",
        description="Distance of the upper and lower bands from the middle band. 2 is the standard setting",
        default=2.0,
        minimum=0.5,
        maximum=5,
    ),
    StrategyParameter(
        name="signal_mode",
        type=ParameterType.STRING,
        title="Signal on",
        description="Mean reversion: BUY at or below the lower band, SELL at or above the upper band. "
        "Breakout: the opposite, BUY at or above the upper band, SELL at or below the lower band",
        default=MEAN_REVERSION,
        choices=[MEAN_REVERSION, BREAKOUT],
    ),
    StrategyParameter(
        name="use_current_price",
        type=ParameterType.BOOLEAN,
        title="Include current price",
        description="Use today's latest price as the last value of the bands and for the signal. "
        "Untick to use completed sessions only, so signals cannot change during the trading day",
        default=True,
    ),
)

OUTPUTS = (
    OutputColumn(name="lower_band", title="Lower", format=OutputFormat.PRICE,
                 description="Lower band: middle band − width × standard deviation"),
    OutputColumn(name="middle_band", title="Middle", format=OutputFormat.PRICE,
                 description="Middle band: simple moving average"),
    OutputColumn(name="upper_band", title="Upper", format=OutputFormat.PRICE,
                 description="Upper band: middle band + width × standard deviation"),
    OutputColumn(name="percent_b", title="%B", format=OutputFormat.NUMBER,
                 description="Where the price sits between the bands: 0 = lower band, 0.5 = middle, 1 = upper band. "
                 "Below 0 or above 1: outside the bands"),
    OutputColumn(name="bandwidth", title="Width %", format=OutputFormat.NUMBER,
                 description="(upper − lower) ÷ middle × 100: how wide the bands are, as a percentage of the price"),
    OutputColumn(name="width_rank", title="Width Rank", format=OutputFormat.INTEGER,
                 description=f"Percentage of the previous {WIDTH_RANK_SESSIONS} sessions with narrower bands than now. "
                 "0 = the narrowest in that time (a squeeze). Blank: not enough history"),
)

EXPLANATION = f"""
Bollinger Bands, created by John Bollinger in the 1980s, draw a band around a moving average of the price. The band widens when the price is volatile and narrows when it is calm, so it adapts to each stock. About 90% of closes fall inside the standard bands; a price outside them is unusually far from its recent average.

## How it is calculated

- Middle band: the simple average of the last Period prices (default 20).
- Standard deviation: how spread out those same prices are around the middle band (population standard deviation, as Bollinger defines it).
- Upper band = middle + Band width × standard deviation; lower band = middle − Band width × standard deviation (default 2).
- %B = (price − lower) ÷ (upper − lower). 0 means the price is on the lower band, 0.5 on the middle band, 1 on the upper band. Below 0 or above 1 means outside the bands.
- Width % = (upper − lower) ÷ middle × 100, the width of the bands relative to the price.
- Width Rank: the percentage of the previous {WIDTH_RANK_SESSIONS} sessions (about six months) whose bands were narrower than today's. 0 means the bands are the narrowest they have been in that time.

## Signals

The bands are used in two opposite ways, chosen with Signal on:

- Mean reversion (default): BUY when the price is at or below the lower band (unusually low, expected to bounce back towards the average); SELL when it is at or above the upper band. No signal in between. This is the same idea as the Mean Reversion strategy: with the standard settings the lower band is a z-score of −2.
- Breakout: BUY when the price is at or above the upper band (a strong move that may continue); SELL when it is at or below the lower band. This is trend following and works best right after a squeeze.

## The squeeze

Periods of low volatility tend to be followed by periods of high volatility. When the bands become unusually narrow (a Width Rank near 0), Bollinger calls it a squeeze: a big move is often near, although the bands do not say in which direction. Sort the table by Width Rank to find squeezes in a watchlist, then watch for a breakout.

## Settings

- Period: 20 is the standard. 10 reacts faster and suits short-term trading; 50 is smoother and slower.
- Band width: 2 is the standard. Bollinger suggests 1.9 with a period of 10 and 2.1 with a period of 50. A wider band gives fewer, more extreme signals.
- Include current price: when ticked, today's latest price is part of the bands and decides the signal, so a signal can appear and disappear during the day. Untick it to use completed sessions only.

## Things to know

- Touching a band is not a signal by itself in Bollinger's own method: in a strong uptrend the price can "walk" along the upper band for weeks. Mean reversion signals work best in sideways markets; consider checking the trend first (see the Moving Average Crossover strategy).
- The price is part of the average it is compared with, which limits how far outside the bands it can get. With a very short period this matters: at a Band width of 2, a Period of 5 or less can never produce a signal.
- The bands need at least Period sessions of history; the Width Rank needs Period + {WIDTH_RANK_SESSIONS} sessions and is blank until then.
- Prices are regular closes (adjusted for splits, not dividends).
""".strip()
