import type { TickerSearchResult } from '../types/api'
import { apiRequest } from './client'

export function searchTickers(query: string, signal?: AbortSignal): Promise<TickerSearchResult[]> {
  return apiRequest<TickerSearchResult[]>(`/market-data/search?q=${encodeURIComponent(query)}&limit=8`, { signal })
}
