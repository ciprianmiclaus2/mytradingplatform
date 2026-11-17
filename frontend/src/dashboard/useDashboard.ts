import { useCallback, useEffect, useMemo, useReducer, useState, useSyncExternalStore } from 'react'
import { defaultDashboard } from './defaults'
import { dashboardReducer } from './reducer'
import { getSaveStatus, loadDashboard, saveDashboard, subscribeSaveStatus } from './storage'
import type { DashboardState, PaneLayout } from './types'

export interface DashboardApi {
  state: DashboardState
  /** Message about a saved layout that could not be restored. */
  warning: string | null
  /** False when the layout cannot be saved (storage unavailable). */
  saveOk: boolean
  dismissWarning: () => void
  addPane: (paneType: string) => void
  /** Add several panes of one type with the given configurations, one tile each. */
  addPanes: (paneType: string, configs: Record<string, unknown>[]) => void
  removePane: (id: string) => void
  layoutChange: (layouts: readonly PaneLayout[]) => void
  /** Minimise or restore a tile (group id). */
  toggleMinimise: (id: string) => void
  updateConfig: (id: string, config: Record<string, unknown>) => void
  selectTab: (groupId: string, paneId: string) => void
  moveToGroup: (paneId: string, groupId: string) => void
  detachPane: (paneId: string) => void
  reorderTab: (paneId: string, index: number) => void
  resetLayout: () => void
}

/** Dashboard state, restored from and automatically saved to localStorage. */
export function useDashboard(): DashboardApi {
  const [initial] = useState(loadDashboard)
  const [state, dispatch] = useReducer(dashboardReducer, initial.state)
  const [warning, setWarning] = useState<string | null>(initial.warning ?? null)
  const saveOk = useSyncExternalStore(subscribeSaveStatus, getSaveStatus)

  // Save automatically after every change (add, remove, move, resize, config, reset).
  useEffect(() => {
    saveDashboard(state)
  }, [state])

  const addPane = useCallback((paneType: string) => dispatch({ type: 'addPane', paneType }), [])
  const addPanes = useCallback(
    (paneType: string, configs: Record<string, unknown>[]) => dispatch({ type: 'addPanes', paneType, configs }),
    [],
  )
  const removePane = useCallback((id: string) => dispatch({ type: 'removePane', id }), [])
  const layoutChange = useCallback(
    (layouts: readonly PaneLayout[]) => dispatch({ type: 'layoutChange', layouts }),
    [],
  )
  const toggleMinimise = useCallback((id: string) => dispatch({ type: 'toggleMinimise', id }), [])
  const updateConfig = useCallback(
    (id: string, config: Record<string, unknown>) => dispatch({ type: 'updateConfig', id, config }),
    [],
  )
  const selectTab = useCallback((groupId: string, paneId: string) => dispatch({ type: 'selectTab', groupId, paneId }), [])
  const moveToGroup = useCallback((paneId: string, groupId: string) => dispatch({ type: 'moveToGroup', paneId, groupId }), [])
  const detachPane = useCallback((paneId: string) => dispatch({ type: 'detachPane', paneId }), [])
  const reorderTab = useCallback((paneId: string, index: number) => dispatch({ type: 'reorderTab', paneId, index }), [])
  const resetLayout = useCallback(() => {
    dispatch({ type: 'reset', state: defaultDashboard() })
    setWarning(null)
  }, [])
  const dismissWarning = useCallback(() => setWarning(null), [])

  return useMemo(
    () => ({
      state, warning, saveOk, dismissWarning, addPane, addPanes, removePane, layoutChange, toggleMinimise, updateConfig,
      selectTab, moveToGroup, detachPane, reorderTab, resetLayout,
    }),
    [
      state, warning, saveOk, dismissWarning, addPane, addPanes, removePane, layoutChange, toggleMinimise, updateConfig,
      selectTab, moveToGroup, detachPane, reorderTab, resetLayout,
    ],
  )
}
