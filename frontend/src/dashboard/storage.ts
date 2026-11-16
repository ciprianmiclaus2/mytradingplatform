import { getPaneDefinition } from '../panes/registry'
import { defaultDashboard } from './defaults'
import { GRID_COLS, MINIMISED_HEIGHT } from './grid'
import type { DashboardState, Pane, PaneLayout, StoredDashboard } from './types'
import { LAYOUT_VERSION } from './types'

export const STORAGE_KEY = 'my-trading-platform-layout'

export interface LoadResult {
  state: DashboardState
  /** Set when a saved layout existed but could not be (fully) used. */
  warning?: string
}

const isObject = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v)

const isGridInt = (v: unknown, min: number): v is number =>
  typeof v === 'number' && Number.isInteger(v) && v >= min && v < 10_000

class InvalidLayout extends Error {}

/**
 * Validate a stored document. Structural problems (wrong version, wrong
 * shapes) reject the whole document; individual panes that are unusable
 * (unknown type, bad layout) are dropped with a warning.
 */
export function parseStoredDashboard(raw: unknown): { state: DashboardState; dropped: number } {
  if (!isObject(raw)) throw new InvalidLayout('not an object')
  if (raw.version !== LAYOUT_VERSION) throw new InvalidLayout(`unsupported version ${String(raw.version)}`)
  if (!Array.isArray(raw.panes) || !Array.isArray(raw.layouts)) throw new InvalidLayout('panes/layouts missing')
  const minimisedRaw = raw.minimised === undefined ? {} : raw.minimised
  if (!isObject(minimisedRaw)) throw new InvalidLayout('minimised is not an object')

  const layoutsById = new Map<string, PaneLayout>()
  for (const item of raw.layouts) {
    if (!isObject(item) || typeof item.i !== 'string') continue
    const { i, x, y, w, h } = item
    if (isGridInt(x, 0) && isGridInt(y, 0) && isGridInt(w, 1) && isGridInt(h, 1) && (x as number) < GRID_COLS) {
      layoutsById.set(i, { i, x, y, w: Math.min(w, GRID_COLS - x), h })
    }
  }

  const panes: Pane[] = []
  const layouts: PaneLayout[] = []
  const minimised: Record<string, number> = {}
  const seen = new Set<string>()
  let dropped = 0
  for (const item of raw.panes) {
    const valid =
      isObject(item) &&
      typeof item.id === 'string' &&
      /^[A-Za-z0-9_-]{1,64}$/.test(item.id) &&
      !seen.has(item.id) &&
      typeof item.type === 'string' &&
      getPaneDefinition(item.type) !== undefined &&
      typeof item.title === 'string' &&
      isObject(item.config) &&
      layoutsById.has(item.id)
    if (!valid) {
      dropped += 1
      continue
    }
    const pane = item as unknown as Pane
    seen.add(pane.id)
    panes.push({ id: pane.id, type: pane.type, title: pane.title, config: pane.config })
    const layout = layoutsById.get(pane.id)!
    const restore = minimisedRaw[pane.id]
    if (isGridInt(restore, 1)) {
      minimised[pane.id] = restore
      layouts.push({ ...layout, h: MINIMISED_HEIGHT })
    } else {
      layouts.push(layout)
    }
  }
  return { state: { panes, layouts, minimised }, dropped }
}

function getStorage(): Storage | null {
  try {
    return typeof window !== 'undefined' ? window.localStorage : null
  } catch {
    return null
  }
}

export function loadDashboard(): LoadResult {
  const storage = getStorage()
  let text: string | null = null
  try {
    text = storage?.getItem(STORAGE_KEY) ?? null
  } catch {
    return { state: defaultDashboard(), warning: 'Saved layout could not be read; using the default layout.' }
  }
  if (text === null) return { state: defaultDashboard() }

  try {
    const { state, dropped } = parseStoredDashboard(JSON.parse(text))
    if (dropped > 0) {
      return { state, warning: `${dropped} saved pane(s) could not be restored and were removed.` }
    }
    return { state }
  } catch (error) {
    console.warn('Invalid saved dashboard layout, using default', error)
    return { state: defaultDashboard(), warning: 'Saved layout was invalid; the default layout has been restored.' }
  }
}

// Save status as a tiny external store, so components can subscribe to it.
let lastSaveOk = true
const saveListeners = new Set<() => void>()

export function subscribeSaveStatus(listener: () => void): () => void {
  saveListeners.add(listener)
  return () => saveListeners.delete(listener)
}

export function getSaveStatus(): boolean {
  return lastSaveOk
}

function setSaveStatus(ok: boolean): void {
  if (ok === lastSaveOk) return
  lastSaveOk = ok
  saveListeners.forEach((listener) => listener())
}

/** Persist the dashboard. Returns false if storage is unavailable or full. */
export function saveDashboard(state: DashboardState): boolean {
  const doc: StoredDashboard = { version: LAYOUT_VERSION, ...state }
  let ok = false
  try {
    const storage = getStorage()
    if (storage) {
      storage.setItem(STORAGE_KEY, JSON.stringify(doc))
      ok = true
    }
  } catch (error) {
    console.warn('Could not save dashboard layout', error)
  }
  setSaveStatus(ok)
  return ok
}
