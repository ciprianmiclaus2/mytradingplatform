import { describe, expect, it } from 'vitest'
import { defaultDashboard, emptyDashboard } from './defaults'
import { MINIMISED_HEIGHT, createPane, dashboardReducer, groupMinSize, groupOf } from './reducer'
import type { DashboardState } from './types'

const empty = emptyDashboard()

/** Panes a, b, c, each in its own tile ga, gb, gc. */
function three(): DashboardState {
  let state = createPane(empty, 'portfolio', 'a', 'ga')
  state = createPane(state, 'positions', 'b', 'gb')
  return createPane(state, 'strategy', 'c', 'gc')
}

const tabs = (state: DashboardState) => state.groups.map((g) => `${g.id}:${g.paneIds.join(',')}>${g.active}`)

describe('dashboardReducer', () => {
  it('creates a default dashboard with portfolio and positions side by side', () => {
    const state = defaultDashboard()
    expect(state.panes.map((p) => p.type)).toEqual(['portfolio', 'positions'])
    expect(state.groups.map((g) => g.paneIds.length)).toEqual([1, 1])
    expect(state.layouts.map(({ x, y }) => [x, y])).toEqual([[0, 0], [6, 0]])
  })

  it('adds several configured panes at once, two tiles per row below existing tiles', () => {
    const start = defaultDashboard() // two tiles in the first row (height 10)
    const configs = [{ accountId: 'a1' }, { accountId: 'a2' }, { accountId: 'a3' }]
    const state = dashboardReducer(start, { type: 'addPanes', paneType: 'positions', configs })
    const added = state.panes.slice(2)
    expect(added.map((p) => p.config)).toEqual(configs)
    expect(state.groups).toHaveLength(5)
    expect(state.layouts.slice(2).map(({ x, y }) => [x, y])).toEqual([[0, 10], [6, 10], [0, 20]])
    expect(dashboardReducer(start, { type: 'addPanes', paneType: 'positions', configs: [] })).toBe(start)
    expect(dashboardReducer(start, { type: 'addPanes', paneType: 'nope', configs })).toBe(start)
  })

  it('adds each pane in its own tile, with unique ids, below existing tiles', () => {
    let state = dashboardReducer(empty, { type: 'addPane', paneType: 'strategy' })
    state = dashboardReducer(state, { type: 'addPane', paneType: 'strategy' })
    state = dashboardReducer(state, { type: 'addPane', paneType: 'portfolio' })
    expect(state.panes.map((p) => p.title)).toEqual(['Strategy', 'Strategy 2', 'Portfolio'])
    expect(new Set(state.panes.map((p) => p.id)).size).toBe(3)
    expect(state.panes.every((p) => /^pane-[A-Za-z0-9-]+$/.test(p.id))).toBe(true)
    expect(state.groups.every((g) => /^group-[A-Za-z0-9-]+$/.test(g.id) && g.paneIds.length === 1)).toBe(true)
    expect(state.layouts.map((l) => l.y)).toEqual([0, 12, 24])
  })

  it('ignores unknown pane types', () => {
    expect(dashboardReducer(empty, { type: 'addPane', paneType: 'nope' })).toBe(empty)
  })

  it('removes a single pane with its tile and minimised state', () => {
    let state = three()
    state = dashboardReducer(state, { type: 'toggleMinimise', id: 'ga' })
    state = dashboardReducer(state, { type: 'removePane', id: 'a' })
    expect(state.panes.map((p) => p.id)).toEqual(['b', 'c'])
    expect(state.layouts.map((l) => l.i)).toEqual(['gb', 'gc'])
    expect(state.minimised).toEqual({})
  })

  it('moves a pane into another tile as the active tab, removing its emptied tile', () => {
    let state = dashboardReducer(three(), { type: 'moveToGroup', paneId: 'c', groupId: 'ga' })
    expect(tabs(state)).toEqual(['ga:a,c>c', 'gb:b>b'])
    expect(state.layouts.map((l) => l.i)).toEqual(['ga', 'gb'])
    state = dashboardReducer(state, { type: 'moveToGroup', paneId: 'b', groupId: 'ga' })
    expect(tabs(state)).toEqual(['ga:a,c,b>b'])
    expect(groupOf(state, 'b')?.id).toBe('ga')
  })

  it('grows a tile that is too small for a moved tab', () => {
    let state = createPane(empty, 'portfolio', 'a', 'ga') // min 3x4
    state = createPane(state, 'positions', 'b', 'gb') // min 4x4
    state = dashboardReducer(state, { type: 'layoutChange', layouts: [{ i: 'ga', x: 0, y: 0, w: 3, h: 4 }, state.layouts[1]] })
    state = dashboardReducer(state, { type: 'moveToGroup', paneId: 'b', groupId: 'ga' })
    expect(state.layouts[0]).toMatchObject({ w: 4, h: 4 })
    expect(groupMinSize(state, state.groups[0])).toEqual({ w: 4, h: 4 })
  })

  it('ignores moves to the same or an unknown tile', () => {
    const state = three()
    expect(dashboardReducer(state, { type: 'moveToGroup', paneId: 'a', groupId: 'ga' })).toBe(state)
    expect(dashboardReducer(state, { type: 'moveToGroup', paneId: 'a', groupId: 'nope' })).toBe(state)
  })

  it('selects tabs', () => {
    let state = dashboardReducer(three(), { type: 'moveToGroup', paneId: 'b', groupId: 'ga' })
    state = dashboardReducer(state, { type: 'selectTab', groupId: 'ga', paneId: 'a' })
    expect(state.groups[0].active).toBe('a')
    expect(dashboardReducer(state, { type: 'selectTab', groupId: 'ga', paneId: 'c' })).toBe(state) // not in this tile
  })

  it('removing the active tab activates its neighbour; the tile stays', () => {
    let state = dashboardReducer(three(), { type: 'moveToGroup', paneId: 'b', groupId: 'ga' })
    state = dashboardReducer(state, { type: 'moveToGroup', paneId: 'c', groupId: 'ga' }) // a,b,c active c
    state = dashboardReducer(state, { type: 'selectTab', groupId: 'ga', paneId: 'b' })
    state = dashboardReducer(state, { type: 'removePane', id: 'b' })
    expect(tabs(state)).toEqual(['ga:a,c>c'])
    expect(state.panes.map((p) => p.id)).toEqual(['a', 'c'])
  })

  it('detaches a tab into its own tile below, under the tile it left', () => {
    let state = dashboardReducer(three(), { type: 'moveToGroup', paneId: 'c', groupId: 'gb' })
    state = dashboardReducer(state, { type: 'layoutChange', layouts: [state.layouts[0], { i: 'gb', x: 6, y: 0, w: 6, h: 12 }] })
    state = dashboardReducer(state, { type: 'detachPane', paneId: 'c', groupId: 'gnew' })
    expect(tabs(state)).toEqual(['ga:a>a', 'gb:b>b', 'gnew:c>c'])
    expect(state.layouts[2]).toEqual({ i: 'gnew', x: 6, y: 12, w: 6, h: 12 })
    // A single pane cannot be detached from itself.
    expect(dashboardReducer(state, { type: 'detachPane', paneId: 'a' })).toBe(state)
  })

  it('reorders tabs', () => {
    let state = dashboardReducer(three(), { type: 'moveToGroup', paneId: 'b', groupId: 'ga' })
    state = dashboardReducer(state, { type: 'moveToGroup', paneId: 'c', groupId: 'ga' })
    state = dashboardReducer(state, { type: 'reorderTab', paneId: 'c', index: 0 })
    expect(state.groups[0].paneIds).toEqual(['c', 'a', 'b'])
    state = dashboardReducer(state, { type: 'reorderTab', paneId: 'c', index: 99 })
    expect(state.groups[0].paneIds).toEqual(['a', 'b', 'c'])
    expect(dashboardReducer(state, { type: 'reorderTab', paneId: 'c', index: 2 })).toBe(state)
  })

  it('applies moves and resizes from the grid', () => {
    const state = createPane(createPane(empty, 'portfolio', 'a', 'ga'), 'positions', 'b', 'gb')
    const next = dashboardReducer(state, {
      type: 'layoutChange',
      layouts: [
        { i: 'gb', x: 0, y: 0, w: 4, h: 6 },
        { i: 'ga', x: 4, y: 0, w: 8, h: 12 },
        { i: 'ghost', x: 0, y: 0, w: 1, h: 1 },
      ],
    })
    expect(next.layouts).toEqual([
      { i: 'ga', x: 4, y: 0, w: 8, h: 12 },
      { i: 'gb', x: 0, y: 0, w: 4, h: 6 },
    ])
  })

  it('returns the same state when the layout did not change', () => {
    const state = createPane(empty, 'portfolio', 'a', 'ga')
    expect(dashboardReducer(state, { type: 'layoutChange', layouts: [...state.layouts] })).toBe(state)
  })

  it('minimises and restores a tile to its previous height', () => {
    let state = createPane(empty, 'portfolio', 'a', 'ga')
    state = dashboardReducer(state, { type: 'layoutChange', layouts: [{ i: 'ga', x: 0, y: 0, w: 6, h: 14 }] })
    state = dashboardReducer(state, { type: 'toggleMinimise', id: 'ga' })
    expect(state.layouts[0].h).toBe(MINIMISED_HEIGHT)
    expect(state.minimised).toEqual({ ga: 14 })
    state = dashboardReducer(state, { type: 'toggleMinimise', id: 'ga' })
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
