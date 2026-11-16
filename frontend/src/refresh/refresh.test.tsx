import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import App from '../App'
import { STORAGE_KEY } from '../dashboard/storage'
import { health, meanReversionSchema, portfolio, quote, tickerResult } from '../test/fixtures'
import { apiError, mockApi, reply, type MockRequest } from '../test/mockApi'
import type { RefreshResult } from '../types/api'

const watchlist = portfolio({ tickers: ['AAPL', 'MSFT'] })

const result = (overrides: Partial<RefreshResult> = {}): RefreshResult => ({
  status: 'completed',
  started_at: '2026-11-16T14:59:58Z',
  completed_at: '2026-11-16T15:00:00Z',
  tickers_requested: 3,
  tickers_updated: 3,
  tickers_failed: 0,
  errors: [],
  ...overrides,
})

/** A dashboard with a portfolio pane and a strategy pane using a manual ticker list. */
function saveLayout() {
  const strategy = { strategy: 'mean_reversion', params: { lookback_days: 20 }, source: { kind: 'manual', tickers: ['NVDA', 'AAPL'] } }
  window.localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      version: 1,
      panes: [
        { id: 'pane-p', type: 'portfolio', title: 'Portfolio', config: {} },
        { id: 'pane-s', type: 'strategy', title: 'Strategy', config: strategy },
      ],
      layouts: [
        { i: 'pane-p', x: 0, y: 0, w: 6, h: 10 },
        { i: 'pane-s', x: 0, y: 10, w: 12, h: 10 },
      ],
      minimised: {},
    }),
  )
}

/** Backend whose prices move on every refresh. */
function backend(refreshReply: (req: MockRequest) => unknown = () => result(), status: unknown = { provider: 'fake', last_refresh: null, last_successful_refresh_at: null }) {
  let price = 100
  let stale = false
  let release: (() => void) | null = null
  let hold = false
  const api = mockApi({
    'GET /health': health,
    'GET /market-data/status': status,
    'GET /portfolios': [watchlist],
    'GET /portfolios/pf-main/quotes': () => ({
      portfolio_id: 'pf-main',
      rows: [quote('AAPL', { price }), quote('MSFT', { price: 50, stale, last_error: stale ? 'timeout' : null })],
    }),
    'GET /strategies': [meanReversionSchema],
    'POST /strategies/mean_reversion/run': (req: MockRequest) => {
      const body = req.body as { tickers: string[] }
      return { strategy: 'mean_reversion', instance_id: 'pane-s', config: {}, calculated_at: health.server_time, results: body.tickers.map((t) => tickerResult(t, { current_price: price })) }
    },
    'POST /market-data/refresh': async (req: MockRequest) => {
      if (hold) await new Promise<void>((resolve) => (release = resolve))
      const out = refreshReply(req) as RefreshResult
      price += 10
      stale = (out as { status?: string }).status === 'partial'
      return out
    },
  })
  return {
    api,
    holdNext: () => (hold = true),
    release: () => {
      hold = false
      release?.()
    },
  }
}

// The saved layout is version 1 (before tabs), so these tests also cover its migration.
const strategyRegion = () => screen.getByRole('tabpanel', { name: 'Mean Reversion · 2 manual tickers' })
const portfolioRegion = () => screen.getByRole('tabpanel', { name: 'Main Portfolio' })

describe('global refresh', () => {
  it('refreshes once, then reloads every pane and re-runs strategies', async () => {
    saveLayout()
    const { api, holdNext, release } = backend()
    render(<App />)
    await screen.findByRole('tabpanel', { name: 'Mean Reversion · 2 manual tickers' })
    await within(portfolioRegion()).findByText('100.00')
    await within(strategyRegion()).findAllByText('100.00')
    expect(screen.getByText('Not refreshed yet')).toBeInTheDocument()
    const quotesBefore = api.find('GET', '/portfolios/pf-main/quotes').length
    const runsBefore = api.find('POST', '/strategies/mean_reversion/run').length

    holdNext()
    await userEvent.click(screen.getByRole('button', { name: /^Refresh$|Refresh$/ }))
    // Feedback while the refresh runs; a second click does nothing.
    const busy = screen.getByRole('button', { name: /Refreshing/ })
    expect(busy).toBeDisabled()
    expect(screen.getByText('Refreshing market data…')).toBeInTheDocument()
    release()

    await within(portfolioRegion()).findByText('110.00')
    await waitFor(() => expect(within(strategyRegion()).getAllByText('110.00')).toHaveLength(2))
    expect(api.find('POST', '/market-data/refresh')).toHaveLength(1)
    // Strategy-only tickers are sent; the backend adds portfolio tickers itself.
    expect(api.find('POST', '/market-data/refresh')[0].body).toEqual({ extra_tickers: ['NVDA', 'AAPL'] })
    expect(api.find('GET', '/portfolios/pf-main/quotes').length).toBe(quotesBefore + 1)
    expect(api.find('POST', '/strategies/mean_reversion/run').length).toBe(runsBefore + 1)

    expect(screen.getByText('Updated 3 tickers')).toBeInTheDocument()
    expect(screen.getByText(/Last successful refresh: /)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Refresh/ })).toBeEnabled()
  })

  it('reports partial failures with details and marks stale prices', async () => {
    saveLayout()
    backend(() =>
      result({ status: 'partial', tickers_updated: 2, tickers_failed: 1, errors: [{ ticker: 'MSFT', code: 'provider_error', message: 'timeout' }] }),
    )
    render(<App />)
    await screen.findByRole('tabpanel', { name: 'Mean Reversion · 2 manual tickers' })
    await within(portfolioRegion()).findByText('100.00')
    await userEvent.click(screen.getByRole('button', { name: /Refresh/ }))
    expect(await screen.findByText('1 of 3 tickers failed')).toBeInTheDocument()
    // Successful tickers still update; the failed one keeps its price, marked stale.
    await within(portfolioRegion()).findByText('110.00')
    expect(within(portfolioRegion()).getByText('50.00')).toBeInTheDocument()
    expect(within(portfolioRegion()).getByRole('img', { name: 'Stale price' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'details' }))
    const details = screen.getByRole('dialog', { name: 'Refresh errors' })
    expect(details).toHaveTextContent('MSFT: timeout')
  })

  it('keeps the last data when the refresh request fails', async () => {
    saveLayout()
    const { api } = backend(() => apiError(409, 'A refresh is already in progress', 'refresh_in_progress'))
    render(<App />)
    await screen.findByRole('tabpanel', { name: 'Mean Reversion · 2 manual tickers' })
    await within(portfolioRegion()).findByText('100.00')
    const quotesBefore = api.find('GET', '/portfolios/pf-main/quotes').length
    await userEvent.click(screen.getByRole('button', { name: /Refresh/ }))
    expect(await screen.findByText('Refresh failed: A refresh is already in progress')).toBeInTheDocument()
    expect(within(portfolioRegion()).getByText('100.00')).toBeInTheDocument()
    expect(api.find('GET', '/portfolios/pf-main/quotes').length).toBe(quotesBefore)
  })

  it('shows the last refresh recorded by the backend on startup', async () => {
    backend(undefined, {
      provider: 'fake',
      last_refresh: result({ status: 'failed', tickers_updated: 0, tickers_failed: 3, errors: [] }),
      last_successful_refresh_at: '2026-11-15T10:00:00Z',
    })
    render(<App />)
    expect(await screen.findByText('Refresh failed for all 3 tickers')).toBeInTheDocument()
    expect(screen.getByText(/Last successful refresh: /)).toBeInTheDocument()
  })

  it('still works when the status endpoint is unavailable', async () => {
    backend(undefined, reply(500))
    render(<App />)
    expect(await screen.findByText('Not refreshed yet')).toBeInTheDocument()
  })
})
