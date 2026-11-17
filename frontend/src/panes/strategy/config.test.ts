import { describe, expect, it } from 'vitest'
import { meanReversionSchema, portfolio } from '../../test/fixtures'
import { initialFormValues, parseTickerList, readStrategyConfig, resolveTickers, validateParameters } from './config'

const params = meanReversionSchema.parameters

describe('strategy pane config', () => {
  it('parses manual ticker lists', () => {
    expect(parseTickerList('aapl, msft;vod.l  AAPL\nbrk-b')).toEqual({ tickers: ['AAPL', 'MSFT', 'VOD.L', 'BRK-B'], invalid: [] })
    expect(parseTickerList('ok, bad$, .x').invalid).toEqual(['bad$', '.x'])
    expect(parseTickerList('^ftse, ^GSPC, ^^x, ^').tickers).toEqual(['^FTSE', '^GSPC'])
  })

  it('reads saved configurations defensively', () => {
    expect(readStrategyConfig({})).toBeUndefined()
    expect(readStrategyConfig({ strategy: 'x', source: { kind: 'nope' } })).toBeUndefined()
    expect(
      readStrategyConfig({ strategy: 'x', params: { a: 1, b: { bad: true } }, source: { kind: 'manual', tickers: ['aapl', 3] } }),
    ).toEqual({ strategy: 'x', params: { a: 1 }, source: { kind: 'manual', tickers: ['AAPL'] } })
  })

  it('resolves tickers from a portfolio, its favourites, or a manual list', () => {
    const list = [portfolio({ tickers: ['A', 'B'], favourites: ['B'] })]
    expect(resolveTickers({ kind: 'portfolio', portfolioId: 'pf-main' }, list).tickers).toEqual(['A', 'B'])
    expect(resolveTickers({ kind: 'favourites', portfolioId: 'pf-main' }, list).tickers).toEqual(['B'])
    expect(resolveTickers({ kind: 'manual', tickers: ['C'] }, list).tickers).toEqual(['C'])
    expect(resolveTickers({ kind: 'portfolio', portfolioId: 'gone' }, list).error).toMatch(/no longer exists/)
  })

  it('fills form values from defaults and saved values', () => {
    expect(initialFormValues(params, {})).toEqual({ lookback_days: '20', buy_threshold: '-2', sell_threshold: '2' })
    expect(initialFormValues(params, { lookback_days: 50 }).lookback_days).toBe('50')
  })

  it('validates types and ranges from the schema', () => {
    const ok = validateParameters(params, { lookback_days: '30', buy_threshold: '-1.5', sell_threshold: '1.5' })
    expect(ok).toEqual({ params: { lookback_days: 30, buy_threshold: -1.5, sell_threshold: 1.5 }, errors: {} })

    const bad = validateParameters(params, { lookback_days: '2.5', buy_threshold: '', sell_threshold: 'abc' })
    expect(bad.errors).toEqual({ lookback_days: 'Must be a whole number', buy_threshold: 'Required', sell_threshold: 'Must be a number' })
    expect(validateParameters(params, { lookback_days: '1', buy_threshold: '0', sell_threshold: '1' }).errors.lookback_days).toBe('Must be at least 2')
    expect(validateParameters(params, { lookback_days: '501', buy_threshold: '0', sell_threshold: '1' }).errors.lookback_days).toBe('Must be at most 500')
  })

  it('handles string and boolean parameters', () => {
    const extra = [
      { name: 'mode', type: 'string' as const, title: 'Mode', description: '', default: 'fast', minimum: null, maximum: null, choices: ['fast', 'slow'] },
      { name: 'flag', type: 'boolean' as const, title: 'Flag', description: '', default: true, minimum: null, maximum: null, choices: null },
    ]
    expect(initialFormValues(extra, {})).toEqual({ mode: 'fast', flag: true })
    expect(validateParameters(extra, { mode: 'slow', flag: false })).toEqual({ params: { mode: 'slow', flag: false }, errors: {} })
    expect(validateParameters(extra, { mode: 'other', flag: true }).errors.mode).toMatch(/Choose one of/)
  })
})
