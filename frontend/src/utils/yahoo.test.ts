import { describe, expect, it } from 'vitest'
import { yahooQuoteUrl, yahooTickerForPosition } from './yahoo'

describe('Yahoo Finance links', () => {
  it('builds quote URLs, escaping special characters', () => {
    expect(yahooQuoteUrl('BRK-B')).toBe('https://finance.yahoo.com/quote/BRK-B/')
    expect(yahooQuoteUrl('^GSPC')).toBe('https://finance.yahoo.com/quote/%5EGSPC/')
    expect(yahooQuoteUrl('A&B')).toBe('https://finance.yahoo.com/quote/A%26B/')
  })

  it('picks the Yahoo ticker for broker positions', () => {
    expect(yahooTickerForPosition({ ticker: 'VOD.L', symbol: 'VOD', kind: 'stock' })).toBe('VOD.L')
    expect(yahooTickerForPosition({ ticker: null, symbol: 'AAPL  261218C00240000', kind: 'option' })).toBe('AAPL261218C00240000')
    expect(yahooTickerForPosition({ ticker: null, symbol: 'weird option', kind: 'option' })).toBeNull()
    expect(yahooTickerForPosition({ ticker: null, symbol: 'USD', kind: 'cash' })).toBeNull()
  })
})
