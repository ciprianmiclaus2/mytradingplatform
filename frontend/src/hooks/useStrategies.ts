import { listStrategies } from '../api/strategies'
import type { StrategySchema } from '../types/api'
import { useApiData, type ApiData } from './useApiData'

export function useStrategies(): ApiData<StrategySchema[]> {
  return useApiData('strategies', listStrategies)
}
