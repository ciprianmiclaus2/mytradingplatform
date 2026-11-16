import { describe, expect, it } from 'vitest'
import { defaultDashboard } from './defaults'
import { MINIMISED_HEIGHT, createPane, dashboardReducer } from './reducer'
import type { DashboardState } from './types'

const empty: DashboardState = { panes: [], layouts: [], minimised: {} }

describe('dashboardReducer', () => {
  it('creates a default dashboard with portfolio and positions side by side', () => {
    const state = defaultDashboard()
    expect(state.panes.map((p) => p.type)).toEqual(['portfolio', 'positions'])
    expect(state.layouts.map(({ x, y }) => [x, y])).toEqual([[0, 0], [6, 0]])
  })

  it('adds panes with unique ids, placed below existing panes', () => {
    let state = dashboardReducer(empty, { type: 'addPane', paneType: 'strategy' })
    state = dashboardReducer(state, { type: 'addPane', paneType: 'strategy' })
    state = dashboardReducer(state, { type: 'addPane', paneType: 'portfolio' })
    expect(state.panes.map((p) => p.title)).toEqual(['Strategy', 'Strategy 2', 'Portfolio'])
    expect(new Set(state.panes.map((p) => p.id)).size).toBe(3)
    expect(state.panes.every((p) => /^pane-[A-Za-z0-9-]+$/.test(p.id))).toBe(true)
    expect(state.layouts.map((l) => l.y)).toEqual([0, 12, 24])
  })

  it('ignores unknown pane types', () => {
    expect(dashboardReducer(empty, { type: 'addPane', paneType: 'nope' })).toBe(empty)
  })

  it('removes a pane with its layout and minimised state', () => {
    let state = createPane(createPane(empty, 'portfolio', 'a'), 'positions', 'b')
    state = dashboardReducer(state, { type: 'toggleMinimise', id: 'a' })
    state = dashboardReducer(state, { type: 'removePane', id: 'a' })
    expect(state.panes.map((p) => p.id)).toEqual(['b'])
    expect(state.layouts.map((l) => l.i)).toEqual(['b'])
    expect(state.minimised).toEqual({})
  })

  it('applies moves and resizes from the grid', () => {
    const state = createPane(createPane(empty, 'portfolio', 'a'), 'positions', 'b')
    const next = dashboardReducer(state, {
      type: 'layoutChange',
      layouts: [
        { i: 'b', x: 0, y: 0, w: 4, h: 6 },
        { i: 'a', x: 4, y: 0, w: 8, h: 12 },
        { i: 'ghost', x: 0, y: 0, w: 1, h: 1 },
      ],
    })
    expect(next.layouts).toEqual([
      { i: 'a', x: 4, y: 0, w: 8, h: 12 },
      { i: 'b', x: 0, y: 0, w: 4, h: 6 },
    ])
  })

  it('returns the same state when the layout did not change', () => {
    const state = createPane(empty, 'portfolio', 'a')
    expect(dashboardReducer(state, { type: 'layoutChange', layouts: [...state.layouts] })).toBe(state)
  })

  it('minimises and restores a pane to its previous height', () => {
    let state = createPane(empty, 'portfolio', 'a')
    state = dashboardReducer(state, { type: 'layoutChange', layouts: [{ i: 'a', x: 0, y: 0, w: 6, h: 14 }] })
    state = dashboardReducer(state, { type: 'toggleMinimise', id: 'a' })
    expect(state.layouts[0].h).toBe(MINIMISED_HEIGHT)
    expect(state.minimised).toEqual({ a: 14 })
    state = dashboardReducer(state, { type: 'toggleMinimise', id: 'a' })
    expect(state.layouts[0].h).toBe(14)
    expect(state.minimised).toEqual({})
  })

  it('updates pane configuration', () => {
    const state = dashboardReducer(createPane(empty, 'strategy', 'a'), {
      type: 'updateConfig',
      id: 'a',
      config: { strategy: 'mean_reversion' },
    })
    expect(state.panes[0].config).toEqual({ strategy: 'mean_reversion' })
  })
})
