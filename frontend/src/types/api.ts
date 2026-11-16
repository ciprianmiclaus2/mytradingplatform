/** Error envelope returned by every backend error response. */
export interface ApiErrorEnvelope {
  error: {
    code: string
    message: string
    details?: unknown
  }
}

export interface HealthResponse {
  status: string
  version: string
  environment: string
  data_schema_version: number
  market_data_provider: string
  server_time: string
}

// -- Portfolios -------------------------------------------------------------------

export type PortfolioType = 'watchlist' | 'positions'

export interface Portfolio {
  id: string
  name: string
  description: string
  type: PortfolioType
  /** Watchlist: maintained by the user. Positions: tickers of open positions. */
  tickers: string[]
  favourites: string[]
  created_at: string
  updated_at: string
}

export interface QuoteRow {
  ticker: string
  favourite: boolean
  price: number | null
  currency: string | null
  previous_close: number | null
  daily_change: number | null
  /** Percent units (1.5 means 1.5%). */
  daily_change_pct: number | null
  timestamp: string | null
  delayed: boolean | null
  stale: boolean
  last_error: string | null
}

export interface PortfolioQuotes {
  portfolio_id: string
  rows: QuoteRow[]
}

// -- Positions --------------------------------------------------------------------

export type PositionStatus = 'OPEN' | 'CLOSED'

export interface PositionView {
  id: string
  portfolio_id: string
  ticker: string
  currency: string
  status: PositionStatus
  quantity: number
  entry_price: number
  entry_date: string | null
  notes: string
  cost_basis: number
  current_price: number | null
  previous_close: number | null
  price_timestamp: string | null
  market_value: number | null
  unrealised_pnl: number | null
  unrealised_pnl_pct: number | null
  daily_change: number | null
  daily_change_pct: number | null
  daily_pnl: number | null
  stale: boolean
  exit_price: number | null
  exit_date: string | null
  realised_pnl: number | null
  realised_pnl_pct: number | null
  created_at: string
  updated_at: string
}

export interface CurrencyTotals {
  currency: string
  open_positions: number
  closed_positions: number
  market_value: number | null
  cost_basis: number
  unrealised_pnl: number | null
  unrealised_pnl_pct: number | null
  daily_pnl: number | null
  realised_pnl: number
  incomplete: boolean
}

export interface PositionsResponse {
  portfolio_id: string
  positions: PositionView[]
  totals: CurrencyTotals[]
}

/** Decimal values are sent as strings so they reach the backend exactly. */
export interface PositionCreate {
  ticker: string
  quantity: string
  entry_price?: string
  entry_date?: string
  notes?: string
}

export interface PositionUpdate {
  quantity?: string
  entry_price?: string
  entry_date?: string
  exit_price?: string
  exit_date?: string
  notes?: string
}

export interface PositionClose {
  exit_price?: string
  exit_date?: string
}

// -- Market data ------------------------------------------------------------------

export interface TickerSearchResult {
  ticker: string
  name: string
  exchange: string | null
  currency: string | null
  instrument_type: string
  provider: string
}

// -- Strategies -------------------------------------------------------------------

export type ParameterType = 'integer' | 'number' | 'string' | 'boolean'
export type ParameterValue = number | string | boolean

export interface StrategyParameter {
  name: string
  type: ParameterType
  title: string
  description: string
  default: ParameterValue
  minimum: number | null
  maximum: number | null
  choices: string[] | null
}

export type OutputFormat = 'price' | 'number' | 'percent' | 'integer' | 'text'

export interface OutputColumn {
  name: string
  title: string
  format: OutputFormat
  description: string
}

export interface StrategySchema {
  name: string
  title: string
  description: string
  /** User-facing explanation: paragraphs separated by blank lines, '## ' headings, '- ' bullets. */
  explanation: string
  parameters: StrategyParameter[]
  outputs: OutputColumn[]
}

export type Signal = 'BUY' | 'SELL'
export type CalculationStatus = 'OK' | 'NO_PRICE' | 'INSUFFICIENT_DATA' | 'INVALID_CALCULATION' | 'DATA_ERROR'

export interface TickerResult {
  ticker: string
  status: CalculationStatus
  signal: Signal | null
  message: string | null
  current_price: number | null
  currency: string | null
  daily_change: number | null
  daily_change_pct: number | null
  price_timestamp: string | null
  stale: boolean
  metrics: Record<string, number | null>
  previous_signal: Signal | null
  signal_changed_at: string | null
  is_new_signal: boolean
}

export interface StrategyRunResult {
  strategy: string
  instance_id: string | null
  config: Record<string, ParameterValue>
  calculated_at: string
  results: TickerResult[]
}

// -- Market data refresh ------------------------------------------------------------

export type RefreshOutcome = 'completed' | 'partial' | 'failed'

export interface TickerError {
  ticker: string
  code: string
  message: string
}

export interface RefreshResult {
  status: RefreshOutcome
  started_at: string
  completed_at: string
  tickers_requested: number
  tickers_updated: number
  tickers_failed: number
  errors: TickerError[]
}

export interface MarketDataStatus {
  provider: string
  last_refresh: RefreshResult | null
  last_successful_refresh_at: string | null
}
