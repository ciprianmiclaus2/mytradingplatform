import type { ReactNode } from 'react'

/** Row of controls at the top of a pane. */
export function PaneToolbar({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 px-2 py-1.5">{children}</div>
}

/** Whole-pane loading or error state (before any data is available). */
export function PaneMessage({ loading, error, onRetry }: { loading: boolean; error: string | null; onRetry?: () => void }) {
  if (error) {
    return (
      <div role="alert" className="flex items-center gap-2 p-4 text-sm text-red-700">
        <span>{error}</span>
        {onRetry && (
          <button type="button" onClick={onRetry} className="rounded border border-red-300 px-2 py-0.5 text-xs hover:bg-red-50">
            Retry
          </button>
        )}
      </div>
    )
  }
  return (
    <p role="status" className="p-4 text-sm text-slate-500">
      {loading ? 'Loading…' : 'No data.'}
    </p>
  )
}

/** Marks a price whose last refresh failed (last known value is shown). */
export function StaleMarker({ error }: { error?: string | null }) {
  const text = `Stale: the last refresh failed${error ? ` (${error})` : ''}. Showing the last known price.`
  return (
    <span role="img" aria-label="Stale price" title={text} className="mr-1 cursor-help text-amber-500">
      ⚠
    </span>
  )
}
