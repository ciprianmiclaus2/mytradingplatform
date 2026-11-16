import { useEffect, useRef, useState } from 'react'
import type { MarketRefreshState } from '../refresh/useMarketRefresh'
import { formatTime } from '../utils/format'

interface Props extends MarketRefreshState {
  onRefresh: () => void
}

/** Global Refresh button with the outcome of the last refresh. */
export function RefreshControl({ running, lastResult, lastSuccessAt, error, onRefresh }: Props) {
  const [showDetails, setShowDetails] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!showDetails) return
    const close = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setShowDetails(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [showDetails])

  let summary: React.ReactNode = null
  if (running) {
    summary = <span className="text-slate-500">Refreshing market data…</span>
  } else if (error) {
    summary = <span className="text-red-600">Refresh failed: {error}</span>
  } else if (lastResult) {
    const { status, tickers_requested: total, tickers_failed: failed } = lastResult
    const tone = status === 'completed' ? 'text-emerald-700' : status === 'partial' ? 'text-amber-700' : 'text-red-600'
    const text =
      status === 'completed'
        ? `Updated ${total} ticker${total === 1 ? '' : 's'}`
        : status === 'partial'
          ? `${failed} of ${total} tickers failed`
          : `Refresh failed for all ${total} tickers`
    summary = (
      <span className={tone}>
        {text}
        {failed > 0 && (
          <button type="button" onClick={() => setShowDetails((v) => !v)} aria-expanded={showDetails} className="ml-1 underline">
            details
          </button>
        )}
      </span>
    )
  }

  return (
    <div ref={rootRef} className="relative flex items-center gap-3 text-sm">
      <button
        type="button"
        onClick={onRefresh}
        disabled={running}
        aria-busy={running}
        className="inline-flex items-center gap-1.5 rounded bg-slate-800 px-3 py-1.5 text-sm text-white hover:bg-slate-900 disabled:cursor-wait disabled:opacity-70"
      >
        <span aria-hidden className={running ? 'inline-block animate-spin' : 'inline-block'}>
          ↻
        </span>
        {running ? 'Refreshing…' : 'Refresh'}
      </button>
      <div role="status" aria-live="polite" className="flex flex-col leading-tight">
        {summary}
        <span className="text-xs text-slate-400">
          {lastSuccessAt ? `Last successful refresh: ${formatTime(lastSuccessAt)}` : 'Not refreshed yet'}
        </span>
      </div>
      {showDetails && lastResult && lastResult.errors.length > 0 && (
        <div role="dialog" aria-label="Refresh errors" className="absolute left-0 top-full z-40 mt-1 max-h-72 w-96 overflow-auto rounded-md border border-slate-200 bg-white p-3 text-xs shadow-lg">
          <p className="mb-2 text-slate-600">These tickers keep their last known price, marked ⚠ as stale:</p>
          <ul className="space-y-1">
            {lastResult.errors.map((e) => (
              <li key={e.ticker}>
                <span className="font-medium">{e.ticker}</span>: <span className="text-slate-600">{e.message}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
