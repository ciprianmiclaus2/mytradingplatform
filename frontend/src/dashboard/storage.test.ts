import { afterEach, describe, expect, it, vi } from 'vitest'
import { STORAGE_KEY, loadDashboard, parseStoredDashboard, saveDashboard } from './storage'
import type { DashboardState } from './types'

const valid = {
  version: 1,
  panes: [
    { id: 'pane-a', type: 'portfolio', title: 'Watch', config: { portfolioId: 'p1' } },
    { id: 'pane-b', type: 'strategy', title: 'MR', config: {} },
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

  it('round-trips through localStorage', () => {
    const state: DashboardState = parseStoredDashboard(valid).state
    expect(saveDashboard(state)).toBe(true)
    expect(JSON.parse(window.localStorage.getItem(STORAGE_KEY)!).version).toBe(1)
    const loaded = loadDashboard()
    expect(loaded.state).toEqual(state)
    expect(loaded.warning).toBeUndefined()
    expect(loaded.state.minimised).toEqual({ 'pane-b': 9 })
  })

  it.each([
    ['not JSON', '{oops'],
    ['wrong version', JSON.stringify({ ...valid, version: 2 })],
    ['no panes array', JSON.stringify({ version: 1, layouts: [] })],
    ['array document', JSON.stringify([1, 2])],
    ['bad minimised', JSON.stringify({ ...valid, minimised: [] })],
  ])('falls back to the default layout for %s', (_label, text) => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    window.localStorage.setItem(STORAGE_KEY, text)
    const { state, warning } = loadDashboard()
    expect(state.panes.map((p) => p.type)).toEqual(['portfolio', 'positions'])
    expect(warning).toMatch(/default layout/)
  })

  it('drops individual unusable panes and keeps the rest', () => {
    const doc = {
      ...valid,
      panes: [
        ...valid.panes,
        { id: 'pane-c', type: 'unknown-type', title: 'X', config: {} },
        { id: 'pane-d', type: 'portfolio', title: 'No layout', config: {} },
        { id: 'pane-a', type: 'portfolio', title: 'Duplicate id', config: {} },
        { id: 'bad id!', type: 'portfolio', title: 'Bad id', config: {} },
        { id: 'pane-e', type: 'portfolio', title: 'Bad config', config: 'x' },
        { id: 'pane-f', type: 'portfolio', title: 'Bad layout', config: {} },
      ],
      layouts: [...valid.layouts, { i: 'pane-c', x: 0, y: 0, w: 1, h: 1 }, { i: 'pane-f', x: -1, y: 0, w: 0, h: 1 }],
    }
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(doc))
    const { state, warning } = loadDashboard()
    expect(state.panes.map((p) => p.id)).toEqual(['pane-a', 'pane-b'])
    expect(warning).toBe('6 saved pane(s) could not be restored and were removed.')
  })

  it('clamps widths to the grid', () => {
    const doc = { ...valid, layouts: [{ i: 'pane-a', x: 8, y: 0, w: 10, h: 4 }, valid.layouts[1]] }
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
