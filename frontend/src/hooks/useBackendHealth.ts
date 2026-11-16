import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { getHealth } from '../api/health'
import type { HealthResponse } from '../types/api'

export type BackendHealthState =
  | { status: 'checking' }
  | { status: 'ok'; health: HealthResponse }
  | { status: 'error'; message: string }

export function useBackendHealth(): { state: BackendHealthState; recheck: () => void } {
  const [state, setState] = useState<BackendHealthState>({ status: 'checking' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    getHealth(controller.signal)
      .then((health) => setState({ status: 'ok', health }))
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        const message = err instanceof ApiError ? err.message : 'Unexpected error contacting backend.'
        setState({ status: 'error', message })
      })
    return () => controller.abort()
  }, [attempt])

  const recheck = useCallback(() => {
    setState({ status: 'checking' })
    setAttempt((n) => n + 1)
  }, [])

  return { state, recheck }
}
