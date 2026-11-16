"""Strategy registry and discovery.

Each strategy lives in its own sub-package of ``app.strategies`` with a
``strategy.py`` module that registers its class with ``@register_strategy``.
Discovery only imports sub-packages of this trusted application package —
never arbitrary directories or user-supplied module names. Adding a strategy
means adding a folder; no API route changes.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from pathlib import Path

from app.strategies.base import BaseStrategy, coerce_parameter
from app.strategies.models import StrategySchema

logger = logging.getLogger(__name__)

STRATEGIES_PACKAGE = "app.strategies"


class StrategyRegistry:
    def __init__(self) -> None:
        self._classes: dict[str, type[BaseStrategy]] = {}

    def register(self, cls: type[BaseStrategy]) -> type[BaseStrategy]:
        name = getattr(cls, "name", None)
        if not name or not name.isidentifier():
            raise ValueError(f"Strategy {cls.__name__} needs an identifier-like 'name'")
        if name in self._classes and self._classes[name] is not cls:
            raise ValueError(f"Strategy {name!r} is already registered")
        _check_definition(cls)
        self._classes[name] = cls
        return cls

    def unregister(self, name: str) -> None:
        self._classes.pop(name, None)

    def names(self) -> list[str]:
        return sorted(self._classes)

    def get(self, name: str) -> BaseStrategy | None:
        cls = self._classes.get(name)
        return cls() if cls else None

    def implementation(self, name: str) -> type[BaseStrategy] | None:
        return self._classes.get(name)

    def schemas(self) -> list[StrategySchema]:
        return [self._classes[n]().get_config_schema() for n in self.names()]


def _check_definition(cls: type[BaseStrategy]) -> None:
    names = [p.name for p in cls.parameters]
    if len(names) != len(set(names)):
        raise ValueError(f"Strategy {cls.name}: duplicate parameter names")
    for param in cls.parameters:
        try:
            coerce_parameter(param, param.default)
        except ValueError as exc:
            raise ValueError(f"Strategy {cls.name}: default for {param.name} {exc}") from exc
    outputs = [o.name for o in cls.outputs]
    if cls.primary_metric is not None and cls.primary_metric not in outputs:
        raise ValueError(f"Strategy {cls.name}: primary_metric must be one of its outputs")


strategy_registry = StrategyRegistry()


def register_strategy(cls: type[BaseStrategy]) -> type[BaseStrategy]:
    """Class decorator registering a strategy in the application registry."""
    return strategy_registry.register(cls)


def discover_strategies(package: str = STRATEGIES_PACKAGE) -> list[str]:
    """Import ``<package>.<sub>.strategy`` for every sub-package that has one."""
    module = importlib.import_module(package)
    root = Path(module.__file__).parent  # type: ignore[arg-type]
    loaded = []
    for info in pkgutil.iter_modules([str(root)]):
        if not info.ispkg or not (root / info.name / "strategy.py").is_file():
            continue
        importlib.import_module(f"{package}.{info.name}.strategy")
        loaded.append(info.name)
    logger.info("strategies discovered", extra={"packages": loaded, "strategies": strategy_registry.names()})
    return loaded
