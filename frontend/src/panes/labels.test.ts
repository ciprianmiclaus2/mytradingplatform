import { describe, expect, it } from 'vitest'
import type { Pane } from '../dashboard/types'
import { meanReversionSchema, portfolio } from '../test/fixtures'
import { paneLabels, portfolioLabel, positionsLabel, strategyLabel } from './labels'

const pane = (type: string, config: Record<string, unknown> = {}, id = 'p'): Pane => ({ id, type, title: 'Fallback', config })
const portfolios = [portfolio(), portfolio({ id: 'pf-pos', name: 'IBKR', type: 'positions' })]
const data = { portfolios, strategies: [meanReversionSchema] }
const none = { portfolios: undefined, strategies: undefined }

describe('pane labels', () => {
  it('names portfolio panes after the shown portfolio', () => {
    expect(portfolioLabel(pane('portfolio'), data)).toBe('Main Portfolio') // first, when none chosen
    expect(portfolioLabel(pane('portfolio', { portfolioId: 'pf-pos' }), data)).toBe('IBKR')
    expect(portfolioLabel(pane('portfolio', { portfolioId: 'gone' }), data)).toBeUndefined()
    expect(portfolioLabel(pane('portfolio'), none)).toBeUndefined()
  })

  it('names positions panes after the positions list', () => {
    expect(positionsLabel(pane('positions'), data)).toBe('Positions · IBKR')
  })

  it('names strategy panes after the strategy and ticker source', () => {
    const configured = (source: object) => pane('strategy', { strategy: 'mean_reversion', params: {}, source })
    expect(strategyLabel(pane('strategy'), none)).toBe('New strategy')
    expect(strategyLabel(configured({ kind: 'portfolio', portfolioId: 'pf-main' }), data)).toBe('Mean Reversion · Main Portfolio')
    expect(strategyLabel(configured({ kind: 'favourites', portfolioId: 'pf-main' }), data)).toBe('Mean Reversion · Main Portfolio favourites')
    expect(strategyLabel(configured({ kind: 'manual', tickers: ['A', 'B', 'C'] }), data)).toBe('Mean Reversion · 3 manual tickers')
    expect(strategyLabel(configured({ kind: 'manual', tickers: ['A'] }), none)).toBeUndefined() // strategies not loaded
  })

  it('numbers duplicates within a tile only', () => {
    const panes = [pane('x', {}, 'a'), pane('x', {}, 'b'), pane('x', {}, 'c'), pane('x', {}, 'd')]
    const labels = paneLabels(panes, [{ paneIds: ['a', 'b', 'c'] }, { paneIds: ['d'] }], () => 'RSI · Tech')
    expect(labels).toEqual({ a: 'RSI · Tech', b: 'RSI · Tech (2)', c: 'RSI · Tech (3)', d: 'RSI · Tech' })
  })
})
