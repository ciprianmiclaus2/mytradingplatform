import { describe, expect, it } from 'vitest'
import type { Pane } from '../dashboard/types'
import { brokerAccount, meanReversionSchema, portfolio } from '../test/fixtures'
import { paneLabels, portfolioLabel, positionsLabel, strategyLabel } from './labels'

const pane = (type: string, config: Record<string, unknown> = {}, id = 'p'): Pane => ({ id, type, title: 'Fallback', config })
const portfolios = [portfolio(), portfolio({ id: 'pf-two', name: 'Tech' })]
const accounts = [brokerAccount(), brokerAccount({ id: 'acc-2', name: 'ISA', number: '' })]
const data = { portfolios, strategies: [meanReversionSchema], accounts }
const none = { portfolios: undefined, strategies: undefined, accounts: undefined }

describe('pane labels', () => {
  it('names portfolio panes after the shown portfolio', () => {
    expect(portfolioLabel(pane('portfolio'), data)).toBe('Main Portfolio') // first, when none chosen
    expect(portfolioLabel(pane('portfolio', { portfolioId: 'pf-two' }), data)).toBe('Tech')
    expect(portfolioLabel(pane('portfolio', { portfolioId: 'gone' }), data)).toBeUndefined()
    expect(portfolioLabel(pane('portfolio'), none)).toBeUndefined()
  })

  it('names positions panes after the broker account', () => {
    expect(positionsLabel(pane('positions'), data)).toBe('Positions · Brokerage ****1234') // first, when none chosen
    expect(positionsLabel(pane('positions', { accountId: 'acc-2' }), data)).toBe('Positions · ISA')
    expect(positionsLabel(pane('positions', { accountId: 'gone' }), data)).toBeUndefined()
    expect(positionsLabel(pane('positions'), { ...data, accounts: [] })).toBeUndefined() // SnapTrade not set up
    expect(positionsLabel(pane('positions'), none)).toBeUndefined()
  })

  it('names strategy panes after the strategy and ticker source', () => {
    const configured = (source: object) => pane('strategy', { strategy: 'mean_reversion', params: {}, source })
    expect(strategyLabel(pane('strategy'), none)).toBe('New strategy')
    expect(strategyLabel(configured({ kind: 'portfolio', portfolioId: 'pf-main' }), data)).toBe('Mean Reversion · Main Portfolio')
    expect(strategyLabel(configured({ kind: 'favourites', portfolioId: 'pf-main' }), data)).toBe('Mean Reversion · Main Portfolio favourites')
    expect(strategyLabel(configured({ kind: 'manual', tickers: ['A', 'B', 'C'] }), data)).toBe('Mean Reversion · 3 manual tickers')
    expect(strategyLabel(configured({ kind: 'account', accountId: 'acc-2' }), data)).toBe('Mean Reversion · ISA')
    expect(strategyLabel(configured({ kind: 'account', accountId: 'gone' }), data)).toBe('Mean Reversion · missing account')
    expect(strategyLabel(configured({ kind: 'account', accountId: 'acc-2' }), { ...data, accounts: undefined })).toBeUndefined()
    expect(strategyLabel(configured({ kind: 'manual', tickers: ['A'] }), none)).toBeUndefined() // strategies not loaded
  })

  it('numbers duplicates within a tile only', () => {
    const panes = [pane('x', {}, 'a'), pane('x', {}, 'b'), pane('x', {}, 'c'), pane('x', {}, 'd')]
    const labels = paneLabels(panes, [{ paneIds: ['a', 'b', 'c'] }, { paneIds: ['d'] }], () => 'RSI · Tech')
    expect(labels).toEqual({ a: 'RSI · Tech', b: 'RSI · Tech (2)', c: 'RSI · Tech (3)', d: 'RSI · Tech' })
  })
})
