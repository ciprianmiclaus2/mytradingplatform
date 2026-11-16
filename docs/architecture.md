# Architecture

My Trading Platform runs locally as a modular monolith: one FastAPI backend process and one React frontend. See the [README](../README.md) for the overview. This document records the design decisions behind each layer as it's built.

## Backend layers

```text
api/            HTTP routes: request/response models only, no business logic
<domain>/       services: portfolio, positions, market_data, strategies
persistence/    the only code that reads or writes files in DATA_DIR
schemas/        shared API models and the error envelope
```

## Persistence

| Module | Responsibility |
|---|---|
| `persistence/data_dirs.py` | Creates the directory layout and checks the data schema version |
| `persistence/locking.py` | `DataLock`: the single re-entrant write lock |
| `persistence/schemas.py` | `DatasetSchema` declarations, the dataset registry, and validation |
| `persistence/parquet.py` | `ParquetStore`: validated, locked, atomic Parquet reads and writes |
| `persistence/duckdb.py` | Read-only analytical SQL over Parquet files |
| `persistence/derived.py` | Rebuildable derived data (materialised views) and staleness detection |
| `persistence/backup.py` | `BackupManager`: create, prune, verify and restore backups |
| `persistence/jsonfile.py` | Small JSON status files, written atomically under the lock |
| `persistence/__init__.py` | `open_persistence()`: the startup sequence |

### Datasets and schemas

Every persisted dataset is declared once as a `DatasetSchema`, which holds:

- its name and version;
- its Arrow schema, including whether each column may be null;
- optional unique key columns;
- for single-file datasets, its path.

The dataset name and version are written into each Parquet file's metadata.

- **On write:** columns must match exactly by name and type, with no implicit casting. Columns that may not be null must have no nulls, and key values must be unique.
- **On read:** a file whose dataset name, version or columns differ raises `IncompatibleSchemaError`, and an unreadable file raises `CorruptFileError`. In both cases the file is never overwritten.

Money and quantities are stored as Arrow `decimal128` values, so they stay exact. The persistence layer works with Arrow tables. Services convert them to Python `Decimal` values, because pandas would turn decimal columns into generic object columns.

### Writes

The write protocol follows §14.1 of the plan:

1. Acquire the lock.
2. Validate the data.
3. Write a temporary file `.tmp-*` in the same directory.
4. Flush and `fsync` it.
5. `os.replace` it over the original and `fsync` the directory.
6. Release the lock.

If any step fails, the original file is left untouched and the temporary file is removed. Any temporary files left by a crash are deleted on the next startup.

### Locking

There is one data-wide write lock, combining:

- a re-entrant thread lock, which serialises writers inside the backend process;
- an OS file lock at `metadata/.write.lock`, which serialises the backend with the maintenance scripts.

Because there is only one lock, an update that touches several files is consistent whenever the caller holds the lock across all of them. Reads take no lock: atomic replacement means a reader always sees a complete file. If the lock can't be acquired in time, a `LockTimeoutError` is raised, which the API reports as HTTP 503.

### Derived data

Some data is computed entirely from other files, for example `history.parquet` from the daily close-price files. Each such dataset is registered as a `DerivedDataset` with:

- its source files or globs;
- a function that builds it from those sources.

Whenever derived data is written, a SHA-256 fingerprint of its sources is stored in its metadata under `x_source_fingerprint`. If a crash happens after a source was written but before the derived file was, the fingerprints no longer match. The next startup, or `scripts/rebuild_derived.py`, then rebuilds it.

### Backups

- **Contents:** each backup is `backups/<UTC timestamp>Z-<reason>/` with a `manifest.json` of SHA-256 checksums. It covers the `portfolios`, `positions`, `strategies` and `metadata` folders. Market data is excluded because it can be downloaded again.
- **Creation:** backups are assembled in a temporary staging folder and then renamed into place, so a half-written backup never looks complete. Only the newest `BACKUP_RETENTION_COUNT` backups are kept.
- **Restoring:** the checksums are verified first, the current state is backed up, and then each file is replaced atomically. A backup made with a different data schema version is refused.
- **When backups are taken:** on startup, but skipped if nothing changed since the last backup. Services will also take one before destructive operations.

### Startup sequence

`open_persistence()` runs these steps in order. Any incompatibility stops startup with a clear error.

1. Create the directories and check the schema version.
2. Remove leftover temporary files.
3. Validate every registered dataset file.
4. Rebuild stale derived data.
5. Back up the now-consistent state.

### Analytical queries

`persistence.duckdb.query(sql, sources, params)` opens a short-lived in-memory DuckDB connection, so no database file is ever created. It exposes each `ParquetSource` (a file or glob) as a SQL view, runs the query with bound parameters, and returns an Arrow table. A source with no files yet appears as an empty view with its declared schema.

## Market data

```text
API (api/market_data.py)
   │
MarketDataService (market_data/service.py)   cache-first, validation, refresh status
   │                         │
   │                 caches (market_data/cache.py) ──► ParquetStore / DuckDB
   ▼
BaseMarketDataProvider (market_data/base.py)
   └── YFinanceProvider (market_data/providers/yfinance_provider.py)
```

- **Isolation:** only the provider module imports `yfinance`. Everything else uses the models in `market_data/models.py`.
- **Error contract:** a provider must keep three outcomes separate:

  | Outcome | Provider returns |
  |---|---|
  | Data retrieved | A populated result |
  | No data | `HistoricalPrices(bars=[])` or `NoPriceDataError` |
  | Request failed | `ProviderError`, never an empty result |

  For yfinance, this works by setting `yf.config.debug.hide_exceptions = False`. Then `YFTickerMissingError` (and its subclasses) and HTTP 404 on quotes mean no data, and every other exception means failure.
- **History:**
  - The service works out which date ranges have no coverage, fetches the span they cover in one request, validates every bar (any non-positive or non-finite price rejects the whole response), and writes close files and then coverage.
  - It then rebuilds the `price_history` view.
  - The current session is excluded: only dates before today's UTC date count as complete. This is conservative, because every major exchange's session for UTC date D−1 has closed by 00:00 UTC on D.
- **Current prices:**
  - `refresh()` de-duplicates tickers and asks the provider once per ticker. yfinance runs up to 4 requests in parallel, all bounded by `MARKET_DATA_TIMEOUT`.
  - It validates each quote, appends new observations, and records per-ticker state.
  - A failed ticker keeps its last valid price, reported as `stale`.
- **Latest-price view:** a DuckDB `QUALIFY row_number()` query over the active current-price file.

### Adding a market data provider

1. Subclass `BaseMarketDataProvider` in `market_data/providers/<name>_provider.py`. Implement `search_ticker`, `get_historical_prices` and `get_current_price`, and optionally a faster `get_current_prices`. Return only application models, and follow the error contract above.
2. Register a factory for it in `market_data/providers/registry.py`.
3. Set `MARKET_DATA_PROVIDER=<name>`.

Historical coverage is recorded per provider, so switching provider fetches fresh history. Nothing else in the application changes.

## Portfolios

```text
API (api/portfolios.py) ─► PortfolioService (portfolio/service.py) ─► PortfolioRepository ─► ParquetStore
                                   │
                                   └─► MarketDataService.ensure_price()   ticker check on add
```

- **Read-modify-write:** every change goes through `PortfolioRepository.modify()`, which holds the data lock. A rule violation raised inside the change aborts it and leaves the file untouched.
- **Ticker checks happen before the lock.** Checking a new ticker may call the provider, so it runs before the lock is taken. The duplicate check is repeated under the lock.
- **Hooks for positions:** `PositionService` registers these when it is created.
  - `PortfolioService.position_tickers(portfolio_id)` supplies the tickers of open positions.
  - `on_deleted` hooks run under the lock when a portfolio is deleted, to remove its positions.
  - `prune_favourites()` drops favourites that are no longer tickers, e.g. after a position closes.
- **Refresh support:** `all_tickers()` returns the unique tickers across all portfolios, for the market data refresh (Phase 10).

## Positions

```text
API (api/positions.py) ─► PositionService (positions/service.py) ─► PositionRepository ─► ParquetStore
                                  │            │
                                  │            └─► calculations.py   valuation, P&L, per-currency totals (pure functions)
                                  ├─► PortfolioService               portfolio type, ticker derivation, favourites
                                  └─► MarketDataService              ensure_price() on create; latest prices for valuation
```

- **No ledger:** positions are edited in place.
- **Storage:** quantities and prices are stored as `decimal128(20,8)`.
- **Calculations:**
  - Done with `Decimal`. Market prices (stored as float64) are converted using their shortest string form, so `0.1` becomes exactly `Decimal("0.1")`.
  - Results are rounded to 8 decimal places and returned as JSON numbers.
  - A price in a different currency from the position is never used.
- **Multi-step changes hold the lock throughout:** closing or deleting a position, together with pruning favourites (and the backup before a delete), happens under one data lock hold.

## Strategy engine

```text
API (api/strategies.py) ─► StrategyEngine (strategies/engine.py)
                              ├─► StrategyRegistry (strategies/registry.py)   discovery + lookup
                              ├─► MarketDataService                           cached quotes + history before the quote's session
                              ├─► BaseStrategy.calculate()                    pure: normalised data in, StrategyOutput out
                              └─► SignalStore (strategies/signals.py)         transitions → strategies/signals.parquet
```

Running a strategy takes these steps:

1. Resolve the strategy.
2. Validate the configuration against the schema, then apply the strategy's own cross-parameter rules.
3. Remove duplicate tickers.
4. Fetch the cached latest quotes and `required_sessions(config)` completed closes strictly before each quote's trading date. Tickers with no quote get no history fetch.
5. Run `calculate`.
6. Normalise the results:
   - one row per requested ticker, in request order;
   - a missing row becomes `DATA_ERROR`;
   - a signal is only kept when the status is `OK`;
   - price fields come from the quote.
7. If there's an `instance_id`, record the signal transitions under the data lock.

Signal state rules:

- Only `OK` results change state.
- The first `OK` calculation records an existing BUY or SELL straight away.
- Repeated identical states are never recorded.

**Boundaries.** A test checks these by parsing imports:

- Strategy implementations (`strategies/base.py`, `models.py`, `<name>/*.py`) never import portfolios, positions, the API, FastAPI, yfinance, pyarrow, DuckDB or the persistence layer.
- The engine never imports portfolios or positions. It only receives ticker symbols, and the caller decides where they come from.

### Adding a strategy

1. Create the package `app/strategies/<name>/`, containing `__init__.py` and `strategy.py`.
2. In `strategy.py`, subclass `BaseStrategy` and decorate it with `@register_strategy`. Define:
   - `name`, `title` and `description`;
   - `parameters` (`StrategyParameter`s: type, default, min/max, choices, description);
   - `outputs` (`OutputColumn`s for the result grid);
   - optionally `primary_metric` (recorded with signal transitions);
   - `required_sessions(config)`;
   - `calculate(tickers, market_data, config)`, returning one `StrategyOutput` per ticker. Report problems through `status` rather than raising.
   - Optionally override `check_config(config)` for cross-parameter rules.
3. That's all. `discover_strategies()` imports `app.strategies.<pkg>.strategy` at startup. Only sub-packages of this trusted application package are imported. No new API route or frontend form is needed.

### Mean Reversion

`strategies/mean_reversion/` holds `config.py` (parameters and output columns) and `strategy.py` (the calculation).

- **Inputs:** the regular `close` of the last `lookback_days` completed sessions before the quote's session. This is split-adjusted by the provider and not dividend-adjusted.
- **Calculation:**
  - `statistics.fmean` gives the mean, and `statistics.pstdev` the population standard deviation. `pstdev` is computed exactly, so constant prices give exactly 0.
  - Z = (price − mean) / std.
  - Both thresholds are inclusive.
- **Validation:** `check_config` requires `buy_threshold < sell_threshold`.
- **No signal:** insufficient history, a zero standard deviation, a currency mismatch, a missing quote or a history error are each reported as a status, never as a signal.

## Frontend dashboard

```text
App
 ├─ Header        Menu (Reset layout) · Add pane menu · BackendStatus
 ├─ warning banners (saved layout invalid, layout cannot be saved)
 └─ Dashboard     React Grid Layout v2 (useContainerWidth + ReactGridLayout)
     └─ PaneFrame × n   title bar (drag handle) · minimise · remove (ConfirmDialog) · pane body
```

| File | Responsibility |
|---|---|
| `dashboard/types.ts` | `Pane {id, type, title, config}`, `PaneLayout {i, x, y, w, h}`, `DashboardState`, the stored document |
| `dashboard/reducer.ts` | Pure state changes: add, remove, layout change, minimise/restore, update config, reset |
| `dashboard/storage.ts` | Loads and saves to localStorage, validates saved layouts, and tracks whether saving worked |
| `dashboard/useDashboard.ts` | Reducer plus automatic saving after every change |
| `dashboard/grid.ts` | Grid geometry: 12 columns, 32px rows, 12px margins, minimised height of 1 row |
| `panes/registry.ts` | Pane types: title, description, component, default and minimum size, default config |

### Pane types

The registry is the only place that knows the pane types. Adding a type means adding one registry entry with a component that receives `PaneProps {pane, onConfigChange}`. The menus, grid and storage are generic.

### Pane ids

Ids are `pane-<uuid>`. They also serve as the backend strategy `instance_id` (letters, digits and `-`, at most 64 characters).

### Persistence

The layout is saved under `my-trading-platform-layout` as:

```json
{"version": 1, "panes": [...], "layouts": [...], "minimised": {"<pane id>": <height to restore>}}
```

Loading validates the saved layout:

- **Fall back to the default layout, with a notice:** invalid JSON, a wrong version, or a malformed overall structure.
- **Drop just that pane, with a notice:** an unknown type, a bad id, a duplicate id, invalid config, or a missing or invalid layout.
- **Clamp:** widths are clamped to the grid.

Storage errors never crash the app. The dashboard keeps working in memory and shows a "cannot be saved" banner.

### Grid behaviour

- The grid measures the container before its first render (`measureBeforeMount`), so panes don't jump from the library's 1280px default width.
- Only the title bar starts a drag, so pane contents stay interactive.
- A minimised pane is 1 row high, can't be resized, and remembers its height for when it's restored.
