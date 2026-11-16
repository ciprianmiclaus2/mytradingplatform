import { listPortfolios } from '../api/portfolios'
import type { Portfolio, PortfolioType } from '../types/api'
import { useApiData, type ApiData } from './useApiData'

export function usePortfolios(): ApiData<Portfolio[]> {
  return useApiData('portfolios', listPortfolios)
}

export interface PortfolioSelection {
  portfolio: Portfolio | undefined
  /** The saved portfolio no longer exists (or has the wrong type). */
  missing: boolean
}

/**
 * The portfolio a pane shows: the saved one if it still exists, otherwise
 * (when nothing was saved) the first portfolio of an allowed type.
 */
export function selectPortfolio(
  portfolios: Portfolio[] | undefined,
  savedId: string | undefined,
  types: readonly PortfolioType[],
): PortfolioSelection {
  if (!portfolios) return { portfolio: undefined, missing: false }
  const allowed = portfolios.filter((p) => types.includes(p.type))
  if (savedId) {
    const found = allowed.find((p) => p.id === savedId)
    return { portfolio: found, missing: found === undefined }
  }
  return { portfolio: allowed[0], missing: false }
}
