import { getPaneDefinition } from '../panes/registry'
import { newGroupId, newPaneId } from '../utils/id'
import { MINIMISED_HEIGHT } from './grid'
import type { DashboardState, Pane, PaneGroup, PaneLayout } from './types'

export { GRID_COLS, MINIMISED_HEIGHT } from './grid'

export type DashboardAction =
  | { type: 'addPane'; paneType: string; id?: string; groupId?: string }
  | { type: 'removePane'; id: string }
  | { type: 'layoutChange'; layouts: readonly PaneLayout[] }
  | { type: 'toggleMinimise'; id: string }
  | { type: 'updateConfig'; id: string; config: Record<string, unknown> }
  | { type: 'selectTab'; groupId: string; paneId: string }
  | { type: 'moveToGroup'; paneId: string; groupId: string }
  | { type: 'detachPane'; paneId: string; groupId?: string }
  | { type: 'reorderTab'; paneId: string; index: number }
  | { type: 'reset'; state: DashboardState }

function bottom(layouts: PaneLayout[]): number {
  return layouts.reduce((max, l) => Math.max(max, l.y + l.h), 0)
}

function nextTitle(panes: Pane[], baseTitle: string, paneType: string): string {
  const count = panes.filter((p) => p.type === paneType).length
  return count === 0 ? baseTitle : `${baseTitle} ${count + 1}`
}

export function groupOf(state: DashboardState, paneId: string): PaneGroup | undefined {
  return state.groups.find((g) => g.paneIds.includes(paneId))
}

/** Minimum tile size for a group: large enough for every pane in it. */
export function groupMinSize(state: DashboardState, group: PaneGroup): { w: number; h: number } {
  let w = 2
  let h = 2
  for (const id of group.paneIds) {
    const pane = state.panes.find((p) => p.id === id)
    const def = pane ? getPaneDefinition(pane.type) : undefined
    if (def) {
      w = Math.max(w, def.minSize.w)
      h = Math.max(h, def.minSize.h)
    }
  }
  return { w, h }
}

/** A new pane in its own tile, placed below everything else. */
export function createPane(state: DashboardState, paneType: string, id = newPaneId(), groupId = newGroupId()): DashboardState {
  const def = getPaneDefinition(paneType)
  if (!def) return state
  const pane: Pane = { id, type: paneType, title: nextTitle(state.panes, def.title, paneType), config: def.defaultConfig() }
  const group: PaneGroup = { id: groupId, paneIds: [id], active: id }
  const layout: PaneLayout = { i: groupId, x: 0, y: bottom(state.layouts), w: def.defaultSize.w, h: def.defaultSize.h }
  return { ...state, panes: [...state.panes, pane], groups: [...state.groups, group], layouts: [...state.layouts, layout] }
}

/** Take a pane out of its group; an emptied group (and its tile) is removed. */
function withoutPaneInGroups(state: DashboardState, paneId: string): DashboardState {
  const source = groupOf(state, paneId)
  if (!source) return state
  const remaining = source.paneIds.filter((id) => id !== paneId)
  if (remaining.length === 0) {
    const { [source.id]: _gone, ...minimised } = state.minimised
    return {
      ...state,
      groups: state.groups.filter((g) => g.id !== source.id),
      layouts: state.layouts.filter((l) => l.i !== source.id),
      minimised,
    }
  }
  // Activate the neighbouring tab when the active one leaves.
  const index = source.paneIds.indexOf(paneId)
  const active = source.active === paneId ? remaining[Math.min(index, remaining.length - 1)] : source.active
  return { ...state, groups: state.groups.map((g) => (g.id === source.id ? { ...g, paneIds: remaining, active } : g)) }
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
      return createPane(state, action.paneType, action.id, action.groupId)

    case 'removePane': {
      if (!state.panes.some((p) => p.id === action.id)) return state
      const next = withoutPaneInGroups(state, action.id)
      return { ...next, panes: next.panes.filter((p) => p.id !== action.id) }
    }

    case 'layoutChange': {
      // Keep only known tiles, in their current order, with plain {i,x,y,w,h} values.
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

    case 'selectTab': {
      const group = state.groups.find((g) => g.id === action.groupId)
      if (!group || !group.paneIds.includes(action.paneId) || group.active === action.paneId) return state
      return { ...state, groups: state.groups.map((g) => (g === group ? { ...g, active: action.paneId } : g)) }
    }

    case 'moveToGroup': {
      const source = groupOf(state, action.paneId)
      const target = state.groups.find((g) => g.id === action.groupId)
      if (!source || !target || source.id === target.id) return state
      const next = withoutPaneInGroups(state, action.paneId)
      const merged: PaneGroup = { ...target, paneIds: [...target.paneIds, action.paneId], active: action.paneId }
      const result = { ...next, groups: next.groups.map((g) => (g.id === target.id ? merged : g)) }
      // Grow the tile if the new tab needs more room than it has.
      const min = groupMinSize(result, merged)
      const restoreHeight = result.minimised[target.id]
      return {
        ...result,
        minimised: restoreHeight === undefined ? result.minimised : { ...result.minimised, [target.id]: Math.max(restoreHeight, min.h) },
        layouts: result.layouts.map((l) =>
          l.i === target.id
            ? { ...l, w: Math.max(l.w, min.w), h: target.id in result.minimised ? l.h : Math.max(l.h, min.h) }
            : l,
        ),
      }
    }

    case 'detachPane': {
      const source = groupOf(state, action.paneId)
      const pane = state.panes.find((p) => p.id === action.paneId)
      const def = pane ? getPaneDefinition(pane.type) : undefined
      if (!source || !pane || !def || source.paneIds.length < 2) return state
      const next = withoutPaneInGroups(state, action.paneId)
      const groupId = action.groupId ?? newGroupId()
      const sourceLayout = state.layouts.find((l) => l.i === source.id)
      // Same width as the tile it left, so it lines up underneath.
      const w = Math.max(def.minSize.w, sourceLayout?.w ?? def.defaultSize.w)
      return {
        ...next,
        groups: [...next.groups, { id: groupId, paneIds: [pane.id], active: pane.id }],
        layouts: [...next.layouts, { i: groupId, x: sourceLayout?.x ?? 0, y: bottom(next.layouts), w, h: def.defaultSize.h }],
      }
    }

    case 'reorderTab': {
      const group = groupOf(state, action.paneId)
      if (!group) return state
      const others = group.paneIds.filter((id) => id !== action.paneId)
      const index = Math.max(0, Math.min(action.index, others.length))
      const paneIds = [...others.slice(0, index), action.paneId, ...others.slice(index)]
      if (paneIds.every((id, i) => id === group.paneIds[i])) return state
      return { ...state, groups: state.groups.map((g) => (g === group ? { ...g, paneIds } : g)) }
    }

    case 'reset':
      return action.state
  }
}
