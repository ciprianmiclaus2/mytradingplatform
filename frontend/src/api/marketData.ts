import type { MarketDataStatus, RefreshResult, TickerSearchResult } from '../types/api'
import { apiRequest } from './client'

/** A refresh asks the provider for every ticker; allow well over the backend's provider timeout. */
const REFRESH_TIMEOUT_MS = 120_000

export function searchTickers(query: string, signal?: AbortSignal): Promise<TickerSearchResult[]> {
  return apiRequest<TickerSearchResult[]>(`/market-data/search?q=${encodeURIComponent(query)}&limit=8`, { signal })
}

/** Refresh every portfolio's tickers, plus tickers only the dashboard knows about. */
export function refreshMarketData(extraTickers: string[]): Promise<RefreshResult> {
  return apiRequest<RefreshResult>('/market-data/refresh', {
    method: 'POST',
    body: { extra_tickers: extraTickers },
    timeoutMs: REFRESH_TIMEOUT_MS,
  })
}

export function getMarketDataStatus(signal?: AbortSignal): Promise<MarketDataStatus> {
  return apiRequest<MarketDataStatus>('/market-data/status', { signal })
}
