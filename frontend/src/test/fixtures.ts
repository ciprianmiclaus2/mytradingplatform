import type { Portfolio, PositionView, QuoteRow, StrategySchema, TickerResult } from '../types/api'

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

export function position(overrides: Partial<PositionView> = {}): PositionView {
  return {
    id: 'pos-1',
    portfolio_id: 'pf-pos',
    ticker: 'AAPL',
    currency: 'USD',
    status: 'OPEN',
    quantity: 10,
    entry_price: 100,
    entry_date: '2026-01-02',
    notes: '',
    cost_basis: 1000,
    current_price: 110,
    previous_close: 108,
    price_timestamp: stamp,
    market_value: 1100,
    unrealised_pnl: 100,
    unrealised_pnl_pct: 10,
    daily_change: 2,
    daily_change_pct: 1.85,
    daily_pnl: 20,
    stale: false,
    exit_price: null,
    exit_date: null,
    realised_pnl: null,
    realised_pnl_pct: null,
    created_at: stamp,
    updated_at: stamp,
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
