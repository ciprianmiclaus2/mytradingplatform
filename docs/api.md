# API

Reference for the V1 API. Interactive OpenAPI docs are served at `/api/docs` while the backend runs.

## General

All endpoints use the `/api` prefix. Interactive OpenAPI docs: `/api/docs`.

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/health` | GET | Backend status, version, environment, data schema version |

### Error format

Every error response has this shape:

```json
{"error": {"code": "validation_error", "message": "Request validation failed", "details": [...]}}
```

Unexpected errors return `500` with `code: "internal_error"`. Stack traces are logged on the backend only.

## Market data

These endpoints never fabricate prices. A ticker with no cached price is listed under `missing`, and a ticker whose most recent refresh failed keeps its last valid price with `stale: true`.

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/market-data/search?q=&limit=` | GET | Ticker search, normalised. Futures and options are excluded. Returns 502 if the provider is unavailable |
| `/api/market-data/prices?tickers=AAPL,MSFT` | GET | Latest cached prices. Never calls the provider |
| `/api/market-data/history?ticker=&start=&end=` | GET | Completed daily closes. Missing ranges are fetched once and then served from cache |
| `/api/market-data/refresh` | POST | Global refresh: every portfolio's tickers, the tickers held in broker accounts (as of their last SnapTrade refresh) plus `extra_tickers`, once per unique ticker. Does not call SnapTrade. Body (optional): `{"extra_tickers": [...]}`, at most 200. Returns 409 `refresh_in_progress` if a refresh is already running |
| `/api/market-data/status` | GET | Provider, last refresh result, last successful refresh time |

### Latest price

`price` is the latest available price. It is **not** necessarily live: `delayed` is `true` when the provider reports a delay, and `null` when the delay is unknown. A price is never labelled real-time. `timestamp` is when the provider says the quote was made; `fetched_at` is when the backend retrieved it.

```json
{
  "ticker": "AAPL", "price": 356.27, "previous_close": 354.88, "currency": "USD",
  "timestamp": "2026-11-13T21:00:01Z", "trading_date": "2026-11-13", "provider": "yfinance",
  "delayed": true, "fetched_at": "2026-11-16T13:57:48Z",
  "daily_change": 1.39, "daily_change_pct": 0.39, "stale": false, "last_error": null
}
```

### History

`status` is one of:

- `OK`
- `NO_DATA`: the provider has no data for the range.
- `ERROR`: the provider request failed. `error` says why, and any bars already cached are still returned.

The current trading session is never included: bars stop at the last UTC date before today. Ranges are limited to 10 years.

### Refresh result

`status` is one of:

- `completed`: every ticker updated.
- `partial`: some tickers updated and some failed.
- `failed`: no ticker updated.

Each failed ticker is listed in `errors` with `code` set to `no_data`, `provider_error` or `invalid_price`.

```json
{"status": "partial", "started_at": "...", "completed_at": "...", "tickers_requested": 3,
 "tickers_updated": 2, "tickers_failed": 1,
 "errors": [{"ticker": "ZZZZ", "code": "no_data", "message": "No quote available for ZZZZ"}]}
```

The dashboard sends the tickers of strategy panes that use a typed ticker list as `extra_tickers`, because those panes are stored in the browser. Unknown body fields are rejected with 422.

## Portfolios

A portfolio is a named watchlist (type `watchlist`, the only type).

- On first startup, "Main Portfolio" is created.
- Positions lists (type `positions`) were replaced by broker accounts. Old ones are removed on startup, after a backup is taken; creating one returns 422.

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/portfolios?type=` | GET | List portfolios, optionally by type |
| `/api/portfolios` | POST | Create: `{"name", "description"?, "type"?}`. Type defaults to `watchlist` |
| `/api/portfolios/{id}` | GET | Retrieve |
| `/api/portfolios/{id}` | PUT | Update `name` and/or `description`. The type can't be changed |
| `/api/portfolios/{id}` | DELETE | Delete, after taking a backup. Returns 204. The last remaining portfolio can't be deleted (409) |
| `/api/portfolios/{id}/tickers` | POST | Add ticker to a watchlist: `{"ticker": "AAPL"}`. Returns 201 |
| `/api/portfolios/{id}/tickers/{ticker}` | DELETE | Remove a ticker from a watchlist. Also removes it from favourites |
| `/api/portfolios/{id}/favourites/{ticker}` | PUT | Mark favourite. The ticker must already be in the portfolio. Safe to repeat |
| `/api/portfolios/{id}/favourites/{ticker}` | DELETE | Unmark favourite. Safe to repeat |
| `/api/portfolios/{id}/quotes` | GET | Rows for the Portfolio pane, from cached prices |

### Adding a ticker

Adding a ticker checks it against market data:

1. If a price is already cached, it's used and the provider isn't called.
2. Otherwise a quote is fetched and stored.

| Response | Meaning |
|---|---|
| `422 invalid_ticker` | The provider has no data for the ticker |
| `502 market_data_provider_unavailable` | The provider is unreachable and no price is cached. Try again |
| `409 conflict` | The ticker is already in the portfolio |

### Errors

Other errors:

| Response | Meaning |
|---|---|
| `409 conflict` | Duplicate name (case-insensitive), or deleting the last portfolio |
| `404 not_found` | Unknown portfolio |
| `422 validation_error` | Invalid name (empty, or over 100 characters) or invalid ticker format |

### Quote row

`null` values mean no price is cached yet. `stale` means the last refresh of that ticker failed.

```json
{"ticker": "AAPL", "favourite": true, "price": 356.27, "currency": "USD", "previous_close": 354.88,
 "daily_change": 1.39, "daily_change_pct": 0.39, "timestamp": "2026-11-13T21:00:01Z",
 "delayed": true, "stale": false, "last_error": null}
```

## Broker accounts (SnapTrade)

Positions come from brokerage accounts through SnapTrade, read-only. The backend calls SnapTrade only for the settings and refresh endpoints; everything else reads the cache of the last refresh (`brokers/` in the data folder).

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/brokers/snaptrade/settings` | GET | Whether SnapTrade is set up: `{configured, personal, client_id, user_id, consumer_key_hint, user_secret_hint}`. `personal` is `true` for a Personal API key (no user). Secrets are never returned, only their last 4 characters (empty for values of 8 characters or fewer) |
| `/api/brokers/snaptrade/settings` | PUT | `{"client_id", "consumer_key", "user_id"?, "user_secret"?}`. Personal API key: leave the user fields out (or blank); requests then carry no user. Commercial key: both user fields; one without the other is `422`. Lists the accounts with these credentials; if SnapTrade accepts them, saves them, replaces the cache and loads every account's positions. Returns a refresh result. `422 snaptrade_credentials_rejected` (nothing saved) if SnapTrade rejects them |
| `/api/brokers/snaptrade/settings` | DELETE | Delete the credentials and the cached accounts and positions. Returns 204. Nothing changes at SnapTrade |
| `/api/brokers/accounts` | GET | `{configured, accounts, accounts_refreshed_at}` from the cache. Each account includes `tickers`: the market data tickers it held at its last refresh |
| `/api/brokers/refresh` | POST | List the accounts (`GET /accounts/all` at SnapTrade), then fetch each account's positions (`GET /accounts/{id}/positions/all`). An account whose positions fail keeps its previous positions and is listed in `errors` |
| `/api/brokers/accounts/{id}/positions` | GET | The account's positions from the cache, valued with the latest market prices, plus per-currency `totals` |
| `/api/brokers/accounts/{id}/refresh` | POST | The pane's refresh: list the accounts, then fetch this account's positions. Returns the same body as the GET |

### Errors

| Response | Meaning |
|---|---|
| `409 snaptrade_not_configured` | SnapTrade is not set up |
| `409 broker_refresh_in_progress` | Another SnapTrade refresh or settings change is running |
| `422 snaptrade_credentials_rejected` | Setup only: SnapTrade rejected the credentials |
| `502 snaptrade_auth_failed` | SnapTrade rejected the stored credentials (e.g. a deleted user or rotated key) |
| `429 snaptrade_rate_limited` | SnapTrade's rate limit; the message says when to try again (from `Retry-After`) |
| `502 snaptrade_error` | SnapTrade unreachable, timed out, returned an error, or the brokerage connection is disabled (reconnect it at SnapTrade) |
| `404 not_found` | The account is not (or no longer) listed |

Accounts that SnapTrade no longer lists are removed from the cache, with their positions, at the next refresh.

### Account

```json
{"id": "917c8734-...", "name": "Brokerage", "number": "****1234", "status": "open", "kind": "investment",
 "net_value": 15363.23, "net_value_currency": "USD", "listed_at": "...",
 "positions_refreshed_at": "2026-11-16T15:00:00Z", "data_as_of": "2026-11-16T14:30:00Z", "tickers": ["AAPL", "VOD.L"]}
```

`positions_refreshed_at` is when this app last fetched the positions; `data_as_of` is SnapTrade's `data_freshness.as_of`, the time SnapTrade fetched them from the broker.

### Position (response)

All values are calculated in the backend, with decimal arithmetic.

```json
{"symbol": "AAPL", "ticker": "AAPL", "description": "Apple Inc", "kind": "stock", "currency": "USD",
 "quantity": 10, "average_cost": 90.5, "cost_basis": 905, "current_price": 100, "price_source": "market",
 "price_timestamp": "...", "previous_close": 98, "market_value": 1000, "daily_change": 2, "daily_change_pct": 2.04,
 "daily_pnl": 20, "unrealised_pnl": 95, "unrealised_pnl_pct": 10.5, "stale": false}
```

- **`symbol`** is the broker's symbol; **`ticker`** the market data ticker it maps to, or `null` (options, cash, unknown exchanges). Listed stocks, ETFs and funds map by exchange: `BRK.B` on NYSE is `BRK-B`, `VUSA` on the LSE is `VUSA.L`, `SHOP` on the TSX is `SHOP.TO`. Crypto maps to `BTC-USD` style tickers.
- **`price_source`:** `market` when a cached market price in the position's currency exists (a quote in pence, `GBp`, is converted for a `GBP` position); otherwise `broker`, the broker's price at the last refresh, with `price_timestamp` = `data_as_of`. Daily change and daily P&L need a market price.
- **`average_cost`** is SnapTrade's `cost_basis` (average purchase price per unit). `cost_basis` here is the total: quantity × average cost × multiplier. Options use their contract multiplier.
- Short positions have a negative quantity; their P&L % is relative to the absolute cost.

### Totals (one per currency, never combined)

```json
{"currency": "USD", "positions": 2, "market_value": 1550, "cost_basis": 1305, "unrealised_pnl": 245,
 "unrealised_pnl_pct": 18.77, "daily_pnl": 20, "incomplete": true}
```

`incomplete` is `true` when some positions have no price, cost or daily change; those are left out of the affected totals. Positions without a currency are not totalled.

## Strategies

Strategies are generic: adding one needs no new endpoint.

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/strategies` | GET | Available strategies with their schemas, sorted by title |
| `/api/strategies/{name}/schema` | GET | Configuration schema and output columns |
| `/api/strategies/{name}/run` | POST | Run a strategy on a list of tickers |
| `/api/strategies/signals?instance_id=&strategy=&ticker=&limit=50&offset=0` | GET | Recorded signal transitions, newest first (baselines excluded). `limit` is 1–500 |

### Schema

```json
{"name": "mean_reversion", "title": "...", "description": "...", "explanation": "...",
 "parameters": [{"name": "lookback_days", "type": "integer", "title": "Lookback (days)", "description": "...",
                 "default": 20, "minimum": 2, "maximum": null, "choices": null}],
 "outputs": [{"name": "z_score", "title": "Z-Score", "format": "number", "description": ""}]}
```

- **Parameter `type`:** `integer`, `number`, `string` or `boolean`.
- **Output `format`:** `price`, `number`, `percent`, `integer` or `text`.
- The frontend builds the configuration form from `parameters`, and the result columns from `outputs`.
- `explanation` is the user-facing description of the strategy: plain text with blank-line-separated blocks, `## ` headings and `- ` bullets.
- Strategies: `mean_reversion`, `rsi` (parameters `period`, `oversold`, `overbought`; outputs `rsi`, `average_gain`, `average_loss`), `ma_crossover` (parameters `fast_period`, `slow_period`, `average_type` `SMA`/`EMA`, `signal_mode` `Recent cross`/`Trend`, `recent_sessions`, `use_current_price`; outputs `fast_ma`, `slow_ma`, `spread_pct`, `sessions_since_cross`), `bollinger` (parameters `period`, `width`, `signal_mode` `Mean reversion`/`Breakout`, `use_current_price`; outputs `lower_band`, `middle_band`, `upper_band`, `percent_b`, `bandwidth`, `width_rank`) and `macd` (parameters `fast_period`, `slow_period`, `signal_period`, `signal_mode` `Recent cross`/`Trend`, `recent_sessions`, `use_current_price`; outputs `macd`, `signal_line`, `histogram`, `histogram_pct`, `sessions_since_cross`).

### Run

Request body:

```json
{"tickers": ["AAPL", "MSFT"], "config": {"lookback_days": 20}, "instance_id": "pane-123"}
```

- **`config`:** missing parameters take their defaults. Unknown parameters, wrong types, values out of range, and cross-parameter rule violations return `422 invalid_strategy_config`, with `details` mapping each parameter to its message.
- **`instance_id`** is optional: 1–64 characters, using letters, digits, `_` or `-`. It is typically the dashboard pane id. When it's given, signal transitions are recorded and the result rows carry signal-history fields.
- **Data used:** the run uses the cached current prices; refresh first to update them. History is the completed sessions **before the session of the current quote**, so the current session is never included. Missing history is downloaded once and cached.
- **Errors:** an unknown strategy returns `404`. A strategy that crashes returns `500 strategy_failed`, with no stack trace.

Response:

```json
{"strategy": "mean_reversion", "instance_id": "pane-123", "config": {"lookback_days": 20, "...": "..."},
 "calculated_at": "...",
 "results": [{"ticker": "AAPL", "status": "OK", "signal": "BUY", "message": null,
              "current_price": 215.42, "currency": "USD", "daily_change": -2.68, "daily_change_pct": -1.23,
              "price_timestamp": "...", "stale": false,
              "metrics": {"mean": 220.1, "standard_deviation": 2.5, "z_score": -1.87},
              "previous_signal": null, "signal_changed_at": "...", "is_new_signal": true}]}
```

Results come back in request order, with duplicate tickers removed.

### `status` values

| Status | Meaning |
|---|---|
| `OK` | The calculation succeeded |
| `NO_PRICE` | No cached current price for the ticker |
| `INSUFFICIENT_DATA` | Not enough history |
| `INVALID_CALCULATION` | The calculation can't produce a meaningful value (e.g. zero standard deviation) |
| `DATA_ERROR` | History couldn't be retrieved |

`signal` is `BUY`, `SELL` or `null` (no signal). It is a current condition, not an instruction to trade, and it is always `null` unless `status` is `OK`.

### Signal history fields

These are filled only for `OK` rows of runs that had an `instance_id`:

| Field | Meaning |
|---|---|
| `is_new_signal` | The signal state changed in this run. Never true on the first run of an instance for a ticker: that run only records the starting state |
| `signal_changed_at` | When the current state began; null if it was already in place when the instance first saw the ticker |
| `previous_signal` | The state before the current one |

### Signal event

```json
{"id": "...", "instance_id": "pane-123", "strategy": "mean_reversion", "ticker": "AAPL",
 "previous_signal": null, "new_signal": "BUY", "metric_name": "z_score", "metric_value": -2.1,
 "current_price": 210.0, "timestamp": "..."}
```

The response is paginated: `{"items": [...], "total": 12, "limit": 50, "offset": 0}`.

### Mean Reversion (`mean_reversion`)

| Parameter | Type | Default | Rules |
|---|---|---|---|
| `lookback_days` | integer | 20 | 2–500. Number of previous completed sessions |
| `buy_threshold` | number | -2.0 | Must be lower than `sell_threshold` |
| `sell_threshold` | number | 2.0 | |

The `metrics` are:

- `mean` and `standard_deviation`: the population standard deviation of the previous `lookback_days` regular closes. The current session is excluded.
- `z_score` = (current price − mean) / standard deviation.

The signal is `BUY` when Z ≤ `buy_threshold`, `SELL` when Z ≥ `sell_threshold`, and `null` otherwise.

| Status | When |
|---|---|
| `INSUFFICIENT_DATA` | Fewer than `lookback_days` sessions are available. The message says how many there are |
| `INVALID_CALCULATION` | The standard deviation is zero, or the history and the quote are in different currencies. No signal is produced |

Signal transitions record `z_score` as their metric.
