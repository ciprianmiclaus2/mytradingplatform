import { getPaneDefinition } from '../panes/registry'
import { defaultDashboard } from './defaults'
import { GRID_COLS, MINIMISED_HEIGHT } from './grid'
import type { DashboardState, Pane, PaneGroup, PaneLayout, StoredDashboard } from './types'
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

const ID_RE = /^[A-Za-z0-9_-]{1,64}$/
const isId = (v: unknown): v is string => typeof v === 'string' && ID_RE.test(v)

class InvalidLayout extends Error {}

/**
 * Version 1 had one pane per tile: layouts and minimised were keyed by pane id.
 * Each pane becomes a group of one, keyed `group-<pane id>`.
 */
function migrateV1(raw: Record<string, unknown>): Record<string, unknown> {
  if (!Array.isArray(raw.panes) || !Array.isArray(raw.layouts)) throw new InvalidLayout('panes/layouts missing')
  const groupIdFor = (paneId: string) => `group-${paneId}`.slice(0, 64)
  const panes = raw.panes.filter(isObject)
  const minimised = isObject(raw.minimised) ? raw.minimised : {}
  return {
    version: LAYOUT_VERSION,
    panes: raw.panes,
    groups: panes.filter((p) => isId(p.id)).map((p) => ({ id: groupIdFor(p.id as string), paneIds: [p.id], active: p.id })),
    layouts: raw.layouts.filter(isObject).map((l) => (typeof l.i === 'string' ? { ...l, i: groupIdFor(l.i) } : l)),
    minimised: Object.fromEntries(Object.entries(minimised).map(([id, h]) => [groupIdFor(id), h])),
  }
}

/**
 * Validate a stored document. Structural problems (unknown version, wrong
 * shapes) reject the whole document; individual panes that are unusable
 * (unknown type, bad id, not in a valid tile) are dropped and counted.
 */
export function parseStoredDashboard(input: unknown): { state: DashboardState; dropped: number } {
  if (!isObject(input)) throw new InvalidLayout('not an object')
  const raw = input.version === 1 ? migrateV1(input) : input
  if (raw.version !== LAYOUT_VERSION) throw new InvalidLayout(`unsupported version ${String(raw.version)}`)
  if (!Array.isArray(raw.panes) || !Array.isArray(raw.groups) || !Array.isArray(raw.layouts)) {
    throw new InvalidLayout('panes/groups/layouts missing')
  }
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

  // Valid panes, by id.
  const paneById = new Map<string, Pane>()
  let candidates = 0
  for (const item of raw.panes) {
    candidates += 1
    if (
      isObject(item) &&
      isId(item.id) &&
      !paneById.has(item.id) &&
      typeof item.type === 'string' &&
      getPaneDefinition(item.type) !== undefined &&
      typeof item.title === 'string' &&
      isObject(item.config)
    ) {
      paneById.set(item.id, { id: item.id, type: item.type, title: item.title, config: item.config })
    }
  }

  // Groups: known, unassigned panes only; each needs a valid tile.
  const groups: PaneGroup[] = []
  const layouts: PaneLayout[] = []
  const minimised: Record<string, number> = {}
  const assigned = new Set<string>()
  const groupIds = new Set<string>()
  for (const item of raw.groups) {
    if (!isObject(item) || !isId(item.id) || groupIds.has(item.id) || !Array.isArray(item.paneIds)) continue
    const layout = layoutsById.get(item.id)
    if (!layout) continue
    const paneIds = item.paneIds.filter((id): id is string => typeof id === 'string' && paneById.has(id) && !assigned.has(id))
    if (paneIds.length === 0) continue
    paneIds.forEach((id) => assigned.add(id))
    groupIds.add(item.id)
    const active = typeof item.active === 'string' && paneIds.includes(item.active) ? item.active : paneIds[0]
    groups.push({ id: item.id, paneIds, active })
    const restore = minimisedRaw[item.id]
    if (isGridInt(restore, 1)) {
      minimised[item.id] = restore
      layouts.push({ ...layout, h: MINIMISED_HEIGHT })
    } else {
      layouts.push(layout)
    }
  }

  // Panes in tab order of their groups; anything not in a valid group is dropped.
  const panes = groups.flatMap((g) => g.paneIds.map((id) => paneById.get(id)!))
  return { state: { panes, groups, layouts, minimised }, dropped: candidates - panes.length }
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
