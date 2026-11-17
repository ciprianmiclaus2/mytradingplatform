import { createEvent, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { STORAGE_KEY } from './dashboard/storage'
import { brokerAccount, health, meanReversionSchema, portfolio, quote, tickerResult } from './test/fixtures'
import { apiError, mockApi, type MockRequest } from './test/mockApi'

const watchlist = portfolio({ tickers: ['AAPL', 'MSFT'], favourites: ['MSFT'] })
const account = brokerAccount()
const tech = portfolio({ id: 'pf-two', name: 'Tech', tickers: [] })

const healthy = () =>
  mockApi({
    'GET /health': health,
    'GET /market-data/status': { provider: 'fake', last_refresh: null, last_successful_refresh_at: null },
    'GET /portfolios': [watchlist, tech],
    'GET /portfolios/pf-two/quotes': { portfolio_id: 'pf-two', rows: [] },
    'GET /portfolios/pf-main/quotes': { portfolio_id: 'pf-main', rows: [quote('AAPL', { price: 190.5 }), quote('MSFT', { favourite: true })] },
    'GET /brokers/accounts': { configured: true, accounts: [account], accounts_refreshed_at: health.server_time },
    'GET /brokers/accounts/acc-1/positions': { account, positions: [], totals: [] },
    'GET /strategies': [meanReversionSchema],
    'POST /strategies/mean_reversion/run': (req: MockRequest) => {
      const body = req.body as { tickers: string[]; config: object; instance_id?: string }
      return { strategy: 'mean_reversion', instance_id: body.instance_id ?? null, config: body.config, calculated_at: health.server_time, results: body.tickers.map((t) => tickerResult(t)) }
    },
  })

const PORTFOLIO = 'Main Portfolio'
const POSITIONS = 'Positions · Brokerage ****1234'
/** Labels of all tabs, in tile order (automatic names once data has loaded). */
const tabLabels = () => screen.queryAllByRole('tab').map((t) => t.textContent)
const expectTabs = (labels: string[]) => waitFor(() => expect(tabLabels()).toEqual(labels))
const panel = (label: string) => screen.getByRole('tabpanel', { name: label })
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

  it('starts with the default dashboard, with automatic tab names, and saves it', async () => {
    render(<App />)
    expect(tabLabels()).toEqual(['Portfolio', 'Positions']) // before data: the pane titles
    await expectTabs([PORTFOLIO, POSITIONS])
    expect(saved().version).toBe(2)
    expect(saved().panes.map((p: { type: string }) => p.type)).toEqual(['portfolio', 'positions'])
    expect(saved().groups).toHaveLength(2)
  })

  it('adds multiple panes, including several of the same type', async () => {
    render(<App />)
    for (let i = 0; i < 2; i++) {
      await userEvent.click(screen.getByRole('button', { name: /Add pane/ }))
      await userEvent.click(screen.getByRole('menuitem', { name: /Strategy/ }))
    }
    await expectTabs([PORTFOLIO, POSITIONS, 'New strategy', 'New strategy'])
    expect(saved().panes).toHaveLength(4)
    expect(saved().layouts).toHaveLength(4)
  })

  it('removes a pane only after confirmation', async () => {
    render(<App />)
    await expectTabs([PORTFOLIO, POSITIONS])
    await userEvent.click(screen.getByRole('button', { name: `Remove ${POSITIONS}` }))
    const dialog = screen.getByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    expect(tabLabels()).toEqual([PORTFOLIO, POSITIONS])

    await userEvent.click(screen.getByRole('button', { name: `Remove ${POSITIONS}` }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Remove' }))
    expect(tabLabels()).toEqual([PORTFOLIO])
    expect(saved().panes).toHaveLength(1)
  })

  it('shows an empty state when all panes are removed', async () => {
    render(<App />)
    await expectTabs([PORTFOLIO, POSITIONS])
    for (const label of [PORTFOLIO, POSITIONS]) {
      await userEvent.click(screen.getByRole('button', { name: `Remove ${label}` }))
      await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Remove' }))
    }
    expect(screen.getByText(/The dashboard is empty/)).toBeInTheDocument()
  })

  it('moves a pane into another tile as a tab, switches tabs, and detaches it again', async () => {
    render(<App />)
    await expectTabs([PORTFOLIO, POSITIONS])
    await userEvent.click(screen.getByRole('button', { name: `Tab options for ${POSITIONS}` }))
    await userEvent.click(screen.getByRole('menuitem', { name: `Move “${POSITIONS}” to: ${PORTFOLIO}` }))

    // One tile with two tabs; the moved pane is active.
    expect(saved().groups).toHaveLength(1)
    expect(saved().layouts).toHaveLength(1)
    const tablist = screen.getByRole('tablist')
    expect(within(tablist).getAllByRole('tab').map((t) => t.textContent)).toEqual([PORTFOLIO, POSITIONS])
    expect(screen.getByRole('tab', { name: POSITIONS })).toHaveAttribute('aria-selected', 'true')
    expect(panel(POSITIONS)).toBeVisible()
    expect(screen.queryByRole('tabpanel', { name: PORTFOLIO })).not.toBeInTheDocument() // hidden, still mounted
    expect(screen.getByText('190.50', { ignore: false })).not.toBeVisible()

    await userEvent.click(screen.getByRole('tab', { name: PORTFOLIO }))
    expect(within(panel(PORTFOLIO)).getByText('190.50')).toBeVisible()
    expect(saved().groups[0].active).toBe(saved().panes[0].id)

    // Keyboard: arrow keys move between tabs.
    screen.getByRole('tab', { name: PORTFOLIO }).focus()
    await userEvent.keyboard('{ArrowRight}')
    expect(screen.getByRole('tab', { name: POSITIONS })).toHaveFocus()
    expect(screen.getByRole('tab', { name: POSITIONS })).toHaveAttribute('aria-selected', 'true')

    await userEvent.click(screen.getByRole('button', { name: `Tab options for ${POSITIONS}` }))
    await userEvent.click(screen.getByRole('menuitem', { name: `Detach “${POSITIONS}” into its own pane` }))
    expect(saved().groups).toHaveLength(2)
    expect(screen.getAllByRole('tablist')).toHaveLength(2)
  })

  it('reorders tabs by dragging within the tab bar', async () => {
    render(<App />)
    await expectTabs([PORTFOLIO, POSITIONS])
    await userEvent.click(screen.getByRole('button', { name: `Tab options for ${POSITIONS}` }))
    await userEvent.click(screen.getByRole('menuitem', { name: `Move “${POSITIONS}” to: ${PORTFOLIO}` }))
    const [first, second] = within(screen.getByRole('tablist')).getAllByRole('tab').map((t) => t.parentElement!)
    const data = new Map<string, string>()
    const dataTransfer = { setData: (k: string, v: string) => data.set(k, v), getData: (k: string) => data.get(k), effectAllowed: '' }
    vi.spyOn(first, 'getBoundingClientRect').mockReturnValue({ left: 0, width: 100 } as DOMRect)
    fireEvent.dragStart(second, { dataTransfer })
    // jsdom drag events have no pointer position, so set it: the left half of the first tab.
    const over = createEvent.dragOver(first, { dataTransfer })
    Object.defineProperty(over, 'clientX', { value: 10 })
    fireEvent(first, over)
    fireEvent.drop(screen.getByRole('tablist'), { dataTransfer })
    expect(within(screen.getByRole('tablist')).getAllByRole('tab').map((t) => t.textContent)).toEqual([POSITIONS, PORTFOLIO])
    const ids = saved().panes.map((p: { id: string; type: string }) => p)
    expect(saved().groups[0].paneIds).toEqual([ids[1].id, ids[0].id])
  })

  it('numbers identical tab names within a tile', async () => {
    render(<App />)
    for (let i = 0; i < 2; i++) {
      await userEvent.click(screen.getByRole('button', { name: /Add pane/ }))
      await userEvent.click(screen.getByRole('menuitem', { name: /Strategy/ }))
    }
    await expectTabs([PORTFOLIO, POSITIONS, 'New strategy', 'New strategy'])
    const options = screen.getAllByRole('button', { name: 'Tab options for New strategy' })
    await userEvent.click(options[1])
    await userEvent.click(screen.getByRole('menuitem', { name: 'Move “New strategy” to: New strategy' }))
    await expectTabs([PORTFOLIO, POSITIONS, 'New strategy', 'New strategy (2)'])
  })

  it('shows real data in the default panes', async () => {
    render(<App />)
    expect(await screen.findByText('190.50')).toBeInTheDocument()
    expect(await screen.findByText('No positions in this account.')).toBeInTheDocument()
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
    const picker = within(panel(PORTFOLIO)).getByRole('combobox', { name: 'Portfolio' })
    await userEvent.selectOptions(picker, 'pf-two')
    await expectTabs(['Tech', POSITIONS]) // the tab name follows the selection
    first.unmount()
    render(<App />)
    await expectTabs(['Tech', POSITIONS])
    expect(within(panel('Tech')).getByRole('combobox', { name: 'Portfolio' })).toHaveValue('pf-two')
  })

  it('minimises and restores a pane', async () => {
    render(<App />)
    await screen.findByText('190.50')
    await expectTabs([PORTFOLIO, POSITIONS])
    await userEvent.click(screen.getByRole('button', { name: `Minimise ${PORTFOLIO}` }))
    expect(screen.queryByRole('table', { name: 'Main Portfolio prices' })).not.toBeInTheDocument()
    expect(Object.values(saved().minimised)).toEqual([10])
    expect(screen.getByRole('tab', { name: PORTFOLIO })).toBeInTheDocument() // the tab bar stays
    await userEvent.click(screen.getByRole('button', { name: `Restore ${PORTFOLIO}` }))
    expect(await screen.findByRole('table', { name: 'Main Portfolio prices' })).toBeInTheDocument()
  })

  it('restores the saved layout after a browser refresh', async () => {
    const first = render(<App />)
    await userEvent.click(screen.getByRole('button', { name: /Add pane/ }))
    await userEvent.click(screen.getByRole('menuitem', { name: /Strategy/ }))
    const ids = saved().panes.map((p: { id: string }) => p.id)
    first.unmount()

    render(<App />)
    await expectTabs([PORTFOLIO, POSITIONS, 'New strategy'])
    expect(saved().panes.map((p: { id: string }) => p.id)).toEqual(ids)
  })

  it('resets to the default layout after confirmation', async () => {
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: /Add pane/ }))
    await userEvent.click(screen.getByRole('menuitem', { name: /Strategy/ }))
    await userEvent.click(screen.getByRole('button', { name: /Menu/ }))
    await userEvent.click(screen.getByRole('menuitem', { name: /Reset layout/ }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Reset' }))
    await expectTabs([PORTFOLIO, POSITIONS])
    expect(saved().panes).toHaveLength(2)
  })

  it('recovers from a corrupted saved layout with a notice', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    window.localStorage.setItem(STORAGE_KEY, '{"version":1,"panes":"broken"')
    render(<App />)
    await expectTabs([PORTFOLIO, POSITIONS])
    expect(screen.getByText(/Saved layout was invalid/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Dismiss' }))
    expect(screen.queryByText(/Saved layout was invalid/)).not.toBeInTheDocument()
  })
})
