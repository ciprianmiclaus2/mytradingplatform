import { useSyncExternalStore } from 'react'

/**
 * A counter that changes whenever backend data may have changed (a pane
 * edited a portfolio or position; in Phase 10, a market data refresh).
 * Every pane reloads its data when it changes, so panes stay consistent.
 */
let version = 0
const listeners = new Set<() => void>()

export function notifyDataChanged(): void {
  version += 1
  listeners.forEach((listener) => listener())
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function useDataVersion(): number {
  return useSyncExternalStore(subscribe, () => version)
}
