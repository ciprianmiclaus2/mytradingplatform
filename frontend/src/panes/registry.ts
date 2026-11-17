import { portfolioLabel, positionsLabel, strategyLabel } from './labels'
import { PortfolioPane } from './PortfolioPane'
import { BrokerPositionsPane } from './broker/BrokerPositionsPane'
import { POSITIONS_PANE } from './broker/constants'
import { StrategyPane } from './strategy/StrategyPane'
import type { PaneDefinition } from './types'

/**
 * Available pane types. Adding a pane type means adding one entry here;
 * the dashboard, menus and persistence are generic.
 */
const definitions: PaneDefinition[] = [
  {
    type: 'portfolio',
    title: 'Portfolio',
    description: 'Prices and daily change for a watchlist',
    component: PortfolioPane,
    defaultSize: { w: 6, h: 10 },
    minSize: { w: 3, h: 4 },
    defaultConfig: () => ({}),
    label: portfolioLabel,
  },
  {
    type: POSITIONS_PANE,
    title: 'Positions',
    description: 'A broker account\'s positions (via SnapTrade) with valuation and P&L',
    component: BrokerPositionsPane,
    defaultSize: { w: 6, h: 10 },
    minSize: { w: 4, h: 4 },
    defaultConfig: () => ({}),
    label: positionsLabel,
  },
  {
    type: 'strategy',
    title: 'Strategy',
    description: 'Strategy metrics and signals',
    component: StrategyPane,
    defaultSize: { w: 12, h: 12 },
    minSize: { w: 4, h: 4 },
    defaultConfig: () => ({}),
    label: strategyLabel,
  },
]

export const paneRegistry: ReadonlyMap<string, PaneDefinition> = new Map(definitions.map((d) => [d.type, d]))

export function paneDefinitions(): PaneDefinition[] {
  return definitions
}

export function getPaneDefinition(type: string): PaneDefinition | undefined {
  return paneRegistry.get(type)
}
