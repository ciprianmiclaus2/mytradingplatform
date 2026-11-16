import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/client'
import { useDataVersion } from './dataVersion'

export interface ApiData<T> {
  /** Last successfully loaded value for the current key (kept while reloading or after an error). */
  data: T | undefined
  error: string | null
  loading: boolean
  reload: () => void
}

interface Loaded<T> {
  key: string
  token: string
  data: T | undefined
  error: string | null
}

/**
 * Requests in flight, by token. Panes asking for the same data at the same
 * time (e.g. every pane reloading the portfolio list after a refresh) share
 * one request. Entries are removed as soon as the request settles.
 */
const inflight = new Map<string, Promise<unknown>>()

function shared<T>(token: string, load: () => Promise<T>): Promise<T> {
  let promise = inflight.get(token) as Promise<T> | undefined
  if (!promise) {
    promise = load()
    inflight.set(token, promise)
    const forget = () => inflight.delete(token)
    promise.then(forget, forget)
  }
  return promise
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'Unexpected error.'
}

/**
 * Load data from the API. `key` identifies what is loaded (null = nothing to
 * load); the loader re-runs when the key changes, on `reload()`, and when
 * backend data changes (see dataVersion). Data from the previous load of the
 * same key stays visible while reloading and after a failed reload.
 *
 * The key must identify the request completely: identical keys share a request.
 */
export function useApiData<T>(key: string | null, load: (signal: AbortSignal) => Promise<T>): ApiData<T> {
  const version = useDataVersion()
  const [nonce, setNonce] = useState(0)
  const [loaded, setLoaded] = useState<Loaded<T> | null>(null)
  const loadRef = useRef(load)
  useEffect(() => {
    loadRef.current = load
  })

  const token = `${key}|${version}|${nonce}`

  useEffect(() => {
    if (key === null) return
    // Each consumer can stop listening; the shared request itself is not aborted.
    const controller = new AbortController()
    const load = loadRef.current
    shared(token, () => load(new AbortController().signal)).then(
      (data) => {
        if (!controller.signal.aborted) setLoaded({ key, token, data, error: null })
      },
      (err: unknown) => {
        if (controller.signal.aborted) return
        setLoaded((prev) => ({
          key,
          token,
          data: prev?.key === key ? prev.data : undefined,
          error: errorMessage(err),
        }))
      },
    )
    return () => controller.abort()
  }, [key, token])

  const reload = useCallback(() => setNonce((n) => n + 1), [])
  const current = loaded !== null && loaded.key === key ? loaded : null
  return {
    data: current?.data,
    error: current?.error ?? null,
    loading: key !== null && current?.token !== token,
    reload,
  }
}
