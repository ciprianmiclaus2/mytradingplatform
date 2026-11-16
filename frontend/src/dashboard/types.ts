/** A dashboard pane instance. Its tile (group) and position are stored separately. */
export interface Pane {
  id: string
  type: string
  /** Fallback title ("Strategy 2"); tabs show an automatic label when data is available. */
  title: string
  config: Record<string, unknown>
}

/**
 * A grid tile: one or more panes shown as tabs. A single pane is a group of
 * one. `paneIds` is the tab order; `active` is the visible tab.
 */
export interface PaneGroup {
  id: string
  paneIds: string[]
  active: string
}

/** Grid position and size of a group, in grid units. `i` is the group id. */
export interface PaneLayout {
  i: string
  x: number
  y: number
  w: number
  h: number
}

export interface DashboardState {
  panes: Pane[]
  groups: PaneGroup[]
  layouts: PaneLayout[]
  /** Minimised groups: group id -> height to restore. */
  minimised: Record<string, number>
}

/** Version 2 adds tab groups. Version 1 layouts (one pane per tile) are migrated on load. */
export const LAYOUT_VERSION = 2

/** Persisted document in localStorage. */
export interface StoredDashboard extends DashboardState {
  version: typeof LAYOUT_VERSION
}
