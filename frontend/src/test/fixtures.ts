import type { BrokerAccountView, BrokerPositionView, Portfolio, QuoteRow, StrategySchema, TickerResult } from '../types/api'

export const health = {
  status: 'ok',
  version: '0.1.0',
  environment: 'development',
  data_schema_version: 1,
  market_data_provider: 'yfinance',
  server_time: '2026-11-16T12:00:00Z',
}

const stamp = '2026-11-16T12:00:00Z'

export function portfolio(overrides: Partial<Portfolio> = {}): Portfolio {
  return {
    id: 'pf-main',
    name: 'Main Portfolio',
    description: '',
    type: 'watchlist',
    tickers: [],
    favourites: [],
    created_at: stamp,
    updated_at: stamp,
    ...overrides,
  }
}

export function quote(ticker: string, overrides: Partial<QuoteRow> = {}): QuoteRow {
  return {
    ticker,
    favourite: false,
    price: 100,
    currency: 'USD',
    previous_close: 99,
    daily_change: 1,
    daily_change_pct: 1.0101,
    timestamp: stamp,
    delayed: false,
    stale: false,
    last_error: null,
    ...overrides,
  }
}

export function brokerAccount(overrides: Partial<BrokerAccountView> = {}): BrokerAccountView {
  return {
    id: 'acc-1',
    name: 'Brokerage',
    number: '****1234',
    status: 'open',
    kind: 'investment',
    net_value: 1100,
    net_value_currency: 'USD',
    listed_at: stamp,
    positions_refreshed_at: stamp,
    data_as_of: '2026-11-16T11:30:00Z',
    tickers: ['AAPL'],
    ...overrides,
  }
}

export function brokerPosition(overrides: Partial<BrokerPositionView> = {}): BrokerPositionView {
  return {
    symbol: 'AAPL',
    ticker: 'AAPL',
    description: 'Apple Inc',
    kind: 'stock',
    currency: 'USD',
    quantity: 10,
    average_cost: 100,
    cost_basis: 1000,
    current_price: 110,
    price_source: 'market',
    price_timestamp: stamp,
    previous_close: 108,
    market_value: 1100,
    daily_change: 2,
    daily_change_pct: 1.85,
    daily_pnl: 20,
    unrealised_pnl: 100,
    unrealised_pnl_pct: 10,
    stale: false,
    ...overrides,
  }
}

export const meanReversionSchema: StrategySchema = {
  name: 'mean_reversion',
  title: 'Mean Reversion',
  description: 'Z-score of the price against the recent mean.',
  explanation: 'Mean reversion assumes prices return to their average.\n\n## Signals\n\n- BUY when the z-score is low.\n- SELL when it is high.',
  parameters: [
    { name: 'lookback_days', type: 'integer', title: 'Lookback (sessions)', description: 'Number of sessions', default: 20, minimum: 2, maximum: 500, choices: null },
    { name: 'buy_threshold', type: 'number', title: 'Buy threshold (Z)', description: 'BUY at or below', default: -2, minimum: null, maximum: null, choices: null },
    { name: 'sell_threshold', type: 'number', title: 'Sell threshold (Z)', description: 'SELL at or above', default: 2, minimum: null, maximum: null, choices: null },
  ],
  outputs: [
    { name: 'mean', title: 'Mean', format: 'price', description: 'Mean of the previous closes' },
    { name: 'standard_deviation', title: 'Std Dev', format: 'price', description: 'Population standard deviation' },
    { name: 'z_score', title: 'Z-Score', format: 'number', description: 'Z-score' },
  ],
}

export function tickerResult(ticker: string, overrides: Partial<TickerResult> = {}): TickerResult {
  return {
    ticker,
    status: 'OK',
    signal: null,
    message: null,
    current_price: 100,
    currency: 'USD',
    daily_change: 1,
    daily_change_pct: 1,
    price_timestamp: stamp,
    stale: false,
    metrics: { mean: 105, standard_deviation: 2.5, z_score: -2 },
    previous_signal: null,
    signal_changed_at: null,
    is_new_signal: false,
    ...overrides,
  }
}
