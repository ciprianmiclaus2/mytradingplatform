# My Trading Platform

A locally hosted, single-user trading dashboard. It monitors a portfolio of ticker symbols, tracks positions and cash, and runs configurable trading strategies such as mean reversion. All data is stored in local Parquet files. It never places real trades.

> **Status:** Phases 1–2 (project foundation, persistence foundation) are complete. See
> [docs/MyTradingPlatform_v1_ImplementationPlan.md](docs/MyTradingPlatform_v1_ImplementationPlan.md)
> for the full V1 plan.

## Architecture overview

```text
Browser (React + Vite, :5173)
   │  /api/*  (proxied by Vite in development)
   ▼
FastAPI backend (:8000)
   ├── api/           HTTP routes only, no business logic
   ├── services       portfolio, positions, transactions, market data, strategies
   └── persistence/   Parquet files + DuckDB queries (DATA_DIR)
```

The backend is a modular monolith running as a single process. The frontend calls it only through the API.

## Technology stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic, pydantic-settings, Uvicorn |
| Data | Pandas, PyArrow (Parquet), DuckDB, yfinance |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4 |
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

Output from the two servers is prefixed `[backend]` and `[frontend]`. **Ctrl+C stops both.** Backend variables pass straight through, for example `APP_PORT=8001 DATA_DIR=/tmp/mtp ./start.sh`. The frontend proxy follows `APP_PORT` automatically.

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
| `CORS_ORIGINS` | the Vite dev origins | JSON list of allowed browser origins |
| `LOG_LEVEL` | `INFO` | Log level. Logs are written to stderr as JSON lines |

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
│   ├── close_prices/   one Parquet file per trading date
│   ├── current/        current-price time series (rotated)
│   └── history/        rebuildable consolidated history
├── portfolios/
├── positions/
├── transactions/
├── strategies/
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
```

A backup is a timestamped folder under `backups/` with a checksum manifest. It covers portfolios, positions, transactions, strategies and metadata, but not market data, which can be downloaded again. Restoring always backs up the current state first.

The data directory is never served over HTTP.

## Testing

```bash
cd backend && .venv/bin/python -m pytest
cd frontend && npm test            # Vitest
cd frontend && npm run build       # type-check + production build
cd frontend && npm run lint
```

Automated tests never call Yahoo Finance. The market data tests use mocked providers.

## Troubleshooting

| Symptom | Fix |
|---|---|
| UI shows "The backend is unavailable." | Start the backend, and check that `VITE_BACKEND_URL` matches `APP_HOST`/`APP_PORT` |
| Backend exits with "schema version … migration is required" | `DATA_DIR` holds data from an incompatible version. Point `DATA_DIR` elsewhere, or migrate the data |
| Backend exits with "… is incompatible" or "… cannot be read" | A data file has the wrong schema or is damaged. Restore it with `scripts/backup_data.py restore <name>`, or rebuild derived data with `scripts/rebuild_derived.py` |
| API returns `persistence_lock_timeout` | A maintenance script is holding the write lock. Wait for it to finish |
| Backend exits with "Cannot create data directory" | `DATA_DIR` isn't writable, or part of its path is a file |
| Browser shows a CORS error when `VITE_API_BASE_URL` is an absolute URL | Add the frontend origin to `CORS_ORIGINS` |
| `node: command not found` in a script or IDE terminal | Node was installed with nvm. Run `source ~/.nvm/nvm.sh` or open a login shell |
