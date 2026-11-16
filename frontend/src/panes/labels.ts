/** Automatic tab labels for the built-in pane types (pure functions). */
import type { Pane } from '../dashboard/types'
import { selectPortfolio } from '../hooks/usePortfolios'
import { readString } from './config'
import { describeSource, readStrategyConfig } from './strategy/config'
import type { LabelData } from './types'

/** Portfolio pane: the portfolio's name. */
export function portfolioLabel(pane: Pane, { portfolios }: LabelData): string | undefined {
  return selectPortfolio(portfolios, readString(pane.config, 'portfolioId'), ['watchlist', 'positions']).portfolio?.name
}

/** Positions pane: "Positions · <list name>". */
export function positionsLabel(pane: Pane, { portfolios }: LabelData): string | undefined {
  const name = selectPortfolio(portfolios, readString(pane.config, 'portfolioId'), ['positions']).portfolio?.name
  return name ? `Positions · ${name}` : undefined
}

/** Strategy pane: "<strategy> · <ticker source>", or "New strategy" before it is configured. */
export function strategyLabel(pane: Pane, { portfolios, strategies }: LabelData): string | undefined {
  const config = readStrategyConfig(pane.config)
  if (!config) return 'New strategy'
  const title = strategies?.find((s) => s.name === config.strategy)?.title
  if (!title || (config.source.kind !== 'manual' && !portfolios)) return undefined
  return `${title} · ${describeSource(config.source, portfolios ?? [])}`
}

/**
 * Labels for every pane. Within one tile, identical labels are numbered
 * ("RSI · Main Portfolio", "RSI · Main Portfolio (2)") so tabs stay distinct.
 */
export function paneLabels(
  panes: Pane[],
  groups: { paneIds: string[] }[],
  labelFor: (pane: Pane) => string,
): Record<string, string> {
  const byId = new Map(panes.map((p) => [p.id, p]))
  const labels: Record<string, string> = {}
  for (const group of groups) {
    const seen = new Map<string, number>()
    for (const id of group.paneIds) {
      const pane = byId.get(id)
      if (!pane) continue
      const base = labelFor(pane)
      const n = (seen.get(base) ?? 0) + 1
      seen.set(base, n)
      labels[id] = n === 1 ? base : `${base} (${n})`
    }
  }
  return labels
}
