import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { position, portfolio } from '../../test/fixtures'
import { apiError, mockApi } from '../../test/mockApi'
import { renderPane } from '../../test/renderPane'
import { PositionsPane } from './PositionsPane'

const watchlist = portfolio()
const positionsList = portfolio({ id: 'pf-pos', name: 'Main Positions', type: 'positions' })

const aapl = position()
const vod = position({
  id: 'pos-2', ticker: 'VOD.L', currency: 'GBP', quantity: 1000, entry_price: 0.8, cost_basis: 800,
  current_price: 0.7, market_value: 700, unrealised_pnl: -100, unrealised_pnl_pct: -12.5,
  daily_change: -0.01, daily_pnl: -10, stale: true,
})
const closedMsft = position({
  id: 'pos-3', ticker: 'MSFT', status: 'CLOSED', quantity: 5, entry_price: 300, cost_basis: 1500,
  current_price: null, market_value: null, unrealised_pnl: null, unrealised_pnl_pct: null, daily_change: null, daily_pnl: null,
  exit_price: 330, exit_date: '2026-10-01', realised_pnl: 150, realised_pnl_pct: 10,
})

const response = {
  portfolio_id: 'pf-pos',
  positions: [aapl, vod, closedMsft],
  totals: [
    { currency: 'GBP', open_positions: 1, closed_positions: 0, market_value: 700, cost_basis: 800, unrealised_pnl: -100, unrealised_pnl_pct: -12.5, daily_pnl: -10, realised_pnl: 0, incomplete: false },
    { currency: 'USD', open_positions: 1, closed_positions: 1, market_value: 1100, cost_basis: 1000, unrealised_pnl: 100, unrealised_pnl_pct: 10, daily_pnl: 20, realised_pnl: 150, incomplete: true },
  ],
}

function setup(overrides: Record<string, unknown> = {}) {
  return mockApi({
    'GET /portfolios': [watchlist, positionsList],
    'GET /portfolios/pf-pos/positions': response,
    ...overrides,
  })
}

const loaded = () => screen.findByRole('button', { name: 'Edit AAPL' })
const openTable = () => screen.getByRole('table', { name: 'Main Positions open positions' })

describe('PositionsPane', () => {
  it('shows open positions with quantity, valuation and P&L, and only positions lists to choose from', async () => {
    const api = setup()
    renderPane(PositionsPane, { config: { showClosed: false } })
    await loaded()
    const table = openTable()
    expect(api.find('GET', '/portfolios/pf-pos/positions')[0].query.get('status')).toBe('all')
    const row = within(table).getByText('AAPL').closest('tr')!
    const cells = within(row).getAllByRole('cell').map((c) => c.textContent)
    expect(cells.slice(0, 9)).toEqual(['AAPL', '10', '100.00', '110.00', '1,100.00USD', '+2.00', '+20.00', '+100.00', '+10.00%'])
    expect(within(row).getByText('+100.00')).toHaveClass('text-emerald-600')

    const vodRow = within(table).getByText('VOD.L').closest('tr')!
    expect(within(vodRow).getByText('−100.00')).toHaveClass('text-red-600')
    expect(within(vodRow).getByRole('img', { name: 'Stale price' })).toBeInTheDocument()

    // Only positions lists are offered.
    const options = within(screen.getByRole('combobox', { name: 'Positions list' })).getAllByRole('option')
    expect(options.map((o) => o.textContent)).toEqual(['Main Positions'])
    // Closed positions are hidden by default.
    expect(screen.queryByText('MSFT')).not.toBeInTheDocument()
  })

  it('shows one totals row per currency, never a combined total', async () => {
    setup()
    renderPane(PositionsPane)
    await loaded()
    const footer = openTable().querySelector('tfoot')!
    const rows = within(footer as HTMLElement).getAllByRole('row')
    expect(rows.map((r) => within(r).getAllByRole('cell')[0].textContent)).toEqual(['Total GBP', 'Total USD(incomplete)'])
    expect(within(rows[0]).getByText('−12.50%')).toHaveClass('text-red-600')
    expect(within(rows[1]).getByText('+100.00')).toBeInTheDocument()
  })

  it('shows closed history with realised P&L when enabled, and saves the option', async () => {
    setup()
    const { lastConfig } = renderPane(PositionsPane, { config: { showClosed: false } })
    await loaded()
    await userEvent.click(screen.getByLabelText('Show closed'))
    expect(lastConfig()).toEqual({ showClosed: true })
    const closed = screen.getByRole('table', { name: 'Main Positions closed positions' })
    const row = within(closed).getByText('MSFT').closest('tr')!
    expect(within(row).getAllByRole('cell').map((c) => c.textContent).slice(0, 7)).toEqual([
      'MSFT', '5', '300.00', '330.00', '2026-10-01', '+150.00USD', '+10.00%',
    ])
    expect(within(closed).getByText('Total USD')).toBeInTheDocument()
  })

  it('sorts by unrealised P&L', async () => {
    setup()
    renderPane(PositionsPane)
    await loaded()
    await userEvent.click(within(openTable()).getByRole('button', { name: /^Unrealised P&L$/ }))
    const tickers = () => within(openTable().querySelector('tbody') as HTMLElement).getAllByRole('row').map((r) => within(r).getAllByRole('cell')[0].textContent)
    expect(tickers()).toEqual(['VOD.L', 'AAPL'])
  })

  it('adds a position, sending decimals as strings', async () => {
    const api = setup({ 'POST /portfolios/pf-pos/positions': aapl, 'GET /market-data/search': [] })
    renderPane(PositionsPane)
    await loaded()
    await userEvent.click(screen.getByRole('button', { name: '+ Add position' }))
    const dialog = screen.getByRole('dialog', { name: 'Add position' })
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add' }))
    expect(within(dialog).getByRole('alert')).toHaveTextContent('Ticker is required.')

    await userEvent.type(within(dialog).getByRole('combobox', { name: 'Ticker' }), 'nvda')
    await userEvent.type(within(dialog).getByLabelText('Quantity'), '0.5')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    const body = api.find('POST', '/portfolios/pf-pos/positions')[0].body as Record<string, unknown>
    expect(body).toMatchObject({ ticker: 'NVDA', quantity: '0.5' })
    expect(body).not.toHaveProperty('entry_price') // backend uses the latest price
  })

  it('validates quantities', async () => {
    setup({ 'GET /market-data/search': [] })
    renderPane(PositionsPane)
    await loaded()
    await userEvent.click(screen.getByRole('button', { name: '+ Add position' }))
    const dialog = screen.getByRole('dialog')
    await userEvent.type(within(dialog).getByRole('combobox', { name: 'Ticker' }), 'AAPL')
    await userEvent.type(within(dialog).getByLabelText('Quantity'), '-3')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add' }))
    expect(within(dialog).getByRole('alert')).toHaveTextContent(/Quantity must be a number/)
  })

  it('closes a position after confirmation, defaulting the exit price to the current price', async () => {
    const api = setup({ 'POST /positions/:id/close': closedMsft })
    renderPane(PositionsPane)
    await loaded()
    await userEvent.click(screen.getByRole('button', { name: 'Close AAPL' }))
    const dialog = screen.getByRole('dialog', { name: 'Close AAPL?' })
    expect(within(dialog).getByLabelText('Exit price')).toHaveValue('110')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    expect(api.find('POST', /close$/)).toHaveLength(0)

    await userEvent.click(screen.getByRole('button', { name: 'Close AAPL' }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Close position' }))
    await waitFor(() => expect(api.find('POST', '/positions/pos-1/close')).toHaveLength(1))
    expect(api.find('POST', '/positions/pos-1/close')[0].body).toMatchObject({ exit_price: '110' })
  })

  it('deletes a position only after confirmation', async () => {
    const api = setup({ 'DELETE /positions/:id': undefined })
    renderPane(PositionsPane)
    await loaded()
    await userEvent.click(screen.getByRole('button', { name: 'Delete VOD.L' }))
    expect(api.find('DELETE', '/positions/pos-2')).toHaveLength(0)
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(api.find('DELETE', '/positions/pos-2')).toHaveLength(1))
  })

  it('edits only the changed fields of an open position', async () => {
    const api = setup({ 'PUT /positions/:id': aapl })
    renderPane(PositionsPane)
    await loaded()
    await userEvent.click(screen.getByRole('button', { name: 'Edit AAPL' }))
    const dialog = screen.getByRole('dialog', { name: 'Edit AAPL' })
    expect(within(dialog).getByLabelText('Quantity')).toHaveValue('10')
    await userEvent.clear(within(dialog).getByLabelText('Quantity'))
    await userEvent.type(within(dialog).getByLabelText('Quantity'), '12')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.find('PUT', '/positions/pos-1')).toHaveLength(1))
    expect(api.find('PUT', '/positions/pos-1')[0].body).toEqual({ quantity: '12' })
  })

  it('shows backend errors in the dialog', async () => {
    setup({ 'PUT /positions/:id': apiError(409, 'Position was changed elsewhere', 'conflict') })
    renderPane(PositionsPane)
    await loaded()
    await userEvent.click(screen.getByRole('button', { name: 'Edit AAPL' }))
    await userEvent.type(screen.getByLabelText('Notes'), 'x')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Position was changed elsewhere')).toBeInTheDocument()
  })

  it('keeps the last positions visible when a reload fails', async () => {
    let fail = false
    setup({ 'GET /portfolios/pf-pos/positions': () => (fail ? apiError(503, 'Backend busy') : response) })
    renderPane(PositionsPane)
    await loaded()
    fail = true
    await userEvent.click(screen.getByLabelText('Show closed')) // config change only, no reload
    await userEvent.click(screen.getByRole('button', { name: 'Delete AAPL' }))
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    // Force a reload through the data-changed signal.
    const { notifyDataChanged } = await import('../../hooks/dataVersion')
    notifyDataChanged()
    expect(await screen.findByText(/Backend busy/)).toBeInTheDocument()
    expect(within(openTable()).getByText('AAPL')).toBeInTheDocument()
  })
})
