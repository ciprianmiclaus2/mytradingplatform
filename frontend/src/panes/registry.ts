import { PlaceholderPane } from './PlaceholderPane'
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
    component: PlaceholderPane,
    defaultSize: { w: 6, h: 10 },
    minSize: { w: 3, h: 4 },
    defaultConfig: () => ({}),
  },
  {
    type: 'positions',
    title: 'Positions',
    description: 'Positions with valuation and P&L',
    component: PlaceholderPane,
    defaultSize: { w: 6, h: 10 },
    minSize: { w: 4, h: 4 },
    defaultConfig: () => ({}),
  },
  {
    type: 'strategy',
    title: 'Strategy',
    description: 'Strategy metrics and signals',
    component: PlaceholderPane,
    defaultSize: { w: 12, h: 10 },
    minSize: { w: 4, h: 4 },
    defaultConfig: () => ({}),
  },
]

export const paneRegistry: ReadonlyMap<string, PaneDefinition> = new Map(definitions.map((d) => [d.type, d]))

export function paneDefinitions(): PaneDefinition[] {
  return definitions
}

export function getPaneDefinition(type: string): PaneDefinition | undefined {
  return paneRegistry.get(type)
}
