/** Yahoo Finance quote page for a market data ticker (e.g. AAPL, VOD.L, BRK-B, BTC-USD). */
export function yahooQuoteUrl(ticker: string): string {
  return `https://finance.yahoo.com/quote/${encodeURIComponent(ticker)}/`
}

/**
 * The Yahoo ticker for a broker position, or null when Yahoo has no page for it.
 * Listed holdings use their mapped market data ticker; options use the OCC
 * symbol without its padding spaces (Yahoo's option format, e.g. AAPL261218C00240000).
 */
export function yahooTickerForPosition(position: { ticker: string | null; symbol: string; kind: string }): string | null {
  if (position.ticker) return position.ticker
  if (position.kind === 'option') {
    const compact = position.symbol.replace(/\s+/g, '')
    return /^[A-Z0-9.]{1,6}\d{6}[CP]\d{8}$/.test(compact) ? compact : null
  }
  return null
}
