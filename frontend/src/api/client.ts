import type { ApiErrorEnvelope } from '../types/api'

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/+$/, '')

const DEFAULT_TIMEOUT_MS = 35_000

/** Error raised for any failed API call. `status` is 0 when no response was received. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details?: unknown

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }

  get isBackendUnavailable(): boolean {
    return this.status === 0 || this.status === 502 || this.status === 503 || this.status === 504
  }
}

function isErrorEnvelope(value: unknown): value is ApiErrorEnvelope {
  if (typeof value !== 'object' || value === null || !('error' in value)) return false
  const err = (value as { error: unknown }).error
  return (
    typeof err === 'object' &&
    err !== null &&
    typeof (err as { code?: unknown }).code === 'string' &&
    typeof (err as { message?: unknown }).message === 'string'
  )
}

export interface RequestOptions {
  method?: string
  body?: unknown
  signal?: AbortSignal
  timeoutMs?: number
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, signal, timeoutMs = DEFAULT_TIMEOUT_MS } = options
  const timeoutSignal = AbortSignal.timeout(timeoutMs)
  const combined = signal ? AbortSignal.any([signal, timeoutSignal]) : timeoutSignal

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: combined,
    })
  } catch (cause) {
    if (signal?.aborted) throw cause
    const timedOut = timeoutSignal.aborted
    throw new ApiError(
      0,
      timedOut ? 'timeout' : 'backend_unavailable',
      timedOut ? 'The backend did not respond in time.' : 'The backend is unavailable.',
    )
  }

  const payload: unknown = await response.json().catch(() => undefined)

  if (!response.ok) {
    if (isErrorEnvelope(payload)) {
      const { code, message, details } = payload.error
      throw new ApiError(response.status, code, message, details)
    }
    throw new ApiError(response.status, 'http_error', `Request failed with status ${response.status}.`)
  }
  return payload as T
}
