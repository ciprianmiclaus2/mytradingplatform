import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { STORAGE_KEY } from './dashboard/storage'
import { health, meanReversionSchema, portfolio, quote, tickerResult } from './test/fixtures'
import { apiError, mockApi, type MockRequest } from './test/mockApi'

const watchlist = portfolio({ tickers: ['AAPL', 'MSFT'], favourites: ['MSFT'] })
const positionsList = portfolio({ id: 'pf-pos', name: 'Main Positions', type: 'positions' })

const healthy = () =>
  mockApi({
    'GET /health': health,
    'GET /portfolios': [watchlist, positionsList],
    'GET /portfolios/pf-main/quotes': { portfolio_id: 'pf-main', rows: [quote('AAPL', { price: 190.5 }), quote('MSFT', { favourite: true })] },
    'GET /portfolios/pf-pos/positions': { portfolio_id: 'pf-pos', positions: [], totals: [] },
    'GET /strategies': [meanReversionSchema],
    'POST /strategies/mean_reversion/run': (req: MockRequest) => {
      const body = req.body as { tickers: string[]; config: object; instance_id?: string }
      return { strategy: 'mean_reversion', instance_id: body.instance_id ?? null, config: body.config, calculated_at: health.server_time, results: body.tickers.map((t) => tickerResult(t)) }
    },
  })

const paneTitles = () => screen.getAllByRole('region').map((r) => r.getAttribute('aria-label'))
const saved = () => JSON.parse(window.localStorage.getItem(STORAGE_KEY)!)

describe('App', () => {
  beforeEach(() => {
    healthy()
  })

  it('shows the backend as connected when /api/health succeeds', async () => {
    render(<App />)
    expect(await screen.findByText(/Backend connected · v0\.1\.0/)).toBeInTheDocument()
  })

  it('shows an error and recovers on retry when the backend is unavailable', async () => {
    vi.restoreAllMocks()
    let down = true
    const api = mockApi({
      'GET /health': () => {
        if (down) throw new TypeError('Failed to fetch')
        return health
      },
      'GET /portfolios': () => (down ? apiError(503, 'Unavailable') : []),
    })

    render(<App />)
    expect(await screen.findByText('The backend is unavailable.')).toBeInTheDocument()
    down = false
    await userEvent.click(within(screen.getByText('The backend is unavailable.').closest('[role=alert]') as HTMLElement).getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText(/Backend connected/)).toBeInTheDocument()
    expect(api.find('GET', '/health')).toHaveLength(2)
  })

  it('starts with the default dashboard and saves it', () => {
    render(<App />)
    expect(paneTitles()).toEqual(['Portfolio', 'Positions'])
    expect(saved().panes.map((p: { type: string }) => p.type)).toEqual(['portfolio', 'positions'])
  })

  it('adds multiple panes, including several of the same type', async () => {
    render(<App />)
    for (let i = 0; i < 2; i++) {
      await userEvent.click(screen.getByRole('button', { name: /Add pane/ }))
      await userEvent.click(screen.getByRole('menuitem', { name: /Strategy/ }))
    }
    expect(paneTitles()).toEqual(['Portfolio', 'Positions', 'Strategy', 'Strategy 2'])
    expect(saved().panes).toHaveLength(4)
    expect(saved().layouts).toHaveLength(4)
  })

  it('removes a pane only after confirmation', async () => {
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: 'Remove Positions' }))
    const dialog = screen.getByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    expect(paneTitles()).toEqual(['Portfolio', 'Positions'])

    await userEvent.click(screen.getByRole('button', { name: 'Remove Positions' }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Remove' }))
    expect(paneTitles()).toEqual(['Portfolio'])
    expect(saved().panes).toHaveLength(1)
  })

  it('shows an empty state when all panes are removed', async () => {
    render(<App />)
    for (const title of ['Portfolio', 'Positions']) {
      await userEvent.click(screen.getByRole('button', { name: `Remove ${title}` }))
      await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Remove' }))
    }
    expect(screen.getByText(/The dashboard is empty/)).toBeInTheDocument()
  })

  it('shows real data in the default panes', async () => {
    render(<App />)
    expect(await screen.findByText('190.50')).toBeInTheDocument()
    expect(await screen.findByText('No open positions.')).toBeInTheDocument()
  })

  it('keeps several strategy panes with different configurations across a refresh', async () => {
    const api = healthy()
    const first = render(<App />)
    for (let i = 0; i < 2; i++) {
      await userEvent.click(screen.getByRole('button', { name: /Add pane/ }))
      await userEvent.click(screen.getByRole('menuitem', { name: /Strategy/ }))
    }
    const [one, two] = screen.getAllByRole('form', { name: 'Strategy settings' })
    // Pane 1: whole watchlist, lookback 10.
    const lookback = await within(one).findByLabelText(/Lookback/)
    await userEvent.clear(lookback)
    await userEvent.type(lookback, '10')
    await userEvent.click(within(one).getByRole('button', { name: 'Save' }))
    // Pane 2: favourites, default settings.
    await userEvent.click(within(two).getByLabelText('Portfolio favourites'))
    await userEvent.click(within(two).getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(screen.getAllByRole('table', { name: 'Mean Reversion results' })).toHaveLength(2))

    const strategyPanes = () => saved().panes.filter((p: { type: string }) => p.type === 'strategy')
    const [c1, c2] = strategyPanes().map((p: { config: unknown }) => p.config)
    expect(c1).toMatchObject({ params: { lookback_days: 10 }, source: { kind: 'portfolio', portfolioId: 'pf-main' } })
    expect(c2).toMatchObject({ params: { lookback_days: 20 }, source: { kind: 'favourites', portfolioId: 'pf-main' } })
    first.unmount()

    api.calls.length = 0
    render(<App />)
    await waitFor(() => expect(screen.getAllByRole('table', { name: 'Mean Reversion results' })).toHaveLength(2))
    const ids = strategyPanes().map((p: { id: string }) => p.id)
    const reruns = api.find('POST', '/strategies/mean_reversion/run').map((c) => c.body as { instance_id: string; tickers: string[]; config: { lookback_days: number } })
    expect(reruns.find((r) => r.instance_id === ids[0])).toMatchObject({ tickers: ['AAPL', 'MSFT'], config: { lookback_days: 10 } })
    expect(reruns.find((r) => r.instance_id === ids[1])).toMatchObject({ tickers: ['MSFT'], config: { lookback_days: 20 } })
  })

  it('keeps the selected portfolio after a refresh', async () => {
    const first = render(<App />)
    await screen.findByText('190.50')
    const picker = within(screen.getByRole('region', { name: 'Portfolio' })).getByRole('combobox', { name: 'Portfolio' })
    await userEvent.selectOptions(picker, 'pf-pos')
    first.unmount()
    render(<App />)
    const region = screen.getByRole('region', { name: 'Portfolio' })
    await waitFor(() => expect(within(region).getByRole('combobox', { name: 'Portfolio' })).toHaveValue('pf-pos'))
  })

  it('minimises and restores a pane', async () => {
    render(<App />)
    await screen.findByText('190.50')
    await userEvent.click(screen.getByRole('button', { name: 'Minimise Portfolio' }))
    expect(screen.queryByRole('table', { name: 'Main Portfolio prices' })).not.toBeInTheDocument()
    expect(Object.values(saved().minimised)).toEqual([10])
    await userEvent.click(screen.getByRole('button', { name: 'Restore Portfolio' }))
    expect(await screen.findByRole('table', { name: 'Main Portfolio prices' })).toBeInTheDocument()
  })

  it('restores the saved layout after a browser refresh', async () => {
    const first = render(<App />)
    await userEvent.click(screen.getByRole('button', { name: /Add pane/ }))
    await userEvent.click(screen.getByRole('menuitem', { name: /Strategy/ }))
    const ids = saved().panes.map((p: { id: string }) => p.id)
    first.unmount()

    render(<App />)
    expect(paneTitles()).toEqual(['Portfolio', 'Positions', 'Strategy'])
    expect(saved().panes.map((p: { id: string }) => p.id)).toEqual(ids)
  })

  it('resets to the default layout after confirmation', async () => {
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: /Add pane/ }))
    await userEvent.click(screen.getByRole('menuitem', { name: /Strategy/ }))
    await userEvent.click(screen.getByRole('button', { name: /Menu/ }))
    await userEvent.click(screen.getByRole('menuitem', { name: /Reset layout/ }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Reset' }))
    expect(paneTitles()).toEqual(['Portfolio', 'Positions'])
    expect(saved().panes).toHaveLength(2)
  })

  it('recovers from a corrupted saved layout with a notice', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    window.localStorage.setItem(STORAGE_KEY, '{"version":1,"panes":"broken"')
    render(<App />)
    expect(paneTitles()).toEqual(['Portfolio', 'Positions'])
    expect(screen.getByText(/Saved layout was invalid/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Dismiss' }))
    expect(screen.queryByText(/Saved layout was invalid/)).not.toBeInTheDocument()
  })
})
