from __future__ import annotations

import ast
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.market_data.base import ProviderError
from app.market_data.service import MarketDataService
from app.persistence.derived import derived_registry
from app.persistence.parquet import ParquetStore
from app.schemas.errors import NotFoundError
from app.strategies.base import ConfigValidationError
from app.strategies.engine import StrategyConfigError, StrategyEngine, StrategyExecutionError
from app.strategies.models import CalculationStatus, ParameterType, Signal, StrategyParameter
from app.strategies.registry import StrategyRegistry, discover_strategies, strategy_registry
from app.strategies.signals import SignalStore
from tests.fakes import FIXED_NOW, FakeProvider
from tests.strategy_fixtures import BrokenStrategy, LevelStrategy, SloppyStrategy

APP_DIR = Path(__file__).resolve().parents[2] / "app"


def weekdays(start: date, end: date) -> dict[date, float]:
    out, day = {}, start
    while day <= end:
        if day.weekday() < 5:
            out[day] = 100.0
        day += timedelta(days=1)
    return out


@pytest.fixture
def provider() -> FakeProvider:
    p = FakeProvider()
    for t in ("LOW", "MID", "HIGH", "NEWCO", "FAIL"):
        p.set_closes(t, weekdays(date(2026, 10, 1), FIXED_NOW.date()))
    p.set_closes("NEWCO", weekdays(date(2026, 11, 12), FIXED_NOW.date()))  # only 2 completed sessions
    p.history_failures["FAIL"] = ProviderError("history down")
    for ticker, price in {"LOW": 90.0, "MID": 105.0, "HIGH": 120.0, "NEWCO": 95.0, "FAIL": 95.0}.items():
        p.set_quote(ticker, price, previous_close=price - 1)
    return p


@pytest.fixture
def market(store: ParquetStore, provider: FakeProvider) -> MarketDataService:
    svc = MarketDataService(provider, store, derived_registry, archive_threshold=1000, clock=lambda: FIXED_NOW)
    svc.refresh(["LOW", "MID", "HIGH", "NEWCO", "FAIL"])
    return svc


@pytest.fixture
def registry() -> StrategyRegistry:
    reg = StrategyRegistry()
    for cls in (LevelStrategy, BrokenStrategy, SloppyStrategy):
        reg.register(cls)
    return reg


@pytest.fixture
def clock() -> dict:
    return {"now": FIXED_NOW}


@pytest.fixture
def engine(registry: StrategyRegistry, market: MarketDataService, store: ParquetStore, clock: dict) -> StrategyEngine:
    return StrategyEngine(registry, market, SignalStore(store), clock=lambda: clock["now"])


# -- registry & schemas ----------------------------------------------------------------------------


def test_list_and_schema(engine: StrategyEngine) -> None:
    assert [s.name for s in engine.list()] == ["broken_test", "level_test", "sloppy_test"]
    schema = engine.schema("level_test")
    assert [p.name for p in schema.parameters] == ["lookback", "level", "band", "mode", "enabled"]
    assert [o.name for o in schema.outputs] == ["average", "distance"]
    data = json.loads(schema.model_dump_json())  # JSON-serialisable for the frontend form
    assert data["parameters"][0] == {
        "name": "lookback", "type": "integer", "title": "Lookback", "description": "Sessions of history required",
        "default": 3, "minimum": 1.0, "maximum": 50.0, "choices": None,
    }
    with pytest.raises(NotFoundError):
        engine.schema("nope")


def test_registry_rejects_bad_definitions() -> None:
    reg = StrategyRegistry()

    class BadDefault(LevelStrategy):
        name = "bad_default"
        parameters = (StrategyParameter(name="n", type=ParameterType.INTEGER, title="N", default=0, minimum=1),)

    class DuplicateParams(LevelStrategy):
        name = "dup_params"
        parameters = LevelStrategy.parameters[:1] * 2

    class BadMetric(LevelStrategy):
        name = "bad_metric"
        primary_metric = "nope"

    class BadName(LevelStrategy):
        name = "has space"

    for cls, message in [(BadDefault, "default for n"), (DuplicateParams, "duplicate parameter"),
                         (BadMetric, "primary_metric"), (BadName, "identifier")]:
        with pytest.raises(ValueError, match=message):
            reg.register(cls)
    reg.register(LevelStrategy)

    class Clash(LevelStrategy):
        pass

    with pytest.raises(ValueError, match="already registered"):
        reg.register(Clash)


def test_discovery_imports_only_strategy_subpackages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pkg = tmp_path / "trusted_strats"
    (pkg / "alpha").mkdir(parents=True)
    (pkg / "no_strategy").mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "alpha" / "__init__.py").write_text("")
    (pkg / "no_strategy" / "__init__.py").write_text("")
    (pkg / "helpers.py").write_text("raise RuntimeError('must not be imported')")
    (pkg / "alpha" / "strategy.py").write_text(
        "from app.strategies.registry import register_strategy\n"
        "from tests.strategy_fixtures import LevelStrategy\n"
        "@register_strategy\n"
        "class Alpha(LevelStrategy):\n    name = 'alpha_discovered'\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        assert discover_strategies("trusted_strats") == ["alpha"]
        assert "alpha_discovered" in strategy_registry.names()
    finally:
        strategy_registry.unregister("alpha_discovered")
        for mod in [m for m in sys.modules if m.startswith("trusted_strats")]:
            del sys.modules[mod]


def test_app_discovery_runs() -> None:
    discover_strategies()  # app.strategies: must not fail; strategies register themselves


# -- configuration validation ------------------------------------------------------------------------


def test_defaults_applied() -> None:
    assert LevelStrategy().validate_config({}) == {
        "lookback": 3, "level": 100.0, "band": 10.0, "mode": "normal", "enabled": True}


def test_integral_float_accepted_for_integer() -> None:
    assert LevelStrategy().validate_config({"lookback": 20.0})["lookback"] == 20


@pytest.mark.parametrize(
    ("config", "field", "message"),
    [
        ({"lookback": 2.5}, "lookback", "must be an integer"),
        ({"lookback": "20"}, "lookback", "must be a number"),
        ({"lookback": True}, "lookback", "must be a number"),
        ({"lookback": 0}, "lookback", "at least 1"),
        ({"lookback": 51}, "lookback", "at most 50"),
        ({"level": float("nan")}, "level", "finite"),
        ({"band": -1}, "band", "at least 0"),
        ({"mode": "sideways"}, "mode", "must be one of normal, inverted"),
        ({"mode": 1}, "mode", "must be a string"),
        ({"enabled": "yes"}, "enabled", "true or false"),
        ({"unknown": 1}, "unknown", "unknown parameter"),
        ({"mode": "inverted", "band": 0}, "band", "positive in inverted mode"),
    ],
)
def test_invalid_config(config: dict, field: str, message: str) -> None:
    with pytest.raises(ConfigValidationError) as info:
        LevelStrategy().validate_config(config)
    assert message in info.value.errors[field]


def test_engine_reports_config_errors(engine: StrategyEngine) -> None:
    with pytest.raises(StrategyConfigError) as info:
        engine.run("level_test", ["LOW"], {"lookback": 0, "mode": "x"})
    assert set(info.value.details) == {"lookback", "mode"}


# -- execution --------------------------------------------------------------------------------------------


def test_run_produces_signals_and_metrics(engine: StrategyEngine) -> None:
    result = engine.run("level_test", ["LOW", "MID", "HIGH"], {"lookback": 5})
    by = {r.ticker: r for r in result.results}
    assert result.config["lookback"] == 5 and result.calculated_at == FIXED_NOW
    assert (by["LOW"].signal, by["MID"].signal, by["HIGH"].signal) == (Signal.BUY, None, Signal.SELL)
    assert by["LOW"].status is CalculationStatus.OK
    assert by["LOW"].metrics == {"average": 100.0, "distance": -10.0}
    assert by["LOW"].current_price == 90.0 and by["LOW"].daily_change == 1.0 and by["LOW"].currency == "USD"


def test_history_excludes_current_session(engine: StrategyEngine, provider: FakeProvider) -> None:
    engine.run("level_test", ["LOW"], {"lookback": 5})
    # Quote session is Monday 2026-11-16: history is requested up to the day before.
    assert all(end < FIXED_NOW.date() for _, _, end in provider.history_calls)


def test_statuses(engine: StrategyEngine, provider: FakeProvider) -> None:
    result = engine.run("level_test", ["NEWCO", "FAIL", "NOQUOTE"], {"lookback": 5})
    by = {r.ticker: r for r in result.results}
    assert by["NEWCO"].status is CalculationStatus.INSUFFICIENT_DATA and by["NEWCO"].signal is None
    assert by["FAIL"].status is CalculationStatus.DATA_ERROR and by["FAIL"].message == "history down"
    assert by["NOQUOTE"].status is CalculationStatus.NO_PRICE and by["NOQUOTE"].current_price is None
    assert "NOQUOTE" not in [t for t, _, _ in provider.history_calls]  # no pointless fetch


def test_tickers_deduplicated_and_order_kept(engine: StrategyEngine) -> None:
    result = engine.run("level_test", ["HIGH", "LOW", "HIGH"], {})
    assert [r.ticker for r in result.results] == ["HIGH", "LOW"]


def test_output_is_normalised(engine: StrategyEngine) -> None:
    result = engine.run("sloppy_test", ["LOW", "MID"], {})
    assert [r.ticker for r in result.results] == ["LOW", "MID"]  # unknown ticker dropped
    assert result.results[0].signal is None  # signal discarded for a non-OK status
    assert result.results[1].status is CalculationStatus.DATA_ERROR


def test_strategy_crash_is_reported(engine: StrategyEngine) -> None:
    with pytest.raises(StrategyExecutionError, match="boom"):
        engine.run("broken_test", ["LOW"], {})


def test_unknown_strategy(engine: StrategyEngine) -> None:
    with pytest.raises(NotFoundError):
        engine.run("nope", ["LOW"], {})


def test_empty_ticker_list(engine: StrategyEngine) -> None:
    assert engine.run("level_test", [], {}).results == []


# -- signal history ------------------------------------------------------------------------------------------


def test_signal_transitions_recorded_once(engine: StrategyEngine, clock: dict, market: MarketDataService,
                                          provider: FakeProvider) -> None:
    # First sighting: a baseline, not a change. The signal exists but is not "new",
    # and when it began is unknown.
    first = {r.ticker: r for r in engine.run("level_test", ["LOW", "MID"], {}, instance_id="pane-1").results}
    assert first["LOW"].signal is Signal.BUY and first["LOW"].is_new_signal is False
    assert first["LOW"].signal_changed_at is None and first["LOW"].previous_signal is None
    assert first["MID"].signal is None and first["MID"].is_new_signal is False
    assert engine.signals.history(instance_id="pane-1").total == 0  # baselines are not listed

    clock["now"] = FIXED_NOW + timedelta(minutes=5)
    second = {r.ticker: r for r in engine.run("level_test", ["LOW", "MID"], {}, instance_id="pane-1").results}
    assert second["LOW"].signal is Signal.BUY and second["LOW"].is_new_signal is False
    assert second["LOW"].signal_changed_at is None

    # Price moves back between the thresholds: BUY -> NONE is a real change.
    clock["now"] = FIXED_NOW + timedelta(minutes=10)
    provider.set_quote("LOW", 104.0, previous_close=90.0, timestamp=clock["now"])
    market.refresh(["LOW"])
    third = {r.ticker: r for r in engine.run("level_test", ["LOW"], {}, instance_id="pane-1").results}
    assert third["LOW"].signal is None and third["LOW"].is_new_signal is True
    assert third["LOW"].previous_signal is Signal.BUY and third["LOW"].signal_changed_at == clock["now"]

    # ... and back to BUY.
    clock["now"] = FIXED_NOW + timedelta(minutes=15)
    provider.set_quote("LOW", 90.0, previous_close=104.0, timestamp=clock["now"])
    market.refresh(["LOW"])
    fourth = {r.ticker: r for r in engine.run("level_test", ["LOW"], {}, instance_id="pane-1").results}
    assert fourth["LOW"].signal is Signal.BUY and fourth["LOW"].is_new_signal is True

    clock["now"] = FIXED_NOW + timedelta(minutes=20)
    fifth = {r.ticker: r for r in engine.run("level_test", ["LOW"], {}, instance_id="pane-1").results}
    assert fifth["LOW"].is_new_signal is False and fifth["LOW"].signal_changed_at == FIXED_NOW + timedelta(minutes=15)

    events = engine.signals.history(instance_id="pane-1").items
    assert [(e.previous_signal, e.new_signal) for e in events] == [(None, Signal.BUY), (Signal.BUY, None)]
    assert events[0].metric_name == "distance" and events[0].metric_value == -10.0
    assert events[0].current_price == 90.0 and events[0].strategy == "level_test"


def test_instances_are_independent(engine: StrategyEngine, clock: dict, market: MarketDataService,
                                   provider: FakeProvider) -> None:
    engine.run("level_test", ["LOW"], {}, instance_id="a")
    engine.run("level_test", ["LOW"], {}, instance_id="b")
    clock["now"] = FIXED_NOW + timedelta(minutes=5)
    provider.set_quote("LOW", 104.0, previous_close=90.0, timestamp=clock["now"])
    market.refresh(["LOW"])
    assert engine.run("level_test", ["LOW"], {}, instance_id="a").results[0].is_new_signal is True
    assert engine.run("level_test", ["LOW"], {}, instance_id="a").results[0].is_new_signal is False
    assert engine.run("level_test", ["LOW"], {}, instance_id="b").results[0].is_new_signal is True  # b's own state
    assert engine.run("level_test", ["LOW"], {}, instance_id="c").results[0].is_new_signal is False  # c: first sighting
    assert engine.signals.history().total == 2


def test_no_history_without_instance_id(engine: StrategyEngine) -> None:
    result = engine.run("level_test", ["LOW"], {}).results[0]
    assert result.signal is Signal.BUY and result.is_new_signal is False
    assert engine.signals.history().total == 0


def test_failed_calculation_keeps_previous_state(engine: StrategyEngine, provider: FakeProvider,
                                                 clock: dict, store: ParquetStore) -> None:
    engine.run("level_test", ["LOW"], {"lookback": 5}, instance_id="p")
    clock["now"] = FIXED_NOW + timedelta(minutes=1)
    # More history needed than exists: insufficient data must not record BUY -> NONE.
    insufficient = engine.run("level_test", ["LOW"], {"lookback": 50}, instance_id="p").results[0]
    assert insufficient.status is CalculationStatus.INSUFFICIENT_DATA
    assert engine.signals.current_states("p", ["LOW"])["LOW"].signal is Signal.BUY  # baseline kept
    again = engine.run("level_test", ["LOW"], {"lookback": 5}, instance_id="p").results[0]
    assert again.signal is Signal.BUY and again.is_new_signal is False


def test_history_filters_and_pagination(engine: StrategyEngine, clock: dict) -> None:
    for i, instance in enumerate(["a", "b", "c"]):
        clock["now"] = FIXED_NOW + timedelta(minutes=i)
        engine.run("level_test", ["LOW", "HIGH"], {"level": 85, "band": 50}, instance_id=instance)  # baseline: no signals
        engine.run("level_test", ["LOW", "HIGH"], {}, instance_id=instance)  # both change
    assert engine.signals.history().total == 6
    page = engine.signals.history(limit=2, offset=1)
    assert page.total == 6 and len(page.items) == 2 and page.offset == 1
    assert [e.instance_id for e in engine.signals.history(ticker="HIGH").items] == ["c", "b", "a"]
    assert engine.signals.history(strategy="other").total == 0


# -- architecture boundaries ------------------------------------------------------------------------------------


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_strategies_are_independent_of_portfolios_positions_and_storage() -> None:
    forbidden = ("app.portfolio", "app.positions", "app.api", "fastapi", "yfinance", "pyarrow", "duckdb",
                 "app.persistence")
    strategy_files = [APP_DIR / "strategies" / "base.py", APP_DIR / "strategies" / "models.py",
                      *(APP_DIR / "strategies").glob("*/*.py")]
    for path in strategy_files:
        bad = [m for m in _imports(path) if m.startswith(forbidden)]
        assert not bad, f"{path.name} imports {bad}"
    engine_files = [APP_DIR / "strategies" / n for n in ("engine.py", "registry.py", "signals.py")]
    for path in engine_files:
        bad = [m for m in _imports(path) if m.startswith(("app.portfolio", "app.positions", "yfinance"))]
        assert not bad, f"{path.name} imports {bad}"
