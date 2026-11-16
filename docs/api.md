# API

_To be completed as the implementation progresses. See the README and the V1 implementation plan for the current state._

## Implemented endpoints

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
| `/api/market-data/refresh` | POST | Fetches the latest prices, once per unique ticker. Body: `{"tickers": [...]}` |
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

In Phase 10, refresh will also collect tickers from portfolios, positions and strategy panes. For now the caller lists the tickers.

## Portfolios

A portfolio is a named watchlist of type `watchlist` or `positions`.

- On first startup, "Main Portfolio" (watchlist) and "Main Positions" are created.
- A `positions` portfolio's `tickers` are the tickers of its open positions and are read-only.

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
| `400` | The portfolio is a positions portfolio |

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

## Positions

Positions are informational records. There is no ledger and no cash. Each one belongs to a `positions` portfolio.

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/portfolios/{id}/positions?status=all\|open\|closed` | GET | Positions with calculated metrics, plus per-currency `totals`. The filter defaults to `all`; totals always cover the whole portfolio |
| `/api/portfolios/{id}/positions` | POST | Create position. Returns 201 |
| `/api/positions/{id}` | GET | Retrieve position |
| `/api/positions/{id}` | PUT | Edit in place. Only the fields sent are changed |
| `/api/positions/{id}/close` | POST | Close the whole position: `{"exit_price"?, "exit_date"?}`. The body is optional |
| `/api/positions/{id}` | DELETE | Delete an open or closed position, after taking a backup. Returns 204 |

### Creating a position

Request body: `{"ticker", "quantity", "entry_price"?, "entry_date"?, "notes"?}`.

- **Ticker:** checked like a watchlist ticker. An unknown ticker gets `422 invalid_ticker`; if the provider is down and no price is stored, the response is `502`.
- **Currency:** taken from the quote, and never converted. Prices are in the quote's units, e.g. pence for `GBp`.
- **Defaults:** `entry_price` defaults to the latest available price, and `entry_date` to today (UTC).
- **One open position per ticker:** a second open position for the same ticker in the same portfolio gets `409`. Edit the quantity and entry price instead. Once a position is closed, its ticker can be opened again.

### Numbers and dates

- **Numbers:** `quantity` and prices must be greater than 0, with at most 8 decimal places and 12 integer digits. They can be sent as JSON numbers or as strings.
- **Dates:** can't be in the future, and `exit_date` can't be before `entry_date`.

### Editing a position

- **Open positions:** `quantity`, `entry_price`, `entry_date` (send `null` to clear it) and `notes`.
- **Closed positions:** `exit_price`, `exit_date` and `notes`.
- Changing any other field returns `400`.

### Closing a position

- `exit_price` defaults to the latest available price. If there's none, the response is `400`, asking for one.
- `exit_date` defaults to today (UTC).
- Closing an already closed position returns `409`.
- Closing or deleting a position also removes its ticker from the portfolio's favourites.

### Position (response)

All values are calculated in the backend.

```json
{"id": "...", "portfolio_id": "...", "ticker": "AAPL", "currency": "USD", "status": "OPEN",
 "quantity": 20, "entry_price": 210, "entry_date": "2026-01-05", "notes": "", "cost_basis": 4200,
 "current_price": 215.42, "previous_close": 218.10, "price_timestamp": "...",
 "market_value": 4308.4, "unrealised_pnl": 108.4, "unrealised_pnl_pct": 2.58,
 "daily_change": -2.68, "daily_change_pct": -1.23, "daily_pnl": -53.6, "stale": false,
 "exit_price": null, "exit_date": null, "realised_pnl": null, "realised_pnl_pct": null,
 "created_at": "...", "updated_at": "..."}
```

- **Open positions** fill the market fields. These are `null` when there is no stored price in the position's currency.
- **Closed positions** fill `exit_price`, `exit_date`, `realised_pnl` and `realised_pnl_pct`.

### Totals (one per currency, never combined)

```json
{"currency": "USD", "open_positions": 1, "closed_positions": 1, "market_value": 2627.6, "cost_basis": 2627.6,
 "unrealised_pnl": 0.0, "unrealised_pnl_pct": 0.0, "daily_pnl": 8.2, "realised_pnl": 500.0, "incomplete": false}
```

`incomplete` is `true` when some open positions have no current price or previous close. In that case the market totals cover only the positions that have prices, while `cost_basis` always covers all open positions.

## Strategies

Strategies are generic: adding one needs no new endpoint.

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/strategies` | GET | Available strategies with their schemas |
| `/api/strategies/{name}/schema` | GET | Configuration schema and output columns |
| `/api/strategies/{name}/run` | POST | Run a strategy on a list of tickers |
| `/api/strategies/signals?instance_id=&strategy=&ticker=&limit=50&offset=0` | GET | Recorded signal transitions, newest first. `limit` is 1–500 |

### Schema

```json
{"name": "mean_reversion", "title": "...", "description": "...",
 "parameters": [{"name": "lookback_days", "type": "integer", "title": "Lookback (days)", "description": "...",
                 "default": 20, "minimum": 2, "maximum": null, "choices": null}],
 "outputs": [{"name": "z_score", "title": "Z-Score", "format": "number", "description": ""}]}
```

- **Parameter `type`:** `integer`, `number`, `string` or `boolean`.
- **Output `format`:** `price`, `number`, `percent` or `text`.
- The frontend builds the configuration form from `parameters`, and the result columns from `outputs`.

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
| `is_new_signal` | The signal state changed in this run |
| `signal_changed_at` | When the current state began |
| `previous_signal` | The state before the current one |

### Signal event

```json
{"id": "...", "instance_id": "pane-123", "strategy": "mean_reversion", "ticker": "AAPL",
 "previous_signal": null, "new_signal": "BUY", "metric_name": "z_score", "metric_value": -2.1,
 "current_price": 210.0, "timestamp": "..."}
```

The response is paginated: `{"items": [...], "total": 12, "limit": 50, "offset": 0}`.
