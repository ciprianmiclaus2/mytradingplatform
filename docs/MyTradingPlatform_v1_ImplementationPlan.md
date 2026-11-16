# My Trading Platform
## Version 1 – Implementation Plan for AI Coding Agent

**Status:** Approved for implementation. Revision 1.1: positions and portfolios simplified  
**Architecture:** Local single-user web application  
**Backend:** Python / FastAPI  
**Frontend:** React / TypeScript  
**Persistence:** Parquet / DuckDB  
**Market data:** yfinance

---

# Revision 1.1 (2026-11-16)

## Scope change

The platform generates and displays **signals**. It is not a trading or accounting system.

- **Portfolios are named watchlists.** Each has one of two types:
  - `watchlist`: tickers you monitor;
  - `positions`: tickers you hold, each with a quantity and an entry price, kept for display only.
- **No transaction ledger and no cash management.** Positions are edited directly. Closing a position records an exit price and date, and the row stays visible as closed history.
- **Removed:**
  - transactions;
  - cash balances, deposits and withdrawals;
  - weighted-average-cost accounting;
  - correction transactions;
  - the negative-cash and short-sale ledger rules.
- **Rewritten sections:** §1, §3, §6, §7, §8.4, §10.2–10.4, §11, §13.2–13.4, §14.2, §15, §17 (Phases 4, 5 and 11), §18, §20.3 and §21.

## Decisions taken during Phases 1–3

- **Data directory:**
  - `DATA_DIR` defaults to `~/mytradingplatform/data`.
  - A relative path is resolved against the project root.
  - `./start.sh` starts the backend and frontend together.
- **Persistence:**
  - One data-wide write lock.
  - Atomic writes of validated files.
  - Schema name and version stored in each file's metadata.
  - Derived data carries a fingerprint of its sources and is rebuilt when stale.
  - Backups on startup (skipped if nothing changed) and before destructive operations.
- **Market data:**
  - `current.parquet` has four extra columns: `previous_close`, `trading_date`, `delayed` and `fetched_at`.
  - `delayed` is `true` or unknown, never `false`.
  - Refresh status is `completed`, `partial` or `failed`.
  - A daily session counts as complete from the next UTC day.
  - Search results may have no currency.
  - Futures and options are excluded from search.
- **Strategy panes** live in browser localStorage, so the frontend sends their tickers in the refresh request (§11).

---

# 1. Project objectives

Build a locally hosted trading dashboard that allows a user to:

1. Monitor named watchlists (portfolios) of ticker symbols.
2. Record held positions (quantity, entry price) and closed positions (exit price, exit date) for display.
3. Monitor position valuation and profit/loss per currency.
4. Execute configurable trading strategies against selected ticker symbols.
5. Visualise strategy calculations and trading signals.
6. Arrange multiple dashboard panes in a configurable layout.
7. Refresh market data manually and update all dashboard panes.
8. Persist application data locally using Parquet files.

The architecture must support future enhancements without requiring fundamental changes, particularly:

- Additional market data providers.
- Additional trading strategies.
- Multiple portfolios.
- User authentication.
- Persistent layouts stored on the backend.
- Automated market data refresh.
- Additional financial instruments.
- Potential future broker integration.

The platform is a signal-generation and monitoring tool. Positions are informational records entered by the user, not an accounting ledger.

## 1.1 Out of scope

The following are explicitly excluded from version 1:

- Real trading or broker integration.
- Transaction ledgers, cash balances and cash management.
- Accounting for positions: tax lots, fees, dividends, corporate actions.
- Automatic execution of buy/sell orders.
- Short selling.
- Options, futures and other derivatives.
- Intraday historical price analysis.
- Multi-user authentication.
- Cloud hosting.
- Currency conversion.
- Automated background market data refresh.
- Backtesting and strategy performance optimisation.
- Notifications and alerts.

Do not implement these features unless specifically requested.

---

# 2. Technology stack

Use the following technologies.

| Layer | Technology |
|---|---|
| Backend language | Python 3 |
| Backend framework | FastAPI |
| API validation | Pydantic |
| Market data | yfinance |
| Data manipulation | Pandas |
| Analytical queries | DuckDB |
| File storage | Parquet |
| Frontend | React |
| Frontend language | TypeScript |
| Frontend build tool | Vite |
| Dashboard layout | React Grid Layout |
| Styling | Tailwind CSS |
| HTTP client | Axios or Fetch |
| Frontend layout persistence | localStorage |
| Backend testing | Pytest |
| Frontend testing | Vitest |
| API testing | FastAPI TestClient |

Use compatible, stable versions of dependencies. Pin dependencies in the appropriate dependency files.

The agent should verify current library APIs and compatibility before implementation rather than relying on outdated examples.

---

# 3. Project structure

Create the following project structure:

```text
my-trading-platform/
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   │
│   │   ├── api/
│   │   │   ├── market_data.py
│   │   │   ├── portfolios.py
│   │   │   ├── positions.py
│   │   │   └── strategies.py
│   │   │
│   │   ├── market_data/
│   │   │   ├── base.py
│   │   │   ├── models.py
│   │   │   ├── service.py
│   │   │   ├── cache.py
│   │   │   └── providers/
│   │   │       ├── yfinance_provider.py
│   │   │       └── registry.py
│   │   │
│   │   ├── portfolio/
│   │   │   ├── models.py
│   │   │   └── service.py
│   │   │
│   │   ├── positions/
│   │   │   ├── models.py
│   │   │   └── service.py
│   │   │
│   │   ├── strategies/
│   │   │   ├── base.py
│   │   │   ├── registry.py
│   │   │   ├── engine.py
│   │   │   └── mean_reversion/
│   │   │       ├── strategy.py
│   │   │       └── config.py
│   │   │
│   │   ├── persistence/
│   │   │   ├── parquet.py
│   │   │   ├── duckdb.py
│   │   │   ├── locking.py
│   │   │   └── backup.py
│   │   │
│   │   └── schemas/
│   │       ├── common.py
│   │       └── errors.py
│   │
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── fixtures/
│   │
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── panes/
│   │   ├── dashboard/
│   │   ├── hooks/
│   │   ├── layouts/
│   │   ├── types/
│   │   ├── utils/
│   │   ├── App.tsx
│   │   └── main.tsx
│   │
│   ├── package.json
│   └── vite.config.ts
│
├── data/
│   ├── market_data/
│   │   ├── close_prices/
│   │   ├── current/
│   │   └── history/
│   │
│   ├── portfolios/
│   ├── positions/
│   ├── strategies/
│   ├── backups/
│   └── metadata/
│
├── scripts/
│   ├── rebuild_history.py
│   └── backup_data.py
│
├── docs/
│   ├── architecture.md
│   ├── api.md
│   └── data_model.md
│
├── README.md
└── .gitignore
```

The data directory must be configurable through an environment variable.

Default:

```text
~/mytradingplatform/data
```

A relative path is resolved against the project root.

The backend must create the required directory structure automatically on startup.

Do not hardcode absolute filesystem paths.

---

# 4. Backend architecture

The backend must be modular, with a clear separation of responsibilities.

## 4.1 Architectural principles

1. API routes must not contain business logic.
2. Business logic must reside in service classes or modules.
3. Strategies must not directly access Parquet files.
4. Strategies must not directly call yfinance.
5. Frontend components must not calculate financial metrics.
6. All persistence must go through the persistence layer.
7. Market data providers must implement a common interface.
8. All API request and response models must use Pydantic.
9. All persisted entities must have stable identifiers.
10. Financial calculations must use decimal arithmetic where appropriate.

The application should initially run as a modular monolith.

Do not introduce microservices or message queues.

---

# 5. Market data implementation

## 5.1 Provider abstraction

Implement a common market data provider interface.

Required methods:

```python
class BaseMarketDataProvider:

    def search_ticker(self, query: str):
        ...

    def get_historical_prices(
        self,
        ticker: str,
        start_date,
        end_date
    ):
        ...

    def get_current_price(self, ticker: str):
        ...

    def get_current_prices(self, tickers: list[str]):
        ...
```

The yfinance implementation must implement this interface.

Provider-specific response structures must never leak into the rest of the application.

## 5.2 Market data service

Implement a MarketDataService that sits between the application and providers.

Responsibilities:

- Select the configured provider.
- Retrieve data from the cache where available.
- Retrieve missing data from the provider.
- Normalise provider responses.
- Validate returned prices.
- Store retrieved data in Parquet.
- Return consistent application-level models.

The service should also expose the last successful refresh timestamp.

## 5.3 Historical price storage

Store daily close prices in files organised by trading date.

Example:

```text
data/market_data/close_prices/
    20261113.parquet
    20261116.parquet
```

Each file contains multiple tickers.

Required columns:

| Column | Type |
|---|---|
| ticker | string |
| trading_date | date |
| close | float64 |
| adjusted_close | float64 |
| currency | string |
| provider | string |
| fetched_at | timestamp |

Historical data must use the provider's regular daily close and adjusted close fields.

For statistical calculations, use `close`, not `adjusted_close`, so the historical observations remain comparable to the latest quoted price.

Split adjustments should be preserved as supplied by the provider.

Dividends are not adjusted for in the initial mean-reversion calculation.

## 5.4 Historical cache behaviour

When historical prices are requested:

1. Determine which trading dates are required.
2. Check the corresponding Parquet files.
3. Identify missing ticker/date combinations.
4. Retrieve missing data from the configured provider.
5. Merge new data with existing data.
6. Write the updated file atomically.

Do not download historical data unnecessarily.

A cache must distinguish between:
- Data successfully retrieved.
- No data available for an instrument/date.
- Provider request failed.

A provider failure must not be interpreted as a valid empty result.

## 5.5 Current price storage

Store current prices as a time series.

File:

```text
data/market_data/current/current.parquet
```

Columns:

| Column | Type |
|---|---|
| timestamp | timestamp |
| ticker | string |
| price | float64 |
| currency | string |
| provider | string |

Maintain a latest-price query/view that returns the most recent valid observation for each ticker.

Rotate the active file when it reaches a configurable size or row threshold.

Archived files should follow this naming convention:

```text
current.20261116100000.parquet
```

Use atomic file replacement and locking when updating the active file.

## 5.6 Historical materialised view

Maintain:

```text
data/market_data/history/history.parquet
```

This file contains the consolidated historical daily prices.

It is a rebuildable materialised view.

Implement a script to rebuild it from the daily close-price files.

Do not treat history.parquet as the authoritative cache.

## 5.7 Ticker search

Expose a search operation.

Example response:

```json
[
    {
        "ticker": "AAPL",
        "name": "Apple Inc.",
        "exchange": "NASDAQ",
        "currency": "USD",
        "instrument_type": "EQUITY",
        "provider": "yfinance"
    }
]
```

Normalise the response regardless of the underlying provider.

## 5.8 Market data freshness

Every current price must include:

- Price.
- Currency.
- Timestamp.
- Provider.
- Whether the price is delayed, where known.

The application must distinguish the latest available price from a genuinely live price.

Never label data as real-time unless the provider explicitly guarantees this.

---

# 6. Portfolio implementation

## 6.1 Concept

A portfolio is a named list of ticker symbols. There are two types:

| Type | Purpose |
|---|---|
| `watchlist` | Tickers to monitor |
| `positions` | Tickers held, each with a quantity and entry price (see §7), for valuation and P&L display |

Multiple portfolios of each type are supported. A ticker can belong to several portfolios.

## 6.2 Portfolio model

```text
id
name
description
type            watchlist | positions
tickers
favourites
created_at
updated_at
```

Rules:

- **Name:** required, at most 100 characters, and unique regardless of case.
- **Type:** chosen when the portfolio is created and never changed.
- **Watchlist tickers:** an ordered list maintained by the user, with no duplicates.
- **Positions tickers:** read-only. They are always the tickers of the portfolio's open positions.
- **Favourites:** must be a subset of `tickers`. Removing a ticker, or closing or deleting its position, also removes it from favourites.

## 6.3 Default portfolios

On first startup, create:

```text
Main Portfolio    (watchlist)
Main Positions    (positions)
```

At least one portfolio must always exist, so the last remaining portfolio cannot be deleted.

## 6.4 Ticker validation

When a ticker is added to a watchlist, or a position is created:

1. Normalise and validate the symbol format.
2. Use the cached latest price if there is one. Otherwise fetch a quote through `MarketDataService`.
3. If the provider says it has no data for the ticker, reject it as an invalid ticker.
4. If the provider is unavailable and there is no cached price, reject with an error saying to try again.
5. Store a fetched quote in the current-price cache, so the ticker shows a price straight away. Its currency becomes the position's currency.

Ticker search (§5.7) must be available when adding symbols.

## 6.5 Portfolio functionality

Implement:

- Create portfolio.
- List portfolios, optionally filtered by type.
- Retrieve portfolio.
- Update name and description.
- Add ticker (watchlists only).
- Remove ticker (watchlists only).
- Add favourite.
- Remove favourite.
- Delete portfolio. This also deletes its positions, needs explicit confirmation in the frontend, and takes a backup first.

## 6.6 Portfolio persistence

```text
data/portfolios/portfolios.parquet
```

One row per portfolio, with `tickers` and `favourites` stored as list columns. Use atomic updates.

---

# 7. Positions

Positions are informational. There is no transaction ledger and no cash balance. Values are entered and edited directly by the user.

## 7.1 Position model

A position belongs to a `positions` portfolio.

```text
id
portfolio_id
ticker
currency
quantity
entry_price
entry_date
status          OPEN | CLOSED
exit_price
exit_date
notes
created_at
updated_at
```

Rules:

- **Values:** `quantity`, `entry_price` and `exit_price` must be greater than 0. Short positions are not supported.
- **One open position per ticker:** each portfolio holds at most one OPEN position per ticker. To record a further purchase, the user edits the quantity and entry price.
- **Closed history:** any number of CLOSED positions per ticker may exist.
- **Currency:** set from the quote currency when the position is created. Prices are entered in the quote's units; for example, many LSE stocks are quoted in `GBp`, which is pence. There is no currency conversion.
- **Dates:** `entry_date` is optional and defaults to today. Both dates are informational only.
- **Storage:** `quantity`, `entry_price` and `exit_price` are stored as exact decimals.

## 7.2 Position operations

**Create position**

Inputs:

- ticker;
- quantity;
- entry price, defaulting to the latest available price. If no price is available, the user must supply one;
- entry date;
- notes.

Validate the ticker as in §6.4, and reject a second OPEN position for the same ticker in the same portfolio.

**Edit position**

- **Open positions:** quantity, entry price, entry date and notes can be changed in place. No change history is kept.
- **Closed positions:** exit price, exit date and notes can be changed.

**Close position**

Closing sets the status to CLOSED and records:

- the exit price, defaulting to the latest available price;
- the exit date, defaulting to today.

The whole position closes; to reduce a position, edit its quantity instead. A closed position stays visible as history, and the ticker can then be opened again as a new position.

**Delete position**

This removes an open or closed position completely, and is meant for correcting mistakes. It needs explicit confirmation in the frontend.

## 7.3 Position calculations

All calculations are done in the backend.

Open positions expose:

```text
ticker
quantity
entry_price
current_price
currency
cost_basis
market_value
unrealised_pnl
unrealised_pnl_pct
daily_change
daily_change_pct
daily_pnl
stale
```

```text
Cost basis       = quantity * entry price
Market value     = quantity * current price
Unrealised P&L   = market value - cost basis
Unrealised P&L % = (unrealised P&L / cost basis) * 100
Daily P&L        = quantity * (current price - previous close)
```

Closed positions expose:

```text
ticker
quantity
entry_price
entry_date
exit_price
exit_date
currency
realised_pnl
realised_pnl_pct
```

```text
Realised P&L   = quantity * (exit price - entry price)
Realised P&L % = ((exit price - entry price) / entry price) * 100
```

If there is no current price, every field that depends on it is null; values are never made up. The `stale` flag comes from market data.

## 7.4 Totals

For each positions portfolio, return totals **per currency**:

- **Open positions:** market value, cost basis, unrealised P&L, unrealised P&L % and daily P&L.
- **Closed positions:** realised P&L.

Never add different currencies into one total. If a currency's total leaves out positions with no current price, flag it as incomplete.

## 7.5 Persistence

```text
data/positions/positions.parquet
```

One row per position, open or closed. There is no transaction ledger and no derived snapshot. Use atomic updates. Take a backup before deleting a position.

---

# 8. Strategy engine

## 8.1 Strategy architecture

Strategies must be independently deployable modules.

Each strategy resides in its own folder.

Implement a common interface:

```python
class BaseStrategy:

    name: str
    description: str

    def get_config_schema(self):
        ...

    def calculate(
        self,
        tickers,
        market_data,
        config
    ):
        ...
```

The strategy must not know about:

- React.
- API routes.
- Parquet storage.
- yfinance.
- Dashboard layouts.

It receives normalised market data and configuration and returns structured results.

## 8.2 Strategy discovery

Implement a strategy registry.

For V1, strategies should register themselves through an explicit registry or discovery mechanism.

The registry must expose:

- Strategy name.
- Description.
- Configuration schema.
- Implementation class.

Adding a strategy must not require adding a dedicated API endpoint.

Avoid unrestricted dynamic Python imports from arbitrary directories. Only load trusted application strategy modules.

## 8.3 Strategy configuration schema

Configuration schemas must be serialisable to JSON.

Example:

```json
{
    "name": "mean_reversion",
    "description": "Mean reversion using rolling standard deviation",
    "parameters": [
        {
            "name": "lookback_days",
            "type": "integer",
            "default": 20,
            "minimum": 2
        },
        {
            "name": "buy_threshold",
            "type": "number",
            "default": -2.0
        },
        {
            "name": "sell_threshold",
            "type": "number",
            "default": 2.0
        }
    ]
}
```

The frontend must use this schema to generate configuration forms.

Validate all configuration values on the backend.

## 8.4 Strategy execution

The strategy engine should:

1. Receive a strategy identifier.
2. Resolve the strategy implementation.
3. Validate configuration.
4. Receive a list of ticker symbols.
5. Retrieve required market data through the market data service.
6. Execute the strategy.
7. Normalise the result.
8. Return results to the caller.

A strategy must be independent of the source of its tickers.

The frontend or an orchestration service resolves whether the strategy operates on:

- A portfolio's tickers. For a `positions` portfolio, these are the tickers of its open positions.
- A portfolio's favourites.
- A manually selected list of symbols.

The strategy engine only receives ticker symbols.

---

# 9. Mean reversion strategy

Implement the first strategy using the following definition.

## 9.1 Configuration

```text
lookback_days = 20
buy_threshold = -2.0
sell_threshold = 2.0
```

All three parameters must be configurable.

## 9.2 Calculation

For each ticker:

Retrieve the previous X completed trading sessions.

Exclude the current incomplete trading session.

Calculate:

```text
Mean = average of the previous X daily closes

Standard deviation = population standard deviation
                    of the previous X daily closes
```

Use regular Close prices, with split adjustments supplied by the provider.

Calculate:

\[
Z = \frac{CurrentPrice - Mean}{StandardDeviation}
\]

Where:

- CurrentPrice = latest available price.
- Mean = historical rolling mean.
- StandardDeviation = historical population standard deviation.

## 9.3 Signals

Generate:

```text
BUY  when Z <= buy_threshold

SELL when Z >= sell_threshold

NONE otherwise
```

The signal is a current condition, not an instruction to execute a trade.

Signals must be calculated on every strategy refresh.

Signal transitions should be recorded so that the application can distinguish a newly generated signal from an existing signal.

On the first calculation, an existing threshold condition should immediately produce the corresponding signal.

If the price returns between the thresholds, the current signal becomes NONE.

If insufficient historical data exists, return an explicit insufficient-data status.

If standard deviation is zero, return an invalid-calculation status rather than generating a signal.

## 9.4 Strategy output

Return:

```text
ticker
current_price
daily_change
daily_change_pct
mean
standard_deviation
z_score
signal
status
calculated_at
```

Example:

```json
{
    "ticker": "AAPL",
    "current_price": 215.42,
    "daily_change": -2.68,
    "daily_change_pct": -1.23,
    "mean": 220.10,
    "standard_deviation": 2.50,
    "z_score": -1.87,
    "signal": null,
    "status": "OK"
}
```

## 9.5 Signal history

Maintain a signal history file:

```text
data/strategies/signals.parquet
```

Record:

- Strategy instance ID.
- Strategy name.
- Ticker.
- Previous signal.
- New signal.
- Z-score.
- Current price.
- Timestamp.

Only record changes in signal state.

Do not record duplicate events on every refresh.

---

# 10. Backend API specification

Use the `/api` prefix for all endpoints.

All responses should use consistent JSON structures.

## 10.1 Market data

| Endpoint | Method | Purpose |
|---|---|---|
| `/market-data/search` | GET | Search ticker |
| `/market-data/prices` | GET | Retrieve current prices |
| `/market-data/history` | GET | Retrieve historical prices |
| `/market-data/refresh` | POST | Refresh market data |
| `/market-data/status` | GET | Retrieve last refresh information |

## 10.2 Portfolios

| Endpoint | Method | Purpose |
|---|---|---|
| `/portfolios?type=` | GET | List portfolios |
| `/portfolios` | POST | Create portfolio (name, description, type) |
| `/portfolios/{id}` | GET | Retrieve portfolio |
| `/portfolios/{id}` | PUT | Update name and description |
| `/portfolios/{id}` | DELETE | Delete portfolio and its positions |
| `/portfolios/{id}/tickers` | POST | Add ticker to a watchlist (validated, §6.4) |
| `/portfolios/{id}/tickers/{ticker}` | DELETE | Remove ticker from a watchlist |
| `/portfolios/{id}/favourites/{ticker}` | PUT | Mark favourite |
| `/portfolios/{id}/favourites/{ticker}` | DELETE | Unmark favourite |
| `/portfolios/{id}/quotes` | GET | Rows for the Portfolio pane: ticker, price, daily change, daily change %, stale, favourite |

## 10.3 Positions

| Endpoint | Method | Purpose |
|---|---|---|
| `/portfolios/{id}/positions?status=open\|closed\|all` | GET | Positions with calculated metrics, plus per-currency totals |
| `/portfolios/{id}/positions` | POST | Create position |
| `/positions/{id}` | GET | Retrieve position |
| `/positions/{id}` | PUT | Edit position |
| `/positions/{id}/close` | POST | Close position (exit price and date) |
| `/positions/{id}` | DELETE | Delete position |

## 10.4 Transactions and cash

Removed in revision 1.1.

## 10.5 Strategies

| Endpoint | Method | Purpose |
|---|---|---|
| `/strategies` | GET | List available strategies |
| `/strategies/{name}/schema` | GET | Retrieve configuration schema |
| `/strategies/{name}/run` | POST | Execute strategy |
| `/strategies/signals` | GET | Retrieve signal history |

Example strategy request:

```json
{
    "tickers": ["AAPL", "MSFT"],
    "config": {
        "lookback_days": 20,
        "buy_threshold": -2.0,
        "sell_threshold": 2.0
    }
}
```

## 10.6 Dashboard

Dashboard layouts are localStorage-based in V1.

No backend layout persistence is required.

However, the backend should expose enough information for the frontend to initialise its panes.

A future endpoint for user-specific dashboard configurations can be added without changing the underlying pane model.

## 10.7 API standards

Implement:

- Pydantic request validation.
- Consistent error responses.
- Appropriate HTTP status codes.
- Input validation.
- API documentation through FastAPI/OpenAPI.
- Pagination for signal history where appropriate.

Never return Python exception stack traces to the frontend.

Log full exceptions on the backend.

---

# 11. Market data refresh orchestration

The frontend must have one global Refresh button.

Implement the following workflow:

```text
USER PRESSES REFRESH
          |
          v
POST /market-data/refresh
          |
          v
BACKEND DETERMINES REQUIRED TICKERS
          |
          v
COLLECT UNIQUE TICKER LIST
          |
          v
RETRIEVE LATEST MARKET PRICES
          |
          v
UPDATE CURRENT PRICE CACHE
          |
          v
RETURN REFRESH RESULT
          |
          v
FRONTEND REFRESHES ALL PANES
          |
          +--------------------+
          |                    |
          v                    v
     PORTFOLIO             POSITIONS
          |                    |
          +--------------------+
          |
          v
     STRATEGIES
          |
          v
     UPDATE DASHBOARD
```

The required ticker list must include:

- Every portfolio's tickers. For `positions` portfolios, these are the tickers of open positions. Closed positions need no current price.
- Symbols referenced by active strategy panes. Panes are stored in browser localStorage, so the frontend sends these symbols in the request body:

```json
{"extra_tickers": ["NVDA", "TSLA"]}
```

Retrieve prices once per unique ticker.

Avoid duplicate provider requests.

The refresh endpoint should return:

```json
{
    "status": "completed",
    "started_at": "...",
    "completed_at": "...",
    "tickers_requested": 10,
    "tickers_updated": 9,
    "tickers_failed": 1,
    "errors": []
}
```

The backend must support partial success.

A failed ticker must not invalidate successful updates for other tickers.

If a provider request fails, retain the previous valid price and expose its stale status.

The frontend should display refresh status and last successful refresh timestamp.

For V1, use synchronous refresh requests with sensible request timeouts. If provider latency makes this unreliable, introduce a background refresh job and status-polling mechanism as a separate improvement.

---

# 12. Frontend architecture

## 12.1 Application structure

Implement a React/TypeScript application.

The main application should consist of:

```text
App
 |
 +-- Header
 |     |
 |     +-- Application Menu
 |     +-- Add Pane Menu
 |     +-- Refresh Button
 |     +-- Refresh Status
 |
 +-- Dashboard
       |
       +-- Portfolio Pane
       |
       +-- Positions Pane
       |
       +-- Strategy Pane
```

The dashboard should support multiple independent pane instances.

## 12.2 Pane model

Every pane must have:

```typescript
interface Pane {
    id: string;
    type: string;
    title: string;
    config: Record<string, unknown>;
}
```

Layout information should be stored separately:

```typescript
interface PaneLayout {
    i: string;
    x: number;
    y: number;
    w: number;
    h: number;
}
```

Each pane must have:

- Unique ID.
- Type.
- Title.
- Configuration.
- Position.
- Dimensions.

## 12.3 Dashboard functionality

Implement:

- Add pane.
- Remove pane.
- Move pane.
- Resize pane.
- Minimise pane if supported by the layout library.
- Reset layout.
- Save layout automatically.
- Restore last saved layout on startup.

Allow multiple instances of the same pane type.

## 12.4 Layout persistence

Store the dashboard layout in localStorage.

Suggested key:

```text
my-trading-platform-layout
```

Example:

```json
{
    "version": 1,
    "panes": [],
    "layouts": []
}
```

Save changes automatically after pane additions, removals, movements and resizing.

Validate the stored layout when loading it.

If an incompatible or corrupted layout is encountered, fall back to a default layout rather than crashing the application.

---

# 13. Frontend components

## 13.1 Shared DataGrid component

Create a reusable grid component.

Responsibilities:

- Display tabular data.
- Sort columns.
- Format prices and percentages.
- Display gains in green.
- Display losses in red.
- Support loading and error states.
- Support empty data states.

Sorting should support:

- Alphabetical ticker sorting.
- Numeric ascending/descending.
- Percentage ascending/descending.
- Absolute monetary value (market value, P&L) ascending/descending.

Sorting should be performed client-side for the initial application.

## 13.2 Portfolio pane

Configuration: the portfolio to show, which can be of either type.

Display:

| Column | Description |
|---|---|
| ★ | Favourite marker. Can be toggled |
| Ticker | Symbol |
| Price | Latest price |
| Daily Change | Absolute change |
| Daily Change % | Percentage change |

Allow sorting by all relevant columns. Show a stale indicator on prices whose last refresh failed.

Controls for watchlists:

- Add ticker, using ticker search.
- Remove ticker.
- Toggle favourite.

The pane must refresh after global market data refresh.

## 13.3 Positions pane

Configuration: the `positions` portfolio to show, and whether to show closed positions.

Open positions:

| Column | Description |
|---|---|
| Ticker | Symbol |
| Quantity | Current quantity |
| Entry Price | Entry price |
| Price | Current market price |
| Market Value | Current value |
| Daily Change | Price change |
| Daily P&L | Daily profit/loss |
| Unrealised P&L | Absolute profit/loss |
| Unrealised P&L % | Percentage profit/loss |

Closed positions, shown when the option is enabled:

| Column | Description |
|---|---|
| Ticker | Symbol |
| Quantity | Quantity |
| Entry Price | Entry price |
| Exit Price | Exit price |
| Exit Date | Exit date |
| Realised P&L | Absolute profit/loss |
| Realised P&L % | Percentage profit/loss |

Show one totals row per currency (§7.4), and never a single total across currencies.

Provide controls for:

- Add position.
- Edit position.
- Close position.
- Delete position.

Closing and deleting require confirmation. The entry price and exit price default to the latest available market price.

## 13.4 Strategy pane

When creating a strategy pane:

1. Display available strategies.
2. Allow the user to select a strategy.
3. Retrieve the strategy configuration schema.
4. Generate the configuration form dynamically.
5. Allow the user to select the ticker source.
6. Save the configuration to the pane.

Ticker source options:

- Portfolio: choose any watchlist or positions portfolio.
- Portfolio favourites.
- Manual selection.

For the initial Mean Reversion strategy, display:

| Column | Description |
|---|---|
| Ticker | Symbol |
| Price | Current price |
| Daily Change | Absolute change |
| Daily Change % | Percentage change |
| Mean | X-day mean |
| Std Dev | X-day standard deviation |
| Z-Score | Current z-score |
| Signal | BUY / SELL / blank |
| Status | Calculation status |

Use green for BUY and red for SELL.

If there is insufficient data, display an appropriate status instead of a misleading numerical result.

The pane must refresh after global market data refresh.

## 13.5 Dynamic strategy forms

Do not hardcode the Mean Reversion configuration form.

Generate it using the configuration schema returned by the backend.

Support at least:

- Integer parameters.
- Numeric parameters.
- String parameters.
- Boolean parameters.
- Minimum and maximum values.
- Defaults.
- Descriptions.

This is essential for future strategy extensibility.

---

# 14. Persistence and data integrity

## 14.1 General rules

All Parquet writes must:

1. Acquire an appropriate file lock.
2. Validate incoming data.
3. Write to a temporary file.
4. Flush and close the file.
5. Atomically replace the original file.
6. Release the lock.

Use a single backend process for V1.

Prevent simultaneous writes from corrupting data.

## 14.2 Data recovery

Implement a basic backup mechanism.

At minimum:

- Back up application state periodically.
- Back up before significant destructive operations: deleting a portfolio or a position.
- Retain a configurable number of backups.
- Provide a script to rebuild derived data.

Market data caches do not need the same backup priority because they can be retrieved again.

## 14.3 Schema versioning

Persist an application data schema version.

When the application starts:

- Check the current schema version.
- Validate existing files.
- Detect incompatible schemas.
- Provide clear errors.
- Do not silently overwrite incompatible data.

Implement migrations when necessary.

---

# 15. Configuration

Create a central backend configuration module.

Support environment variables for:

```text
APP_ENV
APP_HOST
APP_PORT
DATA_DIR
MARKET_DATA_PROVIDER
MARKET_DATA_TIMEOUT
CURRENT_PRICE_ARCHIVE_THRESHOLD
BACKUP_RETENTION_COUNT
```

Defaults:

```text
APP_ENV=development
APP_HOST=127.0.0.1
APP_PORT=8000
DATA_DIR=~/mytradingplatform/data
MARKET_DATA_PROVIDER=yfinance
MARKET_DATA_TIMEOUT=30
CURRENT_PRICE_ARCHIVE_THRESHOLD=100000
BACKUP_RETENTION_COUNT=10
```

The frontend should have its backend API URL configurable through its environment configuration.

Do not expose the data directory through static file serving.

---

# 16. Error handling and logging

Implement structured backend logging.

Log:

- Application startup and shutdown.
- Market data refresh start/completion.
- Provider errors.
- Cache hits and misses.
- Strategy execution.
- Persistence operations.
- Portfolio and position operations.
- Unexpected exceptions.

The UI must handle:

- Backend unavailable.
- Market data provider unavailable.
- Missing historical prices.
- Invalid ticker.
- Invalid strategy configuration.
- Insufficient historical data.
- Invalid calculations.
- Persistence errors.

Never silently convert failed operations into successful ones.

The last valid market price should remain available when a refresh fails.

Display stale data warnings where appropriate.

---

# 17. Implementation phases

The AI agent should implement the application in the following sequence.

Each phase must be completed and tested before moving to the next.

## Phase 1 – Project foundation

Tasks:

1. Create the project directory structure.
2. Set up the Python environment.
3. Install backend dependencies.
4. Set up FastAPI.
5. Configure application settings.
6. Implement data directory initialisation.
7. Set up React with TypeScript and Vite.
8. Configure frontend/backend development environments.
9. Add a basic application health endpoint.
10. Add README setup instructions.

Acceptance criteria:

- Backend starts successfully.
- Frontend starts successfully.
- Frontend can communicate with backend.
- Data directories are created automatically.
- Configuration can be overridden through environment variables.
- Health endpoint returns success.

## Phase 2 – Persistence foundation

Tasks:

1. Implement Parquet read/write utilities.
2. Implement atomic writes.
3. Implement file locking.
4. Implement DuckDB query utilities.
5. Implement schema validation.
6. Implement backup utilities.
7. Add persistence unit tests.

Acceptance criteria:

- Parquet files can be created and read.
- Existing files can be updated safely.
- Concurrent writes are serialised.
- DuckDB can query Parquet files.
- Derived data can be rebuilt.
- Persistence failures are reported correctly.

## Phase 3 – Market data

Tasks:

1. Define provider interface.
2. Implement yfinance provider.
3. Implement ticker search.
4. Implement historical price retrieval.
5. Implement current price retrieval.
6. Implement market data normalisation.
7. Implement historical cache.
8. Implement current price cache.
9. Implement cache rotation.
10. Implement history materialised view.
11. Add market data tests using mocked provider responses.

Acceptance criteria:

- Ticker search returns normalised results.
- Historical prices can be retrieved.
- Current prices can be retrieved.
- Cached historical prices are reused.
- Missing historical data is downloaded.
- Current prices are timestamped.
- Provider errors do not corrupt the cache.
- A different provider could be implemented without changing the market data service.

## Phase 4 – Portfolio management

Tasks:

1. Implement portfolio models, including the `watchlist` and `positions` types.
2. Implement portfolio persistence.
3. Implement the portfolio service.
4. Implement ticker validation on add (§6.4).
5. Implement ticker and favourite management.
6. Implement the portfolio API, including `/portfolios/{id}/quotes`.
7. Create the default portfolios.
8. Remove the obsolete `transactions/` data directory from the directory layout and the backup set.

Acceptance criteria:

- The default portfolios are created on first startup.
- Multiple portfolios of each type can be created.
- Tickers can be added to and removed from watchlists.
- Invalid tickers are rejected. When the provider is unavailable, the error says so.
- Favourites can be added and removed, and are always a subset of the portfolio's tickers.
- The same ticker can belong to multiple portfolios.
- Portfolio names are unique, regardless of case.
- The last remaining portfolio cannot be deleted.
- Deleting a portfolio takes a backup first.
- Invalid portfolio operations return meaningful errors.

## Phase 5 – Positions

Tasks:

1. Implement position models.
2. Implement position persistence.
3. Implement create, edit, close and delete.
4. Default entry and exit prices to the latest available price.
5. Implement position calculations: market value, unrealised, realised and daily P&L.
6. Implement per-currency totals.
7. Derive the tickers of `positions` portfolios from their open positions.
8. Implement the positions API.

Acceptance criteria:

- Positions can be created, edited, closed and deleted.
- A portfolio can hold only one open position per ticker. A closed ticker can be opened again.
- Quantity and prices must be positive.
- Unrealised, realised and daily P&L are calculated correctly.
- Totals are calculated per currency and never mixed across currencies.
- Missing current prices result in null values, never made-up ones.
- Closing or deleting a position updates the portfolio's tickers and favourites.
- Deleting a position takes a backup first.

## Phase 6 – Strategy engine

Tasks:

1. Implement BaseStrategy.
2. Implement strategy registry.
3. Implement strategy discovery.
4. Implement configuration schemas.
5. Implement configuration validation.
6. Implement strategy execution engine.
7. Implement standard result models.
8. Implement signal history persistence.

Acceptance criteria:

- Available strategies can be listed.
- Strategy schemas can be retrieved.
- Strategy configurations are validated.
- Strategies can be executed using ticker lists.
- Strategies are independent of portfolio and position services.
- A new strategy can be added without creating a new API route.

## Phase 7 – Mean Reversion strategy

Tasks:

1. Implement historical price retrieval.
2. Implement rolling mean calculation.
3. Implement population standard deviation.
4. Implement z-score calculation.
5. Implement BUY and SELL conditions.
6. Implement insufficient-data handling.
7. Implement zero-standard-deviation handling.
8. Implement signal transition detection.
9. Implement signal history.

Acceptance criteria:

- Calculations produce expected results for known test datasets.
- Lookback period is configurable.
- Buy threshold is configurable.
- Sell threshold is configurable.
- The current incomplete trading session is excluded from historical statistics.
- Signals are correctly generated.
- Duplicate signal events are not recorded.
- Insufficient data does not generate false signals.

## Phase 8 – Frontend foundation

Tasks:

1. Create application shell.
2. Implement header/menu.
3. Implement dashboard.
4. Integrate React Grid Layout.
5. Implement pane registry.
6. Implement add/remove pane functionality.
7. Implement drag and resize.
8. Implement localStorage persistence.
9. Implement layout restoration.
10. Implement layout reset.

Acceptance criteria:

- Multiple panes can be added.
- Multiple panes of the same type can coexist.
- Panes can be moved.
- Panes can be resized.
- Layout is automatically saved.
- Layout is restored after browser refresh.
- Invalid saved layouts do not crash the application.

## Phase 9 – Dashboard panes

Tasks:

1. Implement reusable DataGrid.
2. Implement PortfolioPane.
3. Implement PositionsPane.
4. Implement StrategyPane.
5. Implement dynamic strategy configuration forms.
6. Implement ticker source selection.
7. Implement pane-specific configurations.
8. Implement loading and error states.

Acceptance criteria:

- Portfolio pane displays current prices.
- Positions pane displays quantities, valuation and P&L, per-currency totals and closed history.
- Strategy pane displays mean, standard deviation, z-score and signal.
- Sorting works.
- Profit/loss formatting works.
- Multiple strategy configurations can coexist.
- Pane configurations survive browser refresh.

## Phase 10 – Market data refresh integration

Tasks:

1. Implement global Refresh button.
2. Implement backend refresh orchestration.
3. Collect unique ticker symbols.
4. Retrieve current prices.
5. Update market data cache.
6. Refresh all dashboard panes.
7. Execute active strategies.
8. Display refresh status.
9. Handle partial failures.
10. Preserve last valid data.

Acceptance criteria:

- One Refresh action updates all panes.
- Duplicate ticker requests are avoided.
- Strategies recalculate after refresh.
- Failed ticker requests do not invalidate successful ones.
- Last valid data remains visible.
- Refresh timestamps are displayed.
- The UI provides meaningful feedback during refresh.

## Phase 11 – Integration and quality assurance

Tasks:

1. Run all backend tests.
2. Run all frontend tests.
3. Test complete user workflows.
4. Test data persistence across restarts.
5. Test backup and recovery.
6. Test invalid input handling.
7. Test market data failures.
8. Test dashboard layout restoration.
9. Review application logs.
10. Complete documentation.

Acceptance criteria:

The application must support the complete workflow:

1. Start the application.
2. Open the dashboard.
3. Add ticker symbols to a watchlist.
4. Mark favourite symbols.
5. Refresh market data.
6. Add positions, with quantity and entry price, to a positions portfolio.
7. View position valuation and P&L, with per-currency totals.
8. Close a position, and view realised P&L in the closed history.
9. Add a Mean Reversion strategy pane.
10. Configure its lookback period.
11. Select a positions portfolio or a watchlist as its source.
12. Refresh market data.
13. View calculated strategy metrics and signals.
14. Move and resize panes.
15. Close the browser.
16. Reopen the application.
17. Restore the previous dashboard layout.
18. Verify that portfolio and position data remain intact.

---

# 18. Testing requirements

Testing is mandatory throughout implementation.

Do not postpone testing until the end.

## 18.1 Backend unit tests

Test at least:

- Market data normalisation.
- Cache retrieval.
- Cache updates.
- Missing historical data.
- Portfolio operations.
- Favourite management.
- Ticker validation on add.
- Position validation: positive values, and one open position per ticker.
- Position calculations.
- Realised P&L.
- Unrealised and daily P&L.
- Per-currency totals.
- Strategy discovery.
- Strategy configuration validation.
- Mean reversion calculations.
- Signal transitions.
- Parquet persistence.
- Atomic file updates.

## 18.2 Frontend tests

Test:

- Dashboard initialisation.
- Adding panes.
- Removing panes.
- Moving panes.
- Resizing panes.
- Layout persistence.
- Layout restoration.
- Portfolio grid rendering.
- Position grid rendering.
- Strategy grid rendering.
- Sorting.
- Gain/loss formatting.
- Configuration form generation.
- API error handling.

## 18.3 Integration tests

Use mocked market data providers.

Do not make external Yahoo Finance calls during automated tests.

Test complete workflows involving:

- Market data retrieval and caching.
- Portfolio creation and ticker management.
- Position creation, editing, closing and deletion.
- Position valuation after a market data refresh.
- Strategy execution.
- Dashboard data refresh.

Include regression tests for any bugs discovered during implementation.

---

# 19. Documentation requirements

Create a README containing:

1. Project overview.
2. Architecture overview.
3. Technology stack.
4. Prerequisites.
5. Installation instructions.
6. Backend startup instructions.
7. Frontend startup instructions.
8. Configuration options.
9. Data directory structure.
10. Testing instructions.
11. Troubleshooting.

Also document:

- API endpoints.
- Parquet schemas.
- Strategy interface.
- How to add a new market data provider.
- How to add a new strategy.

The documentation must be updated as the implementation evolves.

---

# 20. Instructions to the AI coding agent

These instructions apply to the entire project.

## 20.1 Implementation discipline

Follow these rules:

1. Implement the project incrementally, following the phases in this document.
2. Do not attempt to generate the entire application in one step.
3. Complete each phase before proceeding to the next.
4. Run relevant tests after each implementation phase.
5. Fix failing tests before proceeding.
6. Do not introduce unnecessary dependencies.
7. Do not introduce a database in V1.
8. Do not introduce authentication in V1.
9. Do not implement broker integration.
10. Do not implement automatic trade execution.

## 20.2 Architecture discipline

Maintain the separation between:

- API.
- Business services.
- Market data providers.
- Strategies.
- Persistence.
- Frontend presentation.

Do not bypass these boundaries for convenience.

In particular:

- Never call yfinance directly from strategy implementations.
- Never access Parquet files directly from API routes.
- Never implement financial calculations in React.
- Never hardcode strategy-specific configuration forms in React.
- Never introduce provider-specific market data structures into business logic.

## 20.3 Data integrity

Financial data must be handled carefully.

- Validate position inputs.
- Store user-entered quantities and prices as exact decimals.
- Make writes atomic.
- Never aggregate values across currencies.
- Never silently overwrite corrupted or incompatible data.

Where market data is unavailable, display an appropriate error or stale-data status.

Never fabricate market prices.

## 20.4 Extensibility

The following operations must not require fundamental architectural changes:

- Adding another market data provider.
- Adding another strategy.
- Adding another portfolio.
- Adding another pane type.
- Changing dashboard layouts.
- Introducing authentication.
- Moving persistence from Parquet to a database in a later version.

Do not overengineer these future capabilities. Establish clean interfaces and sensible boundaries.

## 20.5 Agent reporting

At the end of each phase, provide:

- What was implemented.
- Files created or modified.
- Tests executed.
- Test results.
- Known limitations.
- Any deviations from the specification.

Do not claim a feature is complete unless its acceptance criteria have been tested.

If a requirement cannot be implemented as written, explain why and propose an alternative before making a significant architectural change.

---

# 21. Definition of Done – Version 1

Version 1 is considered complete when:

- [ ] The backend starts successfully.
- [ ] The frontend starts successfully.
- [ ] The application operates without a database.
- [ ] Market data is retrieved through the provider abstraction.
- [ ] Historical data is cached in Parquet.
- [ ] Current prices are cached in Parquet.
- [ ] DuckDB can query the cached data.
- [ ] Portfolio management works.
- [ ] Favourites work.
- [ ] Position management works: create, edit, close, delete.
- [ ] Closed position history is displayed.
- [ ] Position valuation works, with per-currency totals.
- [ ] Realised and unrealised P&L are calculated correctly.
- [ ] Strategies can be discovered dynamically.
- [ ] Strategy configuration forms are generated dynamically.
- [ ] Mean Reversion works correctly.
- [ ] Signal transitions are recorded.
- [ ] Portfolio pane works.
- [ ] Positions pane works.
- [ ] Strategy pane works.
- [ ] Multiple panes can coexist.
- [ ] Panes can be moved and resized.
- [ ] Dashboard layout is persisted in localStorage.
- [ ] Global market data refresh works.
- [ ] All panes refresh after market data updates.
- [ ] Errors and stale data are handled correctly.
- [ ] Backend and frontend tests pass.
- [ ] Documentation is complete.

---

# 22. Final implementation guidance

The priority is to deliver a working, maintainable application rather than an elaborate framework.

The implementation should follow three principles:

**1. Data first.**

Get market data, caching, portfolio management, position accounting and strategy calculations correct before investing heavily in the dashboard.

**2. Generic architecture, specific first implementation.**

The strategy engine, market data provider and pane architecture should be generic. However, only implement yfinance, Mean Reversion and the three requested pane types in V1.

**3. Keep V1 local and simple.**

Use local files, a single backend process and manual refresh. Avoid databases, authentication, cloud infrastructure and unnecessary asynchronous processing.

The result should be a fully functional personal trading dashboard that provides a solid foundation for subsequent development.