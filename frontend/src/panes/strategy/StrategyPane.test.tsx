import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { meanReversionSchema, portfolio, tickerResult } from '../../test/fixtures'
import { apiError, mockApi, type MockRequest } from '../../test/mockApi'
import { renderPane } from '../../test/renderPane'
import { StrategyPane } from './StrategyPane'

const watchlist = portfolio({ tickers: ['AAPL', 'MSFT', 'NEW'], favourites: ['MSFT'] })

const results: Record<string, ReturnType<typeof tickerResult>> = {
  AAPL: tickerResult('AAPL', { signal: 'BUY', is_new_signal: true, metrics: { mean: 105.123, standard_deviation: 2.5, z_score: -2.04 } }),
  MSFT: tickerResult('MSFT', { signal: 'SELL', current_price: 420, metrics: { mean: 400, standard_deviation: 9, z_score: 2.22 } }),
  NEW: tickerResult('NEW', { status: 'INSUFFICIENT_DATA', message: 'Need 20 sessions, have 3', metrics: { mean: null, standard_deviation: null, z_score: null } }),
}

function setup(overrides: Record<string, unknown> = {}) {
  return mockApi({
    'GET /portfolios': [watchlist],
    'GET /strategies': [meanReversionSchema],
    'POST /strategies/mean_reversion/run': (req: MockRequest) => {
      const body = req.body as { tickers: string[]; config: Record<string, number>; instance_id?: string }
      return {
        strategy: 'mean_reversion',
        instance_id: body.instance_id ?? null,
        config: body.config,
        calculated_at: '2026-11-16T12:00:00Z',
        results: body.tickers.map((t) => results[t] ?? tickerResult(t)),
      }
    },
    ...overrides,
  })
}

const savedConfig = {
  strategy: 'mean_reversion',
  params: { lookback_days: 20, buy_threshold: -2, sell_threshold: 2 },
  source: { kind: 'portfolio', portfolioId: 'pf-main' },
}

const runs = (api: ReturnType<typeof mockApi>) =>
  api.find('POST', '/strategies/mean_reversion/run').map((c) => c.body as { tickers: string[]; config: Record<string, number>; instance_id?: string })

describe('StrategyPane', () => {
  it('starts with a settings form generated from the strategy schema', async () => {
    setup()
    renderPane(StrategyPane)
    expect(await screen.findByRole('form', { name: 'Strategy settings' })).toBeInTheDocument()
    expect(screen.getByLabelText('Strategy')).toHaveValue('mean_reversion')
    expect(screen.getByLabelText(/Lookback \(sessions\)/)).toHaveValue(20)
    expect(screen.getByLabelText(/Buy threshold/)).toHaveValue(-2)
    expect(screen.getByLabelText(/Sell threshold/)).toHaveValue(2)
    expect(screen.getByLabelText('Portfolio')).toBeChecked()
    expect(screen.getByLabelText('Source portfolio')).toHaveValue('pf-main')
  })

  it('validates settings against the schema before saving', async () => {
    const api = setup()
    const { configs } = renderPane(StrategyPane)
    const lookback = await screen.findByLabelText(/Lookback/)
    await userEvent.clear(lookback)
    await userEvent.type(lookback, '1')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(screen.getByText('Must be at least 2')).toBeInTheDocument()
    expect(configs).toHaveLength(0)
    expect(runs(api)).toHaveLength(0)
  })

  it('shows backend validation errors (cross-field rules) and does not save', async () => {
    setup({
      'POST /strategies/mean_reversion/run': apiError(400, 'Invalid configuration for mean_reversion', 'strategy_config_error', {
        buy_threshold: 'must be lower than sell_threshold',
      }),
    })
    const { configs } = renderPane(StrategyPane)
    await userEvent.click(await screen.findByRole('button', { name: 'Save' }))
    expect(await screen.findByText('must be lower than sell_threshold')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Invalid configuration')
    expect(configs).toHaveLength(0)
  })

  it('saves the configuration and shows mean, std dev, z-score and signals', async () => {
    const api = setup()
    const { lastConfig } = renderPane(StrategyPane, { id: 'pane-abc' })
    const lookback = await screen.findByLabelText(/Lookback/)
    await userEvent.clear(lookback)
    await userEvent.type(lookback, '30')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    await screen.findByText('105.12')
    expect(lastConfig()).toEqual({
      strategy: 'mean_reversion',
      params: { lookback_days: 30, buy_threshold: -2, sell_threshold: 2 },
      source: { kind: 'portfolio', portfolioId: 'pf-main' },
    })
    // A dry run (no tickers) validated the settings, then the real run used the pane id.
    const [dry, real] = runs(api)
    expect(dry).toEqual({ tickers: [], config: { lookback_days: 30, buy_threshold: -2, sell_threshold: 2 } })
    expect(real).toMatchObject({ tickers: ['AAPL', 'MSFT', 'NEW'], instance_id: 'pane-abc' })

    const table = screen.getByRole('table', { name: 'Mean Reversion results' })
    const headers = within(table).getAllByRole('columnheader').map((h) => h.textContent?.replace(/[▲▼]/g, ''))
    expect(headers).toEqual(['Ticker', 'Price', 'Daily Change', 'Daily Change %', 'Mean', 'Std Dev', 'Z-Score', 'Signal', 'Status'])

    const aapl = within(table).getByText('AAPL').closest('tr')!
    expect(within(aapl).getAllByRole('cell').map((c) => c.textContent)).toEqual([
      'AAPL', '100.00', '+1.00', '+1.00%', '105.12', '2.50', '−2.04', 'BUY· new', 'OK',
    ])
    expect(within(aapl).getByText('BUY')).toHaveClass('text-emerald-700')
    expect(within(table).getByText('SELL')).toHaveClass('text-red-700')
  })

  it('shows a status instead of numbers when data is insufficient', async () => {
    setup()
    renderPane(StrategyPane, { config: savedConfig })
    const status = await screen.findByText('Insufficient data')
    expect(status).toHaveAttribute('title', 'Need 20 sessions, have 3')
    const row = status.closest('tr')!
    const cells = within(row).getAllByRole('cell').map((c) => c.textContent)
    expect(cells.slice(4, 8)).toEqual(['—', '—', '—', ''])
  })

  it('sorts by z-score', async () => {
    setup()
    renderPane(StrategyPane, { config: savedConfig })
    await screen.findByText('Insufficient data')
    await userEvent.click(screen.getByRole('button', { name: /Sort by z-score/i }))
    const tickers = within(screen.getByRole('table'))
      .getAllByRole('row')
      .slice(1)
      .map((r) => within(r).getAllByRole('cell')[0].textContent)
    expect(tickers).toEqual(['AAPL', 'MSFT', 'NEW'])
  })

  it('uses portfolio favourites or a manual list as the ticker source', async () => {
    const api = setup()
    renderPane(StrategyPane, { config: { ...savedConfig, source: { kind: 'favourites', portfolioId: 'pf-main' } } })
    await screen.findByText('MSFT')
    expect(runs(api).at(-1)!.tickers).toEqual(['MSFT'])

    await userEvent.click(screen.getByRole('button', { name: 'Settings' }))
    await userEvent.click(screen.getByLabelText('Manual selection'))
    await userEvent.type(screen.getByLabelText('Manual tickers'), 'aapl, new')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await screen.findByText('Insufficient data')
    expect(runs(api).at(-1)!.tickers).toEqual(['AAPL', 'NEW'])
  })

  it('rejects invalid manual tickers', async () => {
    setup()
    renderPane(StrategyPane)
    await userEvent.click(await screen.findByLabelText('Manual selection'))
    await userEvent.type(screen.getByLabelText('Manual tickers'), 'AAPL, b@d')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Invalid ticker symbol: b@d')
  })

  it('can cancel editing the settings', async () => {
    setup()
    renderPane(StrategyPane, { config: savedConfig })
    await screen.findByText('Insufficient data')
    await userEvent.click(screen.getByRole('button', { name: 'Settings' }))
    expect(screen.getByLabelText(/Lookback/)).toHaveValue(20)
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.getByRole('table', { name: 'Mean Reversion results' })).toBeInTheDocument()
  })

  it('explains when the source portfolio has been deleted', async () => {
    setup()
    renderPane(StrategyPane, { config: { ...savedConfig, source: { kind: 'portfolio', portfolioId: 'gone' } } })
    expect(await screen.findByText(/no longer exists/)).toBeInTheDocument()
  })

  it('shows run errors with a retry', async () => {
    let fail = true
    setup({
      'POST /strategies/mean_reversion/run': () =>
        fail
          ? apiError(503, 'Market data unavailable')
          : { strategy: 'mean_reversion', instance_id: 'pane-1', config: {}, calculated_at: '2026-11-16T12:00:00Z', results: [tickerResult('AAPL')] },
    })
    renderPane(StrategyPane, { config: savedConfig })
    expect(await screen.findByText('Market data unavailable')).toBeInTheDocument()
    fail = false
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(screen.queryByText('Market data unavailable')).not.toBeInTheDocument())
    expect(screen.getByText('AAPL')).toBeInTheDocument()
  })
})
