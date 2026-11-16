"""Import every module that registers persisted or derived datasets.

Called by the application and by maintenance scripts before opening the data
directory, so startup validation and rebuilds know about all datasets.
"""

from __future__ import annotations


def load_dataset_modules() -> None:
    import app.market_data.cache  # noqa: F401
    import app.portfolio.repository  # noqa: F401
