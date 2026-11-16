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
