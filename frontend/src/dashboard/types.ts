/** A dashboard pane instance. Layout (position/size) is stored separately. */
export interface Pane {
  id: string
  type: string
  title: string
  config: Record<string, unknown>
}

/** Grid position and size of a pane, in grid units. `i` is the pane id. */
export interface PaneLayout {
  i: string
  x: number
  y: number
  w: number
  h: number
}

export interface DashboardState {
  panes: Pane[]
  layouts: PaneLayout[]
  /** Minimised panes: pane id -> height to restore. */
  minimised: Record<string, number>
}

export const LAYOUT_VERSION = 1

/** Persisted document in localStorage. */
export interface StoredDashboard extends DashboardState {
  version: typeof LAYOUT_VERSION
}
