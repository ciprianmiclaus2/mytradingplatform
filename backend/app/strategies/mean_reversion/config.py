"""Mean Reversion configuration (plan §9.1)."""

from __future__ import annotations

from app.strategies.models import OutputColumn, OutputFormat, ParameterType, StrategyParameter

LOOKBACK_MAX = 500

PARAMETERS = (
    StrategyParameter(
        name="lookback_days",
        type=ParameterType.INTEGER,
        title="Lookback (sessions)",
        description="Number of previous completed trading sessions used for the mean and standard deviation",
        default=20,
        minimum=2,
        maximum=LOOKBACK_MAX,
    ),
    StrategyParameter(
        name="buy_threshold",
        type=ParameterType.NUMBER,
        title="Buy threshold (Z)",
        description="BUY when the z-score is at or below this value",
        default=-2.0,
    ),
    StrategyParameter(
        name="sell_threshold",
        type=ParameterType.NUMBER,
        title="Sell threshold (Z)",
        description="SELL when the z-score is at or above this value",
        default=2.0,
    ),
)

OUTPUTS = (
    OutputColumn(name="mean", title="Mean", format=OutputFormat.PRICE,
                 description="Mean of the previous closes"),
    OutputColumn(name="standard_deviation", title="Std Dev", format=OutputFormat.PRICE,
                 description="Population standard deviation of the previous closes"),
    OutputColumn(name="z_score", title="Z-Score", format=OutputFormat.NUMBER,
                 description="(current price - mean) / standard deviation"),
)

EXPLANATION = """
Mean reversion assumes that a price which has moved unusually far from its recent average tends to move back towards it. This strategy measures how unusual today's price is, in units of recent volatility, and flags prices that are unusually low (BUY) or unusually high (SELL).

## How it is calculated

- Take the regular closes of the previous Lookback completed sessions (today's session is not included).
- Mean: their average.
- Std Dev: their population standard deviation, a measure of how much the price normally moves around the mean.
- Z-Score = (current price − mean) ÷ standard deviation. It says how many "normal moves" the price is away from its average: 0 is at the average, −2 is two standard deviations below it.

If prices were normally distributed, a z-score beyond ±2 would happen about 5% of the time.

## Signals

- BUY when the z-score is at or below the Buy threshold (default −2): the price is unusually low.
- SELL when the z-score is at or above the Sell threshold (default +2): the price is unusually high.
- No signal in between.

A signal describes the current condition, not an instruction to trade. The signal history records when a ticker enters or leaves a signal.

## Settings

- Lookback: the number of previous sessions used. 20 (about a month) is common. Longer lookbacks give a steadier mean and fewer signals.
- Buy and Sell thresholds: ±2 is standard. ±1.5 gives more signals; ±2.5 fewer, more extreme ones.

## Things to know

- Prices do not have to revert. After news (earnings, a profit warning) a price can stay far from its old average and keep going. A low z-score in a falling market can keep getting lower.
- The current price is used, so during the trading day the z-score and the signal can change until the session closes.
- A stock that has barely moved has a very small standard deviation, so even a small move gives a large z-score.
- Prices are regular closes (adjusted for splits, not dividends). On the day a stock goes ex-dividend, the price drop can look like an unusual move.
""".strip()
