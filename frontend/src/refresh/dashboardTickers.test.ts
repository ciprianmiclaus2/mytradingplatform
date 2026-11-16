import { describe, expect, it } from 'vitest'
import type { DashboardState } from '../dashboard/types'
import { dashboardExtraTickers } from './dashboardTickers'

const pane = (id: string, type: string, config: Record<string, unknown>) => ({ id, type, title: id, config })

describe('dashboardExtraTickers', () => {
  it('collects manual strategy tickers once, ignoring portfolio sources and other panes', () => {
    const state: DashboardState = {
      panes: [
        pane('a', 'strategy', { strategy: 'mr', params: {}, source: { kind: 'manual', tickers: ['NVDA', 'TSLA'] } }),
        pane('b', 'strategy', { strategy: 'mr', params: {}, source: { kind: 'manual', tickers: ['tsla', 'AMD'] } }),
        pane('c', 'strategy', { strategy: 'mr', params: {}, source: { kind: 'portfolio', portfolioId: 'p1' } }),
        pane('d', 'strategy', {}), // not configured yet
        pane('e', 'portfolio', { portfolioId: 'p1', tickers: ['IGNORED'] }),
      ],
      layouts: [],
      minimised: {},
    }
    expect(dashboardExtraTickers(state)).toEqual(['NVDA', 'TSLA', 'AMD'])
  })
})
