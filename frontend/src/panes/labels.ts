/** Automatic tab labels for the built-in pane types (pure functions). */
import type { Pane } from '../dashboard/types'
import { accountLabel } from '../hooks/useBrokerAccounts'
import { selectPortfolio } from '../hooks/usePortfolios'
import { readString } from './config'
import { describeSource, readStrategyConfig } from './strategy/config'
import type { LabelData } from './types'

/** Portfolio pane: the portfolio's name. */
export function portfolioLabel(pane: Pane, { portfolios }: LabelData): string | undefined {
  return selectPortfolio(portfolios, readString(pane.config, 'portfolioId'), ['watchlist']).portfolio?.name
}

/** Positions pane: "Positions · <account>" (the first account when none is chosen yet). */
export function positionsLabel(pane: Pane, { accounts }: LabelData): string | undefined {
  if (!accounts) return undefined
  const saved = readString(pane.config, 'accountId')
  const account = saved ? accounts.find((a) => a.id === saved) : accounts[0]
  return account ? `Positions · ${accountLabel(account)}` : undefined
}

/** Strategy pane: "<strategy> · <ticker source>", or "New strategy" before it is configured. */
export function strategyLabel(pane: Pane, { portfolios, strategies, accounts }: LabelData): string | undefined {
  const config = readStrategyConfig(pane.config)
  if (!config) return 'New strategy'
  const title = strategies?.find((s) => s.name === config.strategy)?.title
  const kind = config.source.kind
  if (!title || ((kind === 'portfolio' || kind === 'favourites') && !portfolios) || (kind === 'account' && !accounts)) {
    return undefined
  }
  return `${title} · ${describeSource(config.source, portfolios ?? [], accounts ?? [])}`
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
