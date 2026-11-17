import { useMemo } from 'react'
import { useBrokerAccounts } from '../hooks/useBrokerAccounts'
import { usePortfolios } from '../hooks/usePortfolios'
import { useStrategies } from '../hooks/useStrategies'
import { paneLabels } from '../panes/labels'
import { getPaneDefinition } from '../panes/registry'
import type { DashboardState } from './types'

/** Tab label for every pane in the dashboard (falls back to the pane title). */
export function usePaneLabels(state: DashboardState): Record<string, string> {
  const portfolios = usePortfolios().data
  const strategies = useStrategies().data
  const accounts = useBrokerAccounts().data?.accounts
  return useMemo(
    () =>
      paneLabels(state.panes, state.groups, (pane) => {
        const label = getPaneDefinition(pane.type)?.label?.(pane, { portfolios, strategies, accounts })
        return label || pane.title
      }),
    [state.panes, state.groups, portfolios, strategies, accounts],
  )
}
