import type { ParameterValue, StrategyRunResult, StrategySchema } from '../types/api'
import { apiRequest } from './client'

export function listStrategies(signal?: AbortSignal): Promise<StrategySchema[]> {
  return apiRequest<StrategySchema[]>('/strategies', { signal })
}

export function runStrategy(
  name: string,
  body: { tickers: string[]; config: Record<string, ParameterValue>; instance_id?: string },
  signal?: AbortSignal,
): Promise<StrategyRunResult> {
  return apiRequest<StrategyRunResult>(`/strategies/${encodeURIComponent(name)}/run`, { method: 'POST', body, signal })
}
