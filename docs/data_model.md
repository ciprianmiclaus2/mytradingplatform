# Data Model

All persisted data lives under `DATA_DIR`. See the [README](../README.md#data-directory) for the folder layout and [architecture.md](architecture.md#persistence) for how files are written.

## Conventions

- **Format:** Parquet with zstd compression, one declared `DatasetSchema` per dataset.
- **File metadata:**
  - `mtp_dataset` holds the dataset name and `mtp_schema_version` its integer version. Both are checked on every read.
  - Keys starting with `x_` carry extra information, e.g. `x_source_fingerprint` for derived data.
- **Types:**
  - User-entered money and quantities: `decimal128(20,8)` (positions). Market prices from the provider: `float64`.
  - Timestamps: `timestamp[us, tz=UTC]`.
  - Identifiers: strings.
- **Data schema version:** `metadata/schema_version.json` holds the version of the data directory as a whole. It is currently `1`.

## Datasets

| Dataset | Path | Version | Key | Notes |
|---|---|---|---|---|
| `close_prices` | `market_data/close_prices/YYYYMMDD.parquet` | 1 | `ticker` | Authoritative historical cache. One file per trading date |
| `close_price_coverage` | `market_data/coverage.parquet` | 1 | `ticker, provider, start_date` | Date ranges already fetched |
| `current_prices` | `market_data/current/current.parquet` (plus archives) | 1 | `ticker, timestamp` | Current-price time series |
| `price_history` | `market_data/history/history.parquet` | 1 | `ticker, trading_date` | Derived from `close_prices`. Rebuildable |
| `portfolios` | `portfolios/portfolios.parquet` | 1 | `id` | Watchlists and positions portfolios |
| `positions` | `positions/positions.parquet` | 1 | `id` | Open and closed positions |
| `signals` | `strategies/signals.parquet` | 1 | `id` | Signal transitions per strategy instance and ticker |

### close_prices / price_history

| Column | Type | Null | Description |
|---|---|---|---|
| ticker | string | no | Upper-case symbol |
| trading_date | date32 | no | Session date in the exchange's local time |
| close | float64 | no | Regular close. Split-adjusted by the provider, not dividend-adjusted. Used for statistics |
| adjusted_close | float64 | yes | Provider's adjusted close. Stored for reference only |
| currency | string | no | As reported by the provider. Note that it can be e.g. `GBp` (pence) |
| provider | string | no | Provider name |
| fetched_at | timestamp[us, UTC] | no | When the data was retrieved |

### close_price_coverage

| Column | Type | Null | Description |
|---|---|---|---|
| ticker | string | no | Symbol |
| provider | string | no | Provider the range was fetched from |
| start_date, end_date | date32 | no | Inclusive range that was fetched successfully. Adjacent ranges are merged |
| fetched_at | timestamp[us, UTC] | no | Time of the last merge |

For a given ticker and date:

| Situation | Meaning |
|---|---|
| Close row exists | Data available |
| Inside a covered range, no close row | No data from the provider (weekend, holiday, not yet listed) |
| Outside every covered range | Not fetched yet |

A failed provider request is never recorded as covered. Close files are written before coverage, so coverage never claims data that wasn't saved. Dates on or after today's UTC date are never cached, so a partial daily bar is never stored.

### current_prices

| Column | Type | Null | Description |
|---|---|---|---|
| timestamp | timestamp[us, UTC] | no | Quote time as reported by the provider |
| ticker | string | no | Symbol |
| price | float64 | no | Latest available price |
| currency | string | no | |
| provider | string | no | |
| previous_close | float64 | yes | Previous regular session close. Used for daily change. *Not in the plan; added* |
| trading_date | date32 | yes | Exchange-local session date of the quote. *Not in the plan; added* |
| delayed | bool | yes | `true` if the provider reports a delay, otherwise null. Never `false`. *Not in the plan; added* |
| fetched_at | timestamp[us, UTC] | no | When the backend retrieved it. *Not in the plan; added* |

- **Duplicates:** a quote with the same `(ticker, timestamp)` as a stored one (e.g. while the market is closed) is not stored again.
- **Rotation:** when the active file reaches `CURRENT_PRICE_ARCHIVE_THRESHOLD` rows, it is renamed to `current.YYYYMMDDHHMMSS.parquet`. A new active file is started, holding the latest row per ticker, so the latest-price view only needs to read the active file.

### market_data/refresh_status.json

This file stores:

- the last refresh result;
- `last_successful_refresh_at`;
- per-ticker `last_attempt_at`, `last_success_at` and `last_error`.

A price is reported `stale` when its ticker's most recent refresh attempt failed.

### portfolios

| Column | Type | Null | Description |
|---|---|---|---|
| id | string | no | UUID (hex) |
| name | string | no | 1–100 characters. Unique regardless of case. Runs of spaces are collapsed to one |
| description | string | no | Up to 500 characters. May be empty |
| type | string | no | `watchlist` or `positions`. Never changes |
| tickers | list&lt;string&gt; | no | Watchlists: tickers in the order they were added. Positions portfolios: always empty, because their tickers come from open positions |
| favourites | list&lt;string&gt; | no | Always a subset of the portfolio's tickers |
| created_at, updated_at | timestamp[us, UTC] | no | |

### positions

| Column | Type | Null | Description |
|---|---|---|---|
| id | string | no | UUID (hex) |
| portfolio_id | string | no | A `positions` portfolio. Its positions are deleted along with it |
| ticker | string | no | At most one `OPEN` row per (portfolio_id, ticker) |
| currency | string | no | Quote currency when the position was created. Never converted |
| quantity | decimal128(20,8) | no | Greater than 0 |
| entry_price | decimal128(20,8) | no | Greater than 0, in the quote's units |
| entry_date | date32 | yes | Informational. Not in the future |
| status | string | no | `OPEN` or `CLOSED` |
| exit_price | decimal128(20,8) | yes | Set when closed. Greater than 0 |
| exit_date | date32 | yes | Set when closed. On or after `entry_date`, and not in the future |
| notes | string | no | Up to 1000 characters |
| created_at, updated_at | timestamp[us, UTC] | no | |

### signals

Only **changes** of signal state are recorded. The current state of a (instance_id, ticker) series is the `new_signal` of its latest event. A series with no events is in the "no signal" state.

| Column | Type | Null | Description |
|---|---|---|---|
| id | string | no | UUID (hex) |
| instance_id | string | no | Strategy instance, e.g. the dashboard pane id |
| strategy | string | no | Strategy name |
| ticker | string | no | |
| previous_signal | string | yes | `BUY`, `SELL`, or null for no signal |
| new_signal | string | yes | `BUY`, `SELL`, or null for no signal |
| metric_name | string | yes | The strategy's main metric, e.g. `z_score` |
| metric_value | float64 | yes | That metric's value at the transition |
| current_price | float64 | yes | Price at the transition |
| timestamp | timestamp[us, UTC] | no | When the run that produced the transition started |
