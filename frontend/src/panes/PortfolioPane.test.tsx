import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { apiError, mockApi } from '../test/mockApi'
import { portfolio, quote } from '../test/fixtures'
import { renderPane } from '../test/renderPane'
import { PortfolioPane } from './PortfolioPane'

const watchlist = portfolio({ tickers: ['AAPL', 'VOD.L'], favourites: ['AAPL'] })
const second = portfolio({ id: 'pf-two', name: 'Tech', tickers: ['MSFT'] })

const rowTickers = () =>
  within(screen.getByRole('table'))
    .getAllByRole('row')
    .slice(1)
    .map((r) => within(r).getAllByRole('cell')[1].textContent)

function setup(overrides: Record<string, unknown> = {}) {
  return mockApi({
    'GET /portfolios': [watchlist, second],
    'GET /portfolios/pf-main/quotes': {
      portfolio_id: 'pf-main',
      rows: [
        quote('AAPL', { name: 'Apple Inc.', favourite: true, price: 190.5, daily_change: -2.25, daily_change_pct: -1.17 }),
        quote('VOD.L', { price: 0.7123, currency: 'GBP', daily_change: 0.01, daily_change_pct: 1.42, stale: true, last_error: 'timeout' }),
      ],
    },
    'GET /portfolios/pf-two/quotes': { portfolio_id: 'pf-two', rows: [quote('MSFT', { price: null, daily_change: null, daily_change_pct: null })] },
    ...overrides,
  })
}

describe('PortfolioPane', () => {
  it('shows current prices and daily change for the first portfolio', async () => {
    setup()
    renderPane(PortfolioPane)
    expect(await screen.findByText('190.50')).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Portfolio' })).toHaveValue('pf-main')
    expect(screen.getByText('−2.25')).toHaveClass('text-red-600')
    expect(screen.getByText('−1.17%')).toHaveClass('text-red-600')
    expect(screen.getByText('+1.42%')).toHaveClass('text-emerald-600')
    expect(screen.getByText('0.7123')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Stale price' })).toHaveAttribute('title', expect.stringContaining('timeout'))
    expect(screen.getByRole('button', { name: 'Unmark AAPL as favourite' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('sorts by daily change %', async () => {
    setup()
    renderPane(PortfolioPane)
    await screen.findByText('190.50')
    await userEvent.click(screen.getByRole('button', { name: /Daily Change %/ }))
    expect(rowTickers()).toEqual(['AAPL', 'VOD.L'])
    await userEvent.click(screen.getByRole('button', { name: /Daily Change %/ }))
    expect(rowTickers()).toEqual(['VOD.L', 'AAPL'])
  })

  it('toggles favourites, removes and adds tickers, then reloads', async () => {
    const api = setup({
      'PUT /portfolios/pf-main/favourites/:t': watchlist,
      'DELETE /portfolios/pf-main/tickers/:t': watchlist,
      'POST /portfolios/pf-main/tickers': watchlist,
      'GET /market-data/search': [],
    })
    renderPane(PortfolioPane)
    await screen.findByText('190.50')
    await userEvent.click(screen.getByRole('button', { name: 'Mark VOD.L as favourite' }))
    expect(api.find('PUT', '/portfolios/pf-main/favourites/VOD.L')).toHaveLength(1)

    await userEvent.click(screen.getByRole('button', { name: 'Remove VOD.L' }))
    expect(api.find('DELETE', '/portfolios/pf-main/tickers/VOD.L')).toHaveLength(1)

    await userEvent.type(screen.getByRole('combobox', { name: 'Add ticker to Main Portfolio' }), 'msft{Enter}')
    await waitFor(() => expect(api.find('POST', '/portfolios/pf-main/tickers')).toHaveLength(1))
    expect(api.find('POST', '/portfolios/pf-main/tickers')[0].body).toEqual({ ticker: 'MSFT' })
    // Every change reloads the quotes.
    await waitFor(() => expect(api.find('GET', '/portfolios/pf-main/quotes').length).toBeGreaterThanOrEqual(4))
  })

  it('shows an error when adding an invalid ticker', async () => {
    setup({ 'POST /portfolios/pf-main/tickers': apiError(400, 'Unknown ticker ZZZZ'), 'GET /market-data/search': [] })
    renderPane(PortfolioPane)
    await screen.findByText('190.50')
    await userEvent.type(screen.getByRole('combobox', { name: /Add ticker/ }), 'zzzz{Enter}')
    expect(await screen.findByText('Unknown ticker ZZZZ')).toBeInTheDocument()
  })

  it('labels futures in the search results and adds the chosen one', async () => {
    const api = setup({
      'GET /market-data/search': [
        { ticker: 'GC=F', name: 'Gold Dec 26', exchange: 'COMEX', currency: 'USD', instrument_type: 'FUTURE', provider: 'yfinance' },
        { ticker: 'GLD', name: 'SPDR Gold Shares', exchange: 'NYSEArca', currency: 'USD', instrument_type: 'ETF', provider: 'yfinance' },
      ],
      'POST /portfolios/pf-main/tickers': watchlist,
    })
    renderPane(PortfolioPane)
    await screen.findByText('190.50')
    await userEvent.type(screen.getByRole('combobox', { name: /Add ticker/ }), 'gold')
    const [gold, gld] = within(await screen.findByRole('listbox')).getAllByRole('option')
    expect(within(gold).getByText('Future')).toBeInTheDocument()
    expect(within(gld).queryByText('Future')).not.toBeInTheDocument()
    await userEvent.click(within(gold).getByRole('button'))
    await waitFor(() => expect(api.find('POST', '/portfolios/pf-main/tickers')[0]?.body).toEqual({ ticker: 'GC=F' }))
  })

  it('shows the company name when hovering a ticker', async () => {
    setup()
    renderPane(PortfolioPane)
    const table = await screen.findByRole('table')
    expect(await within(table).findByText('AAPL')).toHaveAttribute('title', 'Apple Inc.')
    expect(within(table).getByText('VOD.L')).not.toHaveAttribute('title') // name not known yet
  })

  it('links each ticker to its Yahoo Finance page in a new window', async () => {
    setup()
    renderPane(PortfolioPane)
    const link = await screen.findByRole('link', { name: 'VOD.L' })
    expect(link).toHaveAttribute('href', 'https://finance.yahoo.com/quote/VOD.L/')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('saves the chosen portfolio in the pane configuration', async () => {
    setup()
    const { lastConfig } = renderPane(PortfolioPane)
    await screen.findByText('190.50')
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Portfolio' }), 'pf-two')
    expect(lastConfig()).toEqual({ portfolioId: 'pf-two' })
    expect(await screen.findByText('No price')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Remove MSFT/ })).toBeInTheDocument()
  })

  it('says so when the saved portfolio no longer exists', async () => {
    setup()
    renderPane(PortfolioPane, { config: { portfolioId: 'deleted' } })
    expect(await screen.findByText(/no longer exists/)).toBeInTheDocument()
  })

  it('shows an error with retry when the backend fails', async () => {
    let fail = true
    setup({
      'GET /portfolios/pf-main/quotes': () => (fail ? apiError(500, 'Quotes failed', 'internal_error') : { portfolio_id: 'pf-main', rows: [quote('AAPL')] }),
    })
    renderPane(PortfolioPane)
    expect(await screen.findByText('Quotes failed')).toBeInTheDocument()
    fail = false
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('100.00')).toBeInTheDocument()
    expect(screen.queryByText('Quotes failed')).not.toBeInTheDocument()
  })

  it('creates a new watchlist and selects it', async () => {
    const created = portfolio({ id: 'pf-new', name: 'Tech' })
    const api = setup({
      'POST /portfolios': created,
      'GET /portfolios/pf-new/quotes': { portfolio_id: 'pf-new', rows: [] },
    })
    const { lastConfig } = renderPane(PortfolioPane)
    await screen.findByText('190.50')
    await userEvent.click(screen.getByRole('button', { name: 'Manage portfolio' }))
    await userEvent.click(screen.getByRole('menuitem', { name: /New watchlist/ }))
    await userEvent.type(screen.getByLabelText('Name'), 'Tech')
    await userEvent.click(screen.getByRole('button', { name: 'Create' }))
    expect(api.find('POST', '/portfolios')[0].body).toEqual({ name: 'Tech', type: 'watchlist' })
    expect(lastConfig()).toEqual({ portfolioId: 'pf-new' })
  })
})
