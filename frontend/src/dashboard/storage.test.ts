import { afterEach, describe, expect, it, vi } from 'vitest'
import { STORAGE_KEY, loadDashboard, parseStoredDashboard, saveDashboard } from './storage'
import type { DashboardState } from './types'

const valid = {
  version: 2,
  panes: [
    { id: 'pane-a', type: 'portfolio', title: 'Watch', config: { portfolioId: 'p1' } },
    { id: 'pane-b', type: 'strategy', title: 'MR', config: {} },
    { id: 'pane-c', type: 'strategy', title: 'RSI', config: {} },
  ],
  groups: [
    { id: 'group-1', paneIds: ['pane-a'], active: 'pane-a' },
    { id: 'group-2', paneIds: ['pane-b', 'pane-c'], active: 'pane-c' },
  ],
  layouts: [
    { i: 'group-1', x: 0, y: 0, w: 6, h: 8 },
    { i: 'group-2', x: 6, y: 0, w: 6, h: 1 },
  ],
  minimised: { 'group-2': 9 },
}

/** A layout saved before tabs existed (version 1: one pane per tile). */
const version1 = {
  version: 1,
  panes: [
    { id: 'pane-a', type: 'portfolio', title: 'Watch', config: { portfolioId: 'p1' } },
    { id: 'pane-b', type: 'strategy', title: 'MR', config: { strategy: 'rsi' } },
  ],
  layouts: [
    { i: 'pane-a', x: 0, y: 0, w: 6, h: 8 },
    { i: 'pane-b', x: 6, y: 0, w: 6, h: 1 },
  ],
  minimised: { 'pane-b': 9 },
}

describe('dashboard storage', () => {
  afterEach(() => vi.restoreAllMocks())

  it('uses the default layout when nothing is saved', () => {
    const { state, warning } = loadDashboard()
    expect(state.panes.map((p) => p.type)).toEqual(['portfolio', 'positions'])
    expect(warning).toBeUndefined()
  })

  it('round-trips tab groups through localStorage', () => {
    const state: DashboardState = parseStoredDashboard(valid).state
    expect(state.groups).toEqual(valid.groups)
    expect(saveDashboard(state)).toBe(true)
    expect(JSON.parse(window.localStorage.getItem(STORAGE_KEY)!).version).toBe(2)
    const loaded = loadDashboard()
    expect(loaded.state).toEqual(state)
    expect(loaded.warning).toBeUndefined()
    expect(loaded.state.minimised).toEqual({ 'group-2': 9 })
  })

  it('migrates a version 1 layout: each pane becomes its own tile, keeping ids, sizes and settings', () => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(version1))
    const { state, warning } = loadDashboard()
    expect(warning).toBeUndefined()
    expect(state.panes).toEqual(version1.panes) // pane ids unchanged: signal history still matches
    expect(state.groups).toEqual([
      { id: 'group-pane-a', paneIds: ['pane-a'], active: 'pane-a' },
      { id: 'group-pane-b', paneIds: ['pane-b'], active: 'pane-b' },
    ])
    expect(state.layouts).toEqual([
      { i: 'group-pane-a', x: 0, y: 0, w: 6, h: 8 },
      { i: 'group-pane-b', x: 6, y: 0, w: 6, h: 1 },
    ])
    expect(state.minimised).toEqual({ 'group-pane-b': 9 })
  })

  it.each([
    ['not JSON', '{oops'],
    ['unknown version', JSON.stringify({ ...valid, version: 3 })],
    ['no groups array', JSON.stringify({ ...valid, groups: undefined })],
    ['version 1 without panes', JSON.stringify({ version: 1, layouts: [] })],
    ['array document', JSON.stringify([1, 2])],
    ['bad minimised', JSON.stringify({ ...valid, minimised: [] })],
  ])('falls back to the default layout for %s', (_label, text) => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    window.localStorage.setItem(STORAGE_KEY, text)
    const { state, warning } = loadDashboard()
    expect(state.panes.map((p) => p.type)).toEqual(['portfolio', 'positions'])
    expect(warning).toMatch(/default layout/)
  })

  it('drops unusable panes and repairs groups, keeping the rest', () => {
    const doc = {
      ...valid,
      panes: [
        ...valid.panes,
        { id: 'pane-x', type: 'unknown-type', title: 'X', config: {} },
        { id: 'pane-y', type: 'portfolio', title: 'In no group', config: {} },
        { id: 'pane-a', type: 'portfolio', title: 'Duplicate id', config: {} },
        { id: 'bad id!', type: 'portfolio', title: 'Bad id', config: {} },
        { id: 'pane-e', type: 'portfolio', title: 'Bad config', config: 'x' },
        { id: 'pane-f', type: 'portfolio', title: 'Group without layout', config: {} },
      ],
      groups: [
        { id: 'group-1', paneIds: ['pane-a', 'pane-x', 'ghost'], active: 'ghost' }, // bad members ignored, active repaired
        { id: 'group-2', paneIds: ['pane-b', 'pane-c', 'pane-a'], active: 'pane-c' }, // pane-a already used
        { id: 'group-3', paneIds: ['pane-f'], active: 'pane-f' }, // no layout
        { id: 'group-1', paneIds: ['pane-y'], active: 'pane-y' }, // duplicate group id
      ],
    }
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(doc))
    const { state, warning } = loadDashboard()
    expect(state.panes.map((p) => p.id)).toEqual(['pane-a', 'pane-b', 'pane-c'])
    expect(state.groups).toEqual([
      { id: 'group-1', paneIds: ['pane-a'], active: 'pane-a' },
      { id: 'group-2', paneIds: ['pane-b', 'pane-c'], active: 'pane-c' },
    ])
    expect(warning).toBe('6 saved pane(s) could not be restored and were removed.')
  })

  it('clamps widths to the grid', () => {
    const doc = { ...valid, layouts: [{ i: 'group-1', x: 8, y: 0, w: 10, h: 4 }, valid.layouts[1]] }
    expect(parseStoredDashboard(doc).state.layouts[0].w).toBe(4)
  })

  it('does not crash when storage is unavailable', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('denied')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota')
    })
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    const { state, warning } = loadDashboard()
    expect(state.panes).toHaveLength(2)
    expect(warning).toMatch(/could not be read/)
    expect(saveDashboard(state)).toBe(false)
  })
})
