import type { HealthResponse } from '../types/api'
import { apiRequest } from './client'

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return apiRequest<HealthResponse>('/health', { signal, timeoutMs: 5_000 })
}
