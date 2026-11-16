import { useCallback, useEffect, useRef, useState } from 'react'
import { getMarketDataStatus, refreshMarketData } from '../api/marketData'
import { notifyDataChanged } from '../hooks/dataVersion'
import { errorMessage } from '../hooks/useApiData'
import type { RefreshResult } from '../types/api'

export interface MarketRefreshState {
  running: boolean
  /** Result of the most recent refresh (from this session, or the backend's record). */
  lastResult: RefreshResult | null
  lastSuccessAt: string | null
  /** The refresh request itself failed (backend unreachable, refresh already running, ...). */
  error: string | null
}

/**
 * The global Refresh: one backend request refreshes every ticker once, then
 * every pane reloads (portfolios, positions, and strategies, which re-run).
 */
export function useMarketRefresh(getExtraTickers: () => string[]) {
  const [state, setState] = useState<MarketRefreshState>({ running: false, lastResult: null, lastSuccessAt: null, error: null })
  const running = useRef(false)

  // Show the last refresh recorded by the backend when the app opens.
  useEffect(() => {
    const controller = new AbortController()
    getMarketDataStatus(controller.signal)
      .then((status) =>
        setState((s) => (s.lastResult || s.running ? s : { ...s, lastResult: status.last_refresh, lastSuccessAt: status.last_successful_refresh_at })),
      )
      .catch(() => {}) // Status is informational; the health indicator reports outages.
    return () => controller.abort()
  }, [])

  const refresh = useCallback(async () => {
    if (running.current) return
    running.current = true
    setState((s) => ({ ...s, running: true, error: null }))
    try {
      const result = await refreshMarketData(getExtraTickers())
      setState((s) => ({
        running: false,
        error: null,
        lastResult: result,
        lastSuccessAt: result.tickers_updated > 0 ? result.completed_at : s.lastSuccessAt,
      }))
      // Even a partial or failed refresh changes stale markers, so reload every pane.
      notifyDataChanged()
    } catch (err) {
      setState((s) => ({ ...s, running: false, error: errorMessage(err) }))
    } finally {
      running.current = false
    }
  }, [getExtraTickers])

  return { ...state, refresh }
}
