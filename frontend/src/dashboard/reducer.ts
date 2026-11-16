import { getPaneDefinition } from '../panes/registry'
import { newPaneId } from '../utils/id'
import { MINIMISED_HEIGHT } from './grid'
import type { DashboardState, Pane, PaneLayout } from './types'

export { GRID_COLS, MINIMISED_HEIGHT } from './grid'

export type DashboardAction =
  | { type: 'addPane'; paneType: string; id?: string }
  | { type: 'removePane'; id: string }
  | { type: 'layoutChange'; layouts: readonly PaneLayout[] }
  | { type: 'toggleMinimise'; id: string }
  | { type: 'updateConfig'; id: string; config: Record<string, unknown> }
  | { type: 'reset'; state: DashboardState }

function bottom(layouts: PaneLayout[]): number {
  return layouts.reduce((max, l) => Math.max(max, l.y + l.h), 0)
}

function nextTitle(panes: Pane[], baseTitle: string, paneType: string): string {
  const count = panes.filter((p) => p.type === paneType).length
  return count === 0 ? baseTitle : `${baseTitle} ${count + 1}`
}

export function createPane(state: DashboardState, paneType: string, id = newPaneId()): DashboardState {
  const def = getPaneDefinition(paneType)
  if (!def) return state
  const pane: Pane = { id, type: paneType, title: nextTitle(state.panes, def.title, paneType), config: def.defaultConfig() }
  const layout: PaneLayout = { i: id, x: 0, y: bottom(state.layouts), w: def.defaultSize.w, h: def.defaultSize.h }
  return { ...state, panes: [...state.panes, pane], layouts: [...state.layouts, layout] }
}

function sameLayouts(a: PaneLayout[], b: PaneLayout[]): boolean {
  return a.length === b.length && a.every((l, i) => {
    const o = b[i]
    return l.i === o.i && l.x === o.x && l.y === o.y && l.w === o.w && l.h === o.h
  })
}

export function dashboardReducer(state: DashboardState, action: DashboardAction): DashboardState {
  switch (action.type) {
    case 'addPane':
      return createPane(state, action.paneType, action.id)

    case 'removePane': {
      const { [action.id]: _removed, ...minimised } = state.minimised
      return {
        panes: state.panes.filter((p) => p.id !== action.id),
        layouts: state.layouts.filter((l) => l.i !== action.id),
        minimised,
      }
    }

    case 'layoutChange': {
      // Keep only known panes, in pane order, with plain {i,x,y,w,h} values.
      const byId = new Map(action.layouts.map((l) => [l.i, l]))
      const layouts = state.layouts.map((current) => {
        const next = byId.get(current.i)
        return next ? { i: current.i, x: next.x, y: next.y, w: next.w, h: next.h } : current
      })
      return sameLayouts(layouts, state.layouts) ? state : { ...state, layouts }
    }

    case 'toggleMinimise': {
      const current = state.layouts.find((l) => l.i === action.id)
      if (!current) return state
      if (action.id in state.minimised) {
        const { [action.id]: restoreHeight, ...minimised } = state.minimised
        return {
          ...state,
          minimised,
          layouts: state.layouts.map((l) => (l.i === action.id ? { ...l, h: restoreHeight } : l)),
        }
      }
      return {
        ...state,
        minimised: { ...state.minimised, [action.id]: current.h },
        layouts: state.layouts.map((l) => (l.i === action.id ? { ...l, h: MINIMISED_HEIGHT } : l)),
      }
    }

    case 'updateConfig':
      return {
        ...state,
        panes: state.panes.map((p) => (p.id === action.id ? { ...p, config: action.config } : p)),
      }

    case 'reset':
      return action.state
  }
}
