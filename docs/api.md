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
