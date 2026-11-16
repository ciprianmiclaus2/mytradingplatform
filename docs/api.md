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
- A `positions` portfolio's `tickers` are the tickers of its open positions and are read-only (positions arrive in Phase 5).

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
