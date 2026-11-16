import { createPane } from './reducer'
import type { DashboardState } from './types'

/** Layout used on first start, after a reset, or when the saved layout is unusable. */
export function defaultDashboard(): DashboardState {
  let state: DashboardState = { panes: [], layouts: [], minimised: {} }
  state = createPane(state, 'portfolio')
  state = createPane(state, 'positions')
  // Place the first two panes side by side.
  const [first, second] = state.layouts
  state.layouts = [
    { ...first, x: 0, y: 0 },
    { ...second, x: first.w, y: 0 },
  ]
  return state
}
