import type { ParameterValue, Portfolio, StrategyParameter } from '../../types/api'
import { readObject, readString } from '../config'

export type TickerSource =
  | { kind: 'portfolio'; portfolioId: string }
  | { kind: 'favourites'; portfolioId: string }
  | { kind: 'manual'; tickers: string[] }

export interface StrategyPaneConfig {
  strategy: string
  params: Record<string, ParameterValue>
  source: TickerSource
}

/** Same rule as the backend (app/market_data/models.py). */
const TICKER_RE = /^[A-Z0-9][A-Z0-9.\-=^&]{0,19}$/

/** Split typed text into normalised, de-duplicated tickers, plus any invalid entries. */
export function parseTickerList(text: string): { tickers: string[]; invalid: string[] } {
  const tickers: string[] = []
  const invalid: string[] = []
  for (const raw of text.split(/[\s,;]+/)) {
    const ticker = raw.trim().toUpperCase()
    if (!ticker) continue
    if (!TICKER_RE.test(ticker)) invalid.push(raw.trim())
    else if (!tickers.includes(ticker)) tickers.push(ticker)
  }
  return { tickers, invalid }
}

function readSource(raw: Record<string, unknown> | undefined): TickerSource | undefined {
  if (!raw) return undefined
  if ((raw.kind === 'portfolio' || raw.kind === 'favourites') && typeof raw.portfolioId === 'string' && raw.portfolioId) {
    return { kind: raw.kind, portfolioId: raw.portfolioId }
  }
  if (raw.kind === 'manual' && Array.isArray(raw.tickers)) {
    const { tickers } = parseTickerList(raw.tickers.filter((t): t is string => typeof t === 'string').join(' '))
    return { kind: 'manual', tickers }
  }
  return undefined
}

/** Read a saved strategy pane configuration; undefined if the pane is not configured (or invalid). */
export function readStrategyConfig(config: Record<string, unknown>): StrategyPaneConfig | undefined {
  const strategy = readString(config, 'strategy')
  const source = readSource(readObject(config, 'source'))
  if (!strategy || !source) return undefined
  const params: Record<string, ParameterValue> = {}
  for (const [key, value] of Object.entries(readObject(config, 'params') ?? {})) {
    if (typeof value === 'number' || typeof value === 'string' || typeof value === 'boolean') params[key] = value
  }
  return { strategy, params, source }
}

/** Tickers a source resolves to, given the current portfolios. */
export function resolveTickers(source: TickerSource, portfolios: Portfolio[]): { tickers: string[]; error?: string } {
  if (source.kind === 'manual') return { tickers: source.tickers }
  const portfolio = portfolios.find((p) => p.id === source.portfolioId)
  if (!portfolio) return { tickers: [], error: 'The portfolio used by this strategy no longer exists. Open Settings to choose another.' }
  return { tickers: source.kind === 'favourites' ? portfolio.favourites : portfolio.tickers }
}

export function describeSource(source: TickerSource, portfolios: Portfolio[]): string {
  if (source.kind === 'manual') return `${source.tickers.length} manual ticker${source.tickers.length === 1 ? '' : 's'}`
  const name = portfolios.find((p) => p.id === source.portfolioId)?.name ?? 'missing portfolio'
  return source.kind === 'favourites' ? `${name} favourites` : name
}

// -- parameter form values ----------------------------------------------------------

/** Form state: numbers are kept as typed text until validated. */
export type FormValues = Record<string, string | boolean>

export function initialFormValues(parameters: StrategyParameter[], saved: Record<string, ParameterValue>): FormValues {
  const values: FormValues = {}
  for (const param of parameters) {
    const value = param.name in saved ? saved[param.name] : param.default
    values[param.name] = param.type === 'boolean' ? Boolean(value) : String(value)
  }
  return values
}

/**
 * Validate form values against the schema (types, minimum, maximum, choices).
 * Returns typed parameter values, or field errors.
 */
export function validateParameters(
  parameters: StrategyParameter[],
  values: FormValues,
): { params: Record<string, ParameterValue>; errors: Record<string, string> } {
  const params: Record<string, ParameterValue> = {}
  const errors: Record<string, string> = {}
  for (const param of parameters) {
    const raw = values[param.name]
    if (param.type === 'boolean') {
      params[param.name] = raw === true
      continue
    }
    const text = typeof raw === 'string' ? raw.trim() : ''
    if (param.type === 'string') {
      if (param.choices && !param.choices.includes(text)) errors[param.name] = `Choose one of: ${param.choices.join(', ')}`
      else params[param.name] = text
      continue
    }
    if (text === '') {
      errors[param.name] = 'Required'
      continue
    }
    const value = Number(text)
    if (!Number.isFinite(value)) {
      errors[param.name] = 'Must be a number'
    } else if (param.type === 'integer' && !Number.isInteger(value)) {
      errors[param.name] = 'Must be a whole number'
    } else if (param.minimum !== null && value < param.minimum) {
      errors[param.name] = `Must be at least ${param.minimum}`
    } else if (param.maximum !== null && value > param.maximum) {
      errors[param.name] = `Must be at most ${param.maximum}`
    } else {
      params[param.name] = value
    }
  }
  return { params, errors }
}
