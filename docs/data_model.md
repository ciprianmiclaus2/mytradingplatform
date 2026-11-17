# Data Model

All persisted data lives under `DATA_DIR`. See the [README](../README.md#data-directory) for the folder layout and [architecture.md](architecture.md#persistence) for how files are written.

## Conventions

- **Format:** Parquet with zstd compression, one declared `DatasetSchema` per dataset.
- **File metadata:**
  - `mtp_dataset` holds the dataset name and `mtp_schema_version` its integer version. Both are checked on every read.
  - Keys starting with `x_` carry extra information, e.g. `x_source_fingerprint` for derived data.
- **Types:**
  - Broker quantities and prices (from SnapTrade's decimal strings): `decimal128(28,10)`. Market prices from the provider: `float64`.
  - Timestamps: `timestamp[us, tz=UTC]`.
  - Identifiers: strings.
- **Data schema version:** `metadata/schema_version.json` holds the version of the data directory as a whole. It is currently `1`.

## Datasets

| Dataset | Path | Version | Key | Notes |
|---|---|---|---|---|
| `close_prices` | `market_data/close_prices/YYYYMMDD.parquet` | 1 | `ticker` | Authoritative historical cache. One file per trading date |
| `close_price_coverage` | `market_data/coverage.parquet` | 1 | `ticker, provider, start_date` | Date ranges already fetched |
| `current_prices` | `market_data/current/current.parquet` (plus archives) | 1 | `ticker, timestamp` | Current-price time series |
| `ticker_names` | `market_data/names.parquet` | 1 | `ticker` | Company or fund name per ticker (`ticker`, `name`, `updated_at`), from the latest quote that reported one. Shown when hovering a ticker. Rebuilt by refreshing; not backed up |
| `price_history` | `market_data/history/history.parquet` | 1 | `ticker, trading_date` | Derived from `close_prices`. Rebuildable |
| `portfolios` | `portfolios/portfolios.parquet` | 1 | `id` | Watchlists |
| `broker_accounts` | `brokers/accounts.parquet` | 1 | `id` | Accounts as last listed by SnapTrade. A cache: rebuilt by refreshing, not backed up |
| `broker_positions` | `brokers/positions.parquet` | 1 | (none) | Positions per account at its last refresh. A cache, not backed up |
| `signals` | `strategies/signals.parquet` | 1 | `id` | Signal transitions per strategy instance and ticker, plus one baseline row (`previous_signal == new_signal`) when an instance first evaluates a ticker |

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
| type | string | no | `watchlist`. (Rows of the retired type `positions` are removed on startup, after a backup) |
| tickers | list&lt;string&gt; | no | Tickers in the order they were added |
| favourites | list&lt;string&gt; | no | Always a subset of the portfolio's tickers |
| created_at, updated_at | timestamp[us, UTC] | no | |

### broker_accounts

| Column | Type | Null | Description |
|---|---|---|---|
| id | string | no | SnapTrade account id (UUID) |
| name | string | no | SnapTrade's `display_name`, or the account kind and number |
| number | string | no | Masked account number, e.g. `****8443`. May be empty |
| status | string | yes | `open`, `closed`, `archived` or `unavailable` |
| kind | string | no | `investment`, `deposit`, ... |
| net_value, net_value_currency | float64, string | yes | SnapTrade's `net_value` (informational) |
| listed_at | timestamp[us, UTC] | no | Last time the account list contained this account |
| positions_refreshed_at | timestamp[us, UTC] | yes | Last successful positions refresh by this app |
| data_as_of | timestamp[us, UTC] | yes | SnapTrade's `data_freshness.as_of` at that refresh |

`brokers/status.json` holds `accounts_refreshed_at`, the time the account list was last fetched.

### broker_positions

| Column | Type | Null | Description |
|---|---|---|---|
| account_id | string | no | A `broker_accounts` id. Replaced as a whole when the account is refreshed |
| symbol | string | no | The broker's symbol (OCC symbol for options) |
| ticker | string | yes | Market data ticker, when the instrument maps to one |
| description | string | yes | |
| kind | string | no | SnapTrade instrument kind: `stock`, `etf`, `option`, `crypto`, `cash`, ... |
| units | decimal128(28,10) | no | Negative for short positions |
| price | decimal128(28,10) | yes | Broker price per unit at the refresh |
| cost_basis | decimal128(28,10) | yes | Average purchase price per unit (SnapTrade's `cost_basis`) |
| multiplier | decimal128(28,10) | no | Contract multiplier (options); 1 otherwise |
| currency | string | yes | ISO 4217 currency of `price` and `cost_basis` |
| cash_equivalent | bool | no | SnapTrade's `cash_equivalent` |

### SnapTrade credentials

`config/snaptrade.json` (not a dataset): a JSON object with `client_id`, `consumer_key`, `user_id` and `user_secret`. The user fields are `null` for a Personal API key. The folder is mode 0700 and the file 0600 (repaired on read if wider). It is never included in backups and never returned by the API.

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
