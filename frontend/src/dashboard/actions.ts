import { createContext, useContext } from 'react'
import type { Pane } from './types'

/** Dashboard actions available to dialogs opened from panes (e.g. adding a pane per broker account). */
export interface DashboardActions {
  panes: Pane[]
  addPanes: (paneType: string, configs: Record<string, unknown>[]) => void
  updateConfig: (paneId: string, config: Record<string, unknown>) => void
}

export const DashboardActionsContext = createContext<DashboardActions | null>(null)

export function useDashboardActions(): DashboardActions | null {
  return useContext(DashboardActionsContext)
}
