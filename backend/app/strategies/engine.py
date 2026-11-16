"""Strategy execution engine (plan §8.4).

1. Resolve the strategy.        2. Validate the configuration.
3. Receive ticker symbols.      4. Retrieve market data via MarketDataService.
5. Execute the strategy.        6. Normalise the result.
7. Record signal transitions.   8. Return the result.

The engine only ever receives ticker symbols; whether they came from a
portfolio, favourites, positions or a manual list is the caller's concern.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

from app.market_data.models import HistoryResult, LatestPrice
from app.market_data.service import MarketDataService
from app.schemas.errors import AppError, NotFoundError
from app.strategies.base import BaseStrategy, ConfigValidationError, StrategyMarketData
from app.strategies.models import (
    CalculationStatus,
    StrategyOutput,
    StrategyRunResult,
    StrategySchema,
    TickerResult,
)
from app.strategies.registry import StrategyRegistry
from app.strategies.signals import SignalStore, Transition

logger = logging.getLogger(__name__)


class StrategyConfigError(AppError):
    status_code = 422
    code = "invalid_strategy_config"


class StrategyExecutionError(AppError):
    status_code = 500
    code = "strategy_failed"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class StrategyEngine:
    def __init__(
        self,
        registry: StrategyRegistry,
        market_data: MarketDataService,
        signals: SignalStore,
        *,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self.registry = registry
        self.market_data = market_data
        self.signals = signals
        self.clock = clock

    # -- discovery -------------------------------------------------------------

    def list(self) -> list[StrategySchema]:
        return self.registry.schemas()

    def schema(self, name: str) -> StrategySchema:
        return self._resolve(name).get_config_schema()

    def _resolve(self, name: str) -> BaseStrategy:
        strategy = self.registry.get(name)
        if strategy is None:
            raise NotFoundError(f"Strategy {name!r} not found")
        return strategy

    # -- execution ---------------------------------------------------------------

    def run(
        self,
        name: str,
        tickers: list[str],
        raw_config: dict[str, Any],
        instance_id: str | None = None,
    ) -> StrategyRunResult:
        strategy = self._resolve(name)
        try:
            config = strategy.validate_config(raw_config)
        except ConfigValidationError as exc:
            raise StrategyConfigError(f"Invalid configuration for {name}: {exc}", details=exc.errors) from exc

        tickers = list(dict.fromkeys(tickers))
        started = self.clock()
        market = self._market_data(tickers, strategy.required_sessions(config))
        try:
            outputs = strategy.calculate(tickers, market, config)
        except Exception as exc:
            logger.exception("strategy execution failed", extra={"strategy": name})
            raise StrategyExecutionError(f"Strategy {name} failed: {exc}") from exc

        results = self._normalise(tickers, outputs, market)
        if instance_id is not None:
            results = self._track_signals(strategy, instance_id, results, started)
        logger.info(
            "strategy executed",
            extra={
                "strategy": name,
                "instance_id": instance_id,
                "tickers": len(tickers),
                "signals": sum(1 for r in results if r.signal),
            },
        )
        return StrategyRunResult(
            strategy=name, instance_id=instance_id, config=config, calculated_at=started, results=results
        )

    def _market_data(self, tickers: list[str], sessions: int) -> StrategyMarketData:
        quotes = self.market_data.get_latest_prices(tickers) if tickers else {}
        history: dict[str, HistoryResult] = {}
        if sessions > 0:
            # History is the completed sessions before the quote's session, which
            # excludes the current (possibly incomplete) session. Tickers without a
            # quote cannot be evaluated, so their history is not fetched.
            by_session: dict[date, list[str]] = defaultdict(list)
            for ticker in tickers:
                quote = quotes.get(ticker)
                if quote is not None:
                    by_session[_session_date(quote)].append(ticker)
            for before, group in by_session.items():
                history.update(self.market_data.get_closes_before(group, before, sessions))
        return StrategyMarketData(quotes=quotes, history=history)

    def _normalise(
        self, tickers: list[str], outputs: list[StrategyOutput], market: StrategyMarketData
    ) -> list[TickerResult]:
        by_ticker: dict[str, StrategyOutput] = {}
        for output in outputs:
            if output.ticker in tickers and output.ticker not in by_ticker:
                by_ticker[output.ticker] = output
        results = []
        for ticker in tickers:
            output = by_ticker.get(ticker) or StrategyOutput(
                ticker=ticker, status=CalculationStatus.DATA_ERROR, message="Strategy returned no result"
            )
            # A signal is only valid for a successful calculation.
            signal = output.signal if output.status is CalculationStatus.OK else None
            quote = market.quote(ticker)
            results.append(
                TickerResult(
                    ticker=ticker,
                    status=output.status,
                    signal=signal,
                    message=output.message,
                    current_price=quote.price if quote else None,
                    currency=quote.currency if quote else None,
                    daily_change=quote.daily_change if quote else None,
                    daily_change_pct=quote.daily_change_pct if quote else None,
                    price_timestamp=quote.timestamp if quote else None,
                    stale=quote.stale if quote else False,
                    metrics=output.metrics,
                )
            )
        return results

    def _track_signals(
        self, strategy: BaseStrategy, instance_id: str, results: list[TickerResult], at: datetime
    ) -> list[TickerResult]:
        """Record signal-state changes and annotate results with their history.

        Only successful calculations take part: a ticker with insufficient data
        or an invalid calculation keeps its previous state and is not annotated.
        """
        with self.signals.store.lock.hold():
            states = self.signals.current_states(instance_id, [r.ticker for r in results])
            transitions: list[Transition] = []
            annotated = []
            for result in results:
                if result.status is not CalculationStatus.OK:
                    annotated.append(result)
                    continue
                state = states.get(result.ticker)
                current = state.signal if state else None
                if result.signal != current:
                    metric = strategy.primary_metric
                    transitions.append(
                        Transition(
                            ticker=result.ticker,
                            previous=current,
                            new=result.signal,
                            metric_name=metric,
                            metric_value=result.metrics.get(metric) if metric else None,
                            current_price=result.current_price,
                        )
                    )
                    update = {"previous_signal": current, "signal_changed_at": at, "is_new_signal": True}
                elif state is not None:
                    update = {"previous_signal": state.previous, "signal_changed_at": state.since}
                else:
                    update = {}
                annotated.append(result.model_copy(update=update))
            self.signals.record(instance_id, strategy.name, at, transitions)
        if transitions:
            logger.info(
                "signal transitions recorded",
                extra={"instance_id": instance_id, "transitions": [(t.ticker, t.previous, t.new) for t in transitions]},
            )
        return annotated


def _session_date(quote: LatestPrice) -> date:
    return quote.trading_date or quote.timestamp.astimezone(UTC).date()

