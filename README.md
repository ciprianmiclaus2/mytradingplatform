# My Trading Platform

A locally hosted, single-user signal-generation dashboard. It monitors watchlists of ticker symbols, shows the positions held in your brokerage accounts (pulled read-only through [SnapTrade](https://snaptrade.com)) with their P&L, and runs configurable strategies such as mean reversion. All data is stored in local Parquet files. It never places real trades and does no accounting.

> **Status:** Version 1 is complete (Phases 1–11). See
> [docs/MyTradingPlatform_v1_ImplementationPlan.md](docs/MyTradingPlatform_v1_ImplementationPlan.md)
> for the full V1 plan.

## Architecture overview

```text
Browser (React + Vite, :5173)
   │  /api/*  (proxied by Vite in development)
   ▼
FastAPI backend (:8000)
   ├── api/           HTTP routes only, no business logic
   ├── services       portfolio, brokers (SnapTrade), market data, strategies
   └── persistence/   Parquet files + DuckDB queries (DATA_DIR)
```

The backend is a modular monolith running as a single process. The frontend calls it only through the API.

## Technology stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic, pydantic-settings, Uvicorn |
| Data | Pandas, PyArrow (Parquet), DuckDB, yfinance |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4, React Grid Layout 2 |
| Tests | Pytest + FastAPI TestClient, Vitest + Testing Library |

Exact versions are pinned in [backend/requirements.txt](backend/requirements.txt) and [frontend/package.json](frontend/package.json).

## Prerequisites

- Python 3.12 or newer
- Node.js 22 or newer, with npm

## Installation

```bash
# Backend
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Frontend
cd ../frontend
npm install
```

## Running

### One command

```bash
./start.sh
```

The script:

- Loads nvm if `npm` isn't already on the PATH.
- Creates the backend virtual environment and installs dependencies on first run. It installs again only when `requirements.txt` or `package-lock.json` changes.
- Starts the backend and waits for `/api/health` to respond.
- Starts the frontend at http://127.0.0.1:5173.

Output from the two servers is prefixed `[backend]` and `[frontend]`. **Ctrl+C stops both.** Backend variables pass straight through, for example `APP_PORT=8001 DATA_DIR=/tmp/mtp ./start.sh`. The frontend proxy follows `APP_PORT` automatically, and `FRONTEND_PORT` (default 5173) sets the frontend port. `start.sh` refuses to start if either port is already in use, so a second copy can't silently attach to the first one's backend and data. To run a second copy alongside, use different ports: `APP_PORT=8100 FRONTEND_PORT=5273 DATA_DIR=/tmp/mtp ./start.sh`.

### Separately

Start the backend first, then the frontend, each in its own terminal.

```bash
# Backend: http://127.0.0.1:8000, API docs at http://127.0.0.1:8000/api/docs
cd backend
.venv/bin/python -m app
```

```bash
# Frontend: http://127.0.0.1:5173
cd frontend
npm run dev
```

`python -m app` uses `APP_HOST` and `APP_PORT`, and auto-reloads when `APP_ENV=development`. You can also run Uvicorn directly with `.venv/bin/uvicorn app.main:app --reload`.

Check that everything is up:

```bash
curl http://127.0.0.1:8000/api/health          # backend directly
curl http://127.0.0.1:5173/api/health          # via the Vite proxy
```

The header of the web page shows "Backend connected" when the frontend can reach the backend.

### Using the dashboard

The dashboard is a grid of tiles. Each tile holds one or more panes as tabs.

- **Add pane** adds a Portfolio, Positions or Strategy pane in a new tile. You can have several of the same type.
- **Tabs** are named automatically from each pane's settings, for example "Main Portfolio", "Positions · Brokerage ****1234" or "RSI · Tech favourites". Identical names within a tile are numbered.
- **Group panes as tabs:** open a tab's **⋯** menu and choose **Move … to:** another tile. **Detach** puts a tab back in its own tile. Drag a tab sideways within its tab bar to reorder it; click a tab, or use the arrow keys, to switch.
- **Move** a tile by dragging its grip (⠿) or the empty part of its header. **Resize** it from its bottom-right corner.
- **–** minimises a tile to its header. **×** on a tab removes that pane, after you confirm.
- **Menu → SnapTrade settings…** connects your broker accounts (see below).
- **Menu → Reset layout** restores the default panes.

Panes in hidden tabs keep working: a Refresh updates them and their strategies recalculate, so signal history stays complete.

**Refresh:** the **↻ Refresh** button in the header fetches the latest price of every ticker the dashboard uses, once each: every portfolio's tickers, the tickers held in your broker accounts, and tickers typed into strategy panes. All panes then reload and strategies recalculate. Next to the button you see the outcome (for example "1 of 12 tickers failed", with **details**) and the time of the last successful refresh. A ticker that fails keeps its last valid price, marked ⚠. Prices are only fetched when you press Refresh (and when a ticker is first added). This Refresh does not contact SnapTrade; each Positions pane has its own refresh button for that.

**Panes:**

- **Portfolio:** prices, daily change and daily change % for any portfolio. Use **⋯** to create, rename or delete portfolios. For a watchlist, type a symbol or company name in **Add ticker…** and pick a suggestion or press Enter; **★** marks favourites, and **×** removes a ticker. ⚠ marks a price whose last refresh failed (the last known price is shown).
- **Positions:** the positions of one broker account, pulled through SnapTrade: quantity, average cost, price, market value, daily P&L and unrealised P&L, with one totals row per currency. Choose the account at the top. **↻ Refresh** fetches that account's positions from SnapTrade (the account list is fetched first); the pane shows when it was last refreshed and how old SnapTrade's data from the broker is. Prices come from the dashboard's market data where a holding maps to a ticker (London holdings are converted from pence); otherwise, for example for options, the broker's price at the last refresh is used, marked ⓑ.
- **Strategy:** choose a strategy (Bollinger Bands, MACD, Mean Reversion, Moving Average Crossover or RSI), its settings (the form is built from the strategy's own parameter list), and its tickers: a portfolio, a portfolio's favourites, a broker account's holdings, or a typed list. The pane shows the strategy's metrics and the BUY (green) or SELL (red) signal per ticker; **Settings** changes the configuration, **↻** recalculates, and **About** explains how the strategy works and how to read it (also available as "How this strategy works" while choosing). Tickers without enough history show a status rather than numbers.

Hover a ticker to see the company or fund name; click it to open its Yahoo Finance page in a new window (options link to Yahoo's option page; cash and unmapped holdings have no link). Click a column header to sort; click again to reverse. Each pane's settings (selected portfolio or account, strategy configuration) are saved with the layout.

### Broker accounts (SnapTrade)

Positions come from your brokerage accounts through SnapTrade, read-only: the app never places or changes orders.

1. At [dashboard.snaptrade.com](https://dashboard.snaptrade.com), turn on two-factor authentication, then create a **Personal API key** on the API Key page (free, for your own accounts). Copy the **Client ID** and **Consumer key** straight away. Connect your brokerages in the SnapTrade dashboard.
2. In the app, open **Menu → SnapTrade settings…** (or **Set up SnapTrade…** in a Positions pane) and enter the **Client ID** and **Consumer key**. Leave **User ID** and **User secret** empty: a Personal key identifies you by itself.
   - With a **Commercial** key, also enter the User ID and User secret of the user you registered through the SnapTrade API (`registerUser`). They go together: both or neither.
3. **Connect** checks them with SnapTrade, saves them, lists your accounts and loads each account's positions. Nothing is saved if SnapTrade rejects them.
4. **Add a pane for each account** adds one Positions pane per account that doesn't have one yet. Each pane has its own **↻ Refresh**.

The credentials are stored on this computer in `$DATA_DIR/config/snaptrade.json`, readable only by your user (file mode 0600). The API never returns them; the settings dialog shows only their last four characters. They are not included in backups. **Disconnect…** deletes them and the cached accounts and positions; it doesn't change anything at SnapTrade.

With a Personal key, SnapTrade fetches holdings from the broker when they are requested (its Daily plan, for Commercial keys, updates about once a day); "Broker data as of" in the pane shows the time of SnapTrade's data. SnapTrade also limits how often an account can be queried; if you refresh too often, the pane shows when to try again.

Earlier versions had manually entered positions lists. These have been replaced by broker accounts: any old positions list is removed on startup, after a backup is taken.

The layout is saved automatically in your browser's `localStorage`, under the key `my-trading-platform-layout`, and is restored when you reopen the page. A saved layout that can't be read is replaced by the default layout, and a notice tells you so.

## Configuration

### Backend

The backend reads its settings from environment variables, or from an optional `backend/.env` file. See [backend/.env.example](backend/.env.example).

| Variable | Default | Description |
|---|---|---|
| `APP_ENV` | `development` | `development`, `test` or `production` |
| `APP_HOST` | `127.0.0.1` | Bind address |
| `APP_PORT` | `8000` | Bind port |
| `DATA_DIR` | `~/mytradingplatform/data` | Data root. `~` expands to your home directory; relative paths resolve against the project root |
| `MARKET_DATA_PROVIDER` | `yfinance` | Market data provider |
| `MARKET_DATA_TIMEOUT` | `30` | Provider request timeout, in seconds |
| `CURRENT_PRICE_ARCHIVE_THRESHOLD` | `100000` | Row count at which the current-price file is rotated |
| `BACKUP_RETENTION_COUNT` | `10` | Number of backups kept |
| `BACKUP_ON_STARTUP` | `true` | Back up application state on startup (skipped if nothing changed since the last backup) |
| `PERSISTENCE_LOCK_TIMEOUT` | `10` | Seconds to wait for the data write lock |
| `SNAPTRADE_BASE_URL` | `https://api.snaptrade.com` | SnapTrade API address |
| `SNAPTRADE_TIMEOUT` | `30` | Seconds to wait for each SnapTrade request |
| `CORS_ORIGINS` | the Vite dev origins | JSON list of allowed browser origins |
| `LOG_LEVEL` | `INFO` | Log level. Logs are written to stderr as JSON lines. `DEBUG` adds every file write and full provider error text |

### Frontend

The frontend reads `frontend/.env.local`. See [frontend/.env.example](frontend/.env.example).

| Variable | Default | Description |
|---|---|---|
| `VITE_API_BASE_URL` | `/api` | Base URL the browser uses for API calls |
| `VITE_BACKEND_URL` | `http://127.0.0.1:8000` | Where the Vite dev server forwards `/api` requests |

## Data directory

The backend creates this layout on startup if it doesn't already exist:

```text
$DATA_DIR/
├── market_data/
│   ├── close_prices/        one Parquet file per trading date (YYYYMMDD.parquet), all tickers
│   ├── coverage.parquet     date ranges already fetched per ticker
│   ├── names.parquet        company or fund name per ticker (from quotes)
│   ├── current/             current-price time series; current.YYYYMMDDHHMMSS.parquet archives
│   ├── history/             history.parquet: rebuildable consolidated view
│   └── refresh_status.json  last refresh result and per-ticker refresh state
├── portfolios/
│   └── portfolios.parquet   watchlists
├── brokers/                 cache of the last SnapTrade refresh (rebuilt by refreshing)
│   ├── accounts.parquet     accounts, with their last refresh times
│   ├── positions.parquet    positions per account
│   └── status.json          time the account list was last fetched
├── config/                  owner-only (0700), never backed up
│   └── snaptrade.json       SnapTrade credentials (0600)
├── strategies/
│   └── signals.parquet      recorded signal transitions
├── backups/
└── metadata/
    └── schema_version.json
```

On startup the backend:

1. Checks `metadata/schema_version.json`.
2. Removes temporary files left behind by an interrupted write.
3. Validates every known data file against its declared schema.
4. Rebuilds derived data whose source files have changed.
5. Takes a backup.

The backend refuses to start, and leaves the existing data untouched, if the schema version doesn't match or any data file is unreadable or incompatible.

All writes are validated, serialised by a single write lock, and atomic: data goes to a temporary file that then replaces the original. See [docs/architecture.md](docs/architecture.md#persistence).

## Maintenance scripts

Run these with the backend virtual environment. They use the same `DATA_DIR` setting as the backend.

```bash
backend/.venv/bin/python scripts/backup_data.py create --reason before-upgrade
backend/.venv/bin/python scripts/backup_data.py list
backend/.venv/bin/python scripts/backup_data.py verify <name>
backend/.venv/bin/python scripts/backup_data.py restore <name>   # stop the backend first

backend/.venv/bin/python scripts/rebuild_derived.py --list       # derived data and whether it's stale
backend/.venv/bin/python scripts/rebuild_derived.py              # rebuild everything
backend/.venv/bin/python scripts/rebuild_history.py              # rebuild market_data/history/history.parquet
```

A backup is a timestamped folder under `backups/` with a checksum manifest. It covers portfolios, strategies and metadata, but not market data or the broker cache, which can be downloaded again, and never the SnapTrade credentials. Restoring always backs up the current state first.

The data directory is never served over HTTP.

## Testing

```bash
cd backend && .venv/bin/python -m pytest
cd frontend && npm test            # Vitest
cd frontend && npm run build       # type-check + production build
cd frontend && npm run lint
```

Automated tests never call Yahoo Finance or SnapTrade. The market data tests use a fake in-memory provider (`tests/fakes.py`) and stubbed yfinance objects; the broker tests use a fake SnapTrade API (`tests/fake_snaptrade.py`) that checks every request's signature.

What the suites cover:

- **Backend unit tests** (`backend/tests/unit`): persistence, caches, provider, services, calculations, strategies.
- **Backend integration tests** (`backend/tests/integration`): every API endpoint, plus:
  - `test_workflow.py`: the whole V1 workflow, a restart on the same data folder, a refresh with the provider down (prices kept and marked stale), and recovery from a damaged data file with `scripts/backup_data.py restore`.
  - `test_invalid_input.py`: about 60 invalid requests across the API, each rejected with a 4xx error and leaving the data unchanged.
- **Frontend tests** (`frontend/src/**/*.test.ts(x)`): dashboard, layout persistence, data grid, each pane, the generated strategy form, the global refresh, and API errors.

**Manual acceptance check** (after changes that affect the UI). Run `./start.sh` with a scratch data folder (`DATA_DIR=/tmp/mtp-check ./start.sh`), then:

1. Add tickers and mark favourites, and press **Refresh**.
2. Connect SnapTrade (**Menu → SnapTrade settings…**), add a pane for each account, and press **↻ Refresh** in one of them.
3. Add a Strategy pane on a broker account, change the lookback, and press **Refresh**.
4. Move and resize panes, stop `start.sh`, close the browser, start again, and reopen. Layout, settings and data should all be unchanged.

## Troubleshooting

| Symptom | Fix |
|---|---|
| UI shows "The backend is unavailable." | Start the backend, and check that `VITE_BACKEND_URL` matches `APP_HOST`/`APP_PORT` |
| Backend exits with "schema version … migration is required" | `DATA_DIR` holds data from an incompatible version. Point `DATA_DIR` elsewhere, or migrate the data |
| Backend exits with "… is incompatible" or "… cannot be read" | A data file has the wrong schema or is damaged. Restore it with `scripts/backup_data.py restore <name>`, or rebuild derived data with `scripts/rebuild_derived.py` |
| API returns `persistence_lock_timeout` | A maintenance script is holding the write lock. Wait for it to finish |
| Prices show as stale | The last refresh failed for that ticker. The last valid price stays on screen; see `GET /api/market-data/status` |
| Ticker search returns 502 | Yahoo Finance is unreachable or rate-limiting. Try again later |
| SnapTrade setup says "rejected the request" | A value is wrong. "Unable to verify signature" points to the Client ID or Consumer key; "Invalid userID or userSecret" to the User ID or User secret (leave both empty for a Personal API key) |
| A Positions pane says "rate limit reached" | SnapTrade limits how often an account can be queried. Wait the time shown, then refresh again |
| A broker holding shows ⓑ instead of a live price | It couldn't be matched to a market data ticker (e.g. options, or an exchange the app doesn't know), so the broker's price at the last refresh is shown |
| Backend exits with "Cannot create data directory" | `DATA_DIR` isn't writable, or part of its path is a file |
| Browser shows a CORS error when `VITE_API_BASE_URL` is an absolute URL | Add the frontend origin to `CORS_ORIGINS` |
| `start.sh` says "Backend did not become healthy" but the backend log shows it started | Fixed in V1: the health check now ignores `http_proxy`/`https_proxy`. If you call the API with your own tools behind a proxy, add `127.0.0.1` to `no_proxy` |
| Refresh shows "Refresh failed for all N tickers" | Yahoo Finance is unreachable (network, proxy, or rate limiting). Prices stay on screen marked ⚠; press Refresh again later. **details** shows the error per ticker |
| `start.sh` says "Port 8000 is already in use" | The app (or something else) is already running. Use the running copy, stop it, or choose other ports with `APP_PORT` / `FRONTEND_PORT` |
| `node: command not found` in a script or IDE terminal | Node was installed with nvm. Run `source ~/.nvm/nvm.sh` or open a login shell |
