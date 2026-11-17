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

export type PortfolioType = 'watchlist'

export interface Portfolio {
  id: string
  name: string
  description: string
  type: PortfolioType
  tickers: string[]
  favourites: string[]
  created_at: string
  updated_at: string
}

export interface QuoteRow {
  ticker: string
  /** Company or fund name, when known (shown on hover). */
  name?: string | null
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

// -- Broker accounts (SnapTrade) ---------------------------------------------------

/** What the UI may know about the stored SnapTrade credentials (never the secrets). */
export interface SnapTradeStatus {
  configured: boolean
  /** Personal API key (no SnapTrade user); null when not set up. */
  personal: boolean | null
  client_id: string | null
  user_id: string | null
  /** Last 4 characters ('' for short values). */
  consumer_key_hint: string | null
  user_secret_hint: string | null
}

/** Personal API key: client ID and consumer key only (user fields blank). Commercial keys add the user. */
export interface SnapTradeCredentials {
  client_id: string
  consumer_key: string
  user_id: string
  user_secret: string
}

export interface BrokerAccount {
  id: string
  name: string
  /** Masked, e.g. ****8443 */
  number: string
  status: string | null
  kind: string
  net_value: number | null
  net_value_currency: string | null
  listed_at: string
  /** Last successful positions refresh (by this app). */
  positions_refreshed_at: string | null
  /** When SnapTrade fetched the data from the broker. */
  data_as_of: string | null
}

export interface BrokerAccountView extends BrokerAccount {
  /** Market data tickers held at the last refresh. */
  tickers: string[]
}

export interface BrokerAccounts {
  configured: boolean
  accounts: BrokerAccountView[]
  accounts_refreshed_at: string | null
}

export type PriceSource = 'market' | 'broker'

export interface BrokerPositionView {
  symbol: string
  ticker: string | null
  description: string | null
  kind: string
  currency: string | null
  quantity: number
  average_cost: number | null
  cost_basis: number | null
  current_price: number | null
  /** 'market': live quote; 'broker': the broker's price at the last refresh. */
  price_source: PriceSource | null
  price_timestamp: string | null
  previous_close: number | null
  market_value: number | null
  daily_change: number | null
  /** Percent units. */
  daily_change_pct: number | null
  daily_pnl: number | null
  unrealised_pnl: number | null
  /** Percent units. */
  unrealised_pnl_pct: number | null
  stale: boolean
}

export interface BrokerCurrencyTotals {
  currency: string
  positions: number
  market_value: number | null
  cost_basis: number | null
  unrealised_pnl: number | null
  unrealised_pnl_pct: number | null
  daily_pnl: number | null
  /** Some positions lack a price, cost or daily change and are left out. */
  incomplete: boolean
}

export interface BrokerPositionsResponse {
  account: BrokerAccount
  positions: BrokerPositionView[]
  totals: BrokerCurrencyTotals[]
}

export interface AccountRefreshError {
  account_id: string
  account_name: string
  message: string
}

export interface BrokerRefreshResult {
  accounts: BrokerAccountView[]
  errors: AccountRefreshError[]
  accounts_refreshed_at: string
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
  /** Company or fund name, when known (shown on hover). */
  name?: string | null
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
