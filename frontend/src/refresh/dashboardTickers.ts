import type { DashboardState } from '../dashboard/types'
import { readStrategyConfig } from '../panes/strategy/config'

/**
 * Tickers the backend cannot know about: strategy panes live in the browser,
 * so their manually entered tickers are sent with the refresh request.
 * (Portfolio-based sources are already covered by the backend.)
 */
export function dashboardExtraTickers(state: DashboardState): string[] {
  const tickers = new Set<string>()
  for (const pane of state.panes) {
    if (pane.type !== 'strategy') continue
    const config = readStrategyConfig(pane.config)
    if (config?.source.kind === 'manual') config.source.tickers.forEach((t) => tickers.add(t))
  }
  return [...tickers]
}
