import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { DashboardActionsContext } from '../../dashboard/actions'
import type { Pane } from '../../dashboard/types'
import { brokerAccount, brokerPosition } from '../../test/fixtures'
import { apiError, mockApi, type MockRequest } from '../../test/mockApi'
import { renderPane } from '../../test/renderPane'
import type { BrokerAccountView } from '../../types/api'
import { BrokerPositionsPane } from './BrokerPositionsPane'
import { SnapTradeSettingsDialog } from './SnapTradeSettingsDialog'

const main = brokerAccount()
const isa = brokerAccount({ id: 'acc-2', name: 'ISA', number: '****9999', tickers: ['VOD.L'], positions_refreshed_at: null, data_as_of: null })

const accountsReply = (accounts: BrokerAccountView[], configured = true) => ({
  configured,
  accounts,
  accounts_refreshed_at: '2026-11-16T12:00:00Z',
})

const positions = [
  brokerPosition(),
  brokerPosition({
    symbol: 'AAPL  261218C00240000',
    ticker: null,
    kind: 'option',
    quantity: 1,
    average_cost: 4,
    cost_basis: 400,
    current_price: 5.5,
    price_source: 'broker',
    market_value: 550,
    daily_change: null,
    daily_change_pct: null,
    daily_pnl: null,
    unrealised_pnl: 150,
    unrealised_pnl_pct: 37.5,
  }),
]
const totals = [
  { currency: 'USD', positions: 2, market_value: 1650, cost_basis: 1400, unrealised_pnl: 250, unrealised_pnl_pct: 17.86, daily_pnl: 20, incomplete: true },
]

function setup(overrides: Record<string, unknown> = {}) {
  return mockApi({
    'GET /brokers/accounts': accountsReply([main, isa]),
    'GET /brokers/accounts/acc-1/positions': { account: main, positions, totals },
    'GET /brokers/accounts/acc-2/positions': { account: isa, positions: [], totals: [] },
    ...overrides,
  })
}

describe('BrokerPositionsPane', () => {
  it('shows the first account’s positions with valuation, broker-price marker and totals', async () => {
    setup()
    renderPane(BrokerPositionsPane)
    const table = await screen.findByRole('table', { name: 'Brokerage ****1234 positions' })
    expect(await within(table).findByText('1,100.00')).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Account' })).toHaveValue('acc-1')
    expect(within(table).getByRole('link', { name: 'AAPL' })).toHaveAttribute('href', 'https://finance.yahoo.com/quote/AAPL/')
    // Options link to Yahoo's option page (OCC symbol without the padding spaces).
    expect(within(table).getByRole('link', { name: /261218C00240000/ })).toHaveAttribute(
      'href',
      'https://finance.yahoo.com/quote/AAPL261218C00240000/',
    )
    expect(within(table).getByRole('link', { name: /261218C00240000/ })).toHaveAttribute('target', '_blank')
    expect(within(table).getAllByRole('img', { name: 'Broker price' })).toHaveLength(1) // only the option
    expect(within(table).getByText('(incomplete)')).toBeInTheDocument()
    expect(within(table).getByText('1,650.00')).toBeInTheDocument()
    expect(screen.getByText(/Last refresh:/)).toHaveTextContent(/2026/)
    expect(screen.getByText(/Broker data as of/)).toBeInTheDocument()
  })

  it('saves the chosen account and explains when it has never been refreshed', async () => {
    setup()
    const { lastConfig } = renderPane(BrokerPositionsPane)
    await screen.findByRole('table', { name: 'Brokerage ****1234 positions' })
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Account' }), 'acc-2')
    expect(lastConfig()).toEqual({ accountId: 'acc-2' })
    expect(await screen.findByText(/Not refreshed yet/)).toBeInTheDocument()
    expect(screen.getByText(/Last refresh:/)).toHaveTextContent('never')
  })

  it('refreshes its own account from SnapTrade and reloads', async () => {
    let refreshed = false
    const api = setup({
      'POST /brokers/accounts/acc-1/refresh': () => {
        refreshed = true
        return { account: main, positions: [brokerPosition({ quantity: 12 })], totals }
      },
      'GET /brokers/accounts/acc-1/positions': () => ({
        account: main,
        positions: refreshed ? [brokerPosition({ quantity: 12 })] : positions,
        totals,
      }),
    })
    renderPane(BrokerPositionsPane)
    await screen.findByRole('table', { name: 'Brokerage ****1234 positions' })
    await userEvent.click(screen.getByRole('button', { name: '↻ Refresh' }))
    expect(await screen.findByText('12')).toBeInTheDocument()
    expect(api.calls.filter((c) => c.method === 'POST').map((c) => c.path)).toEqual(['/brokers/accounts/acc-1/refresh'])
  })

  it('shows refresh errors (e.g. the SnapTrade rate limit) and keeps the positions', async () => {
    setup({
      'POST /brokers/accounts/acc-1/refresh': apiError(429, 'SnapTrade rate limit reached. Try again in 12 seconds.', 'snaptrade_rate_limited'),
    })
    renderPane(BrokerPositionsPane)
    await screen.findByRole('table', { name: 'Brokerage ****1234 positions' })
    await userEvent.click(screen.getByRole('button', { name: '↻ Refresh' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Try again in 12 seconds')
    expect(screen.getByText('1,100.00')).toBeInTheDocument()
  })

  it('says so when the saved account is no longer listed, and can refresh the list', async () => {
    const api = setup({ 'POST /brokers/refresh': { accounts: [main], errors: [], accounts_refreshed_at: '2026-11-16T12:00:00Z' } })
    renderPane(BrokerPositionsPane, { config: { accountId: 'gone' } })
    expect(await screen.findByText(/no longer listed by SnapTrade/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '↻ Refresh accounts' }))
    await waitFor(() => expect(api.calls.some((c) => c.method === 'POST' && c.path === '/brokers/refresh')).toBe(true))
  })

  it('offers to set up SnapTrade when it is not configured', async () => {
    setup({
      'GET /brokers/accounts': accountsReply([], false),
      'GET /brokers/snaptrade/settings': { configured: false, personal: null, client_id: null, user_id: null, consumer_key_hint: null, user_secret_hint: null },
    })
    renderPane(BrokerPositionsPane)
    await userEvent.click(await screen.findByRole('button', { name: 'Set up SnapTrade…' }))
    expect(await screen.findByRole('dialog', { name: 'SnapTrade settings' })).toBeInTheDocument()
    expect(screen.getByLabelText('User secret')).toHaveAttribute('type', 'password')
  })
})

describe('SnapTradeSettingsDialog', () => {
  const notConfigured = { configured: false, personal: null, client_id: null, user_id: null, consumer_key_hint: null, user_secret_hint: null }

  function renderDialog(panes: Pane[] = []) {
    const addPanes = vi.fn()
    const updateConfig = vi.fn()
    const onClose = vi.fn()
    render(
      <DashboardActionsContext.Provider value={{ panes, addPanes, updateConfig }}>
        <SnapTradeSettingsDialog onClose={onClose} />
      </DashboardActionsContext.Provider>,
    )
    return { addPanes, updateConfig, onClose }
  }

  it('connects with the four values and adds a pane for each account without one', async () => {
    let saved: unknown
    mockApi({
      'GET /brokers/snaptrade/settings': notConfigured,
      'PUT /brokers/snaptrade/settings': (req: MockRequest) => {
        saved = req.body
        return { accounts: [main, isa], errors: [{ account_id: 'acc-2', account_name: 'ISA', message: 'Brokerage unavailable' }], accounts_refreshed_at: '2026-11-16T12:00:00Z' }
      },
    })
    const existing: Pane = { id: 'p1', type: 'positions', title: 'Positions', config: { accountId: 'acc-1' } }
    const { addPanes, updateConfig } = renderDialog([existing])
    await userEvent.click(await screen.findByRole('button', { name: 'Connect' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Required: Client ID, Consumer key.')

    for (const [label, value] of [['Client ID', ' cid '], ['Consumer key', 'ckey'], ['User ID', 'uid'], ['User secret', 'usecret']]) {
      await userEvent.type(screen.getByLabelText(label), value)
    }
    await userEvent.click(screen.getByRole('button', { name: 'Connect' }))
    expect(await screen.findByText(/Connected\. 2 accounts found/)).toBeInTheDocument()
    expect(saved).toEqual({ client_id: ' cid ', consumer_key: 'ckey', user_id: 'uid', user_secret: 'usecret' })
    expect(screen.getByRole('alert')).toHaveTextContent('ISA: Brokerage unavailable')
    // acc-1 already has a pane: only ISA is added.
    await userEvent.click(screen.getByRole('button', { name: 'Add a pane for the account' }))
    expect(addPanes).toHaveBeenCalledWith('positions', [{ accountId: 'acc-2' }])
    expect(updateConfig).not.toHaveBeenCalled()
    expect(screen.getByText('Panes added.')).toBeInTheDocument()
  })

  it('gives existing positions panes without an account one first, instead of duplicating them', async () => {
    mockApi({
      'GET /brokers/snaptrade/settings': notConfigured,
      'PUT /brokers/snaptrade/settings': { accounts: [main, isa], errors: [], accounts_refreshed_at: '2026-11-16T12:00:00Z' },
    })
    // The default dashboard's pane (no account chosen) and a pane saved before SnapTrade (old config).
    const fresh: Pane = { id: 'p1', type: 'positions', title: 'Positions', config: {} }
    const old: Pane = { id: 'p2', type: 'positions', title: 'Positions 2', config: { portfolioId: 'pf-pos', showClosed: false } }
    const { addPanes, updateConfig } = renderDialog([fresh, old])
    for (const label of ['Client ID', 'Consumer key', 'User ID', 'User secret']) {
      await userEvent.type(await screen.findByLabelText(label), 'x')
    }
    await userEvent.click(screen.getByRole('button', { name: 'Connect' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Add a pane for each account (2)' }))
    expect(updateConfig.mock.calls).toEqual([
      ['p1', { accountId: 'acc-1' }],
      ['p2', { portfolioId: 'pf-pos', showClosed: false, accountId: 'acc-2' }],
    ])
    expect(addPanes).toHaveBeenCalledWith('positions', [])
  })

  it('connects with a Personal API key: client ID and consumer key only', async () => {
    let saved: unknown
    let connected = false
    mockApi({
      'GET /brokers/snaptrade/settings': () =>
        connected
          ? { configured: true, personal: true, client_id: 'cid', user_id: null, consumer_key_hint: '9876', user_secret_hint: null }
          : notConfigured,
      'PUT /brokers/snaptrade/settings': (req: MockRequest) => {
        saved = req.body
        connected = true
        return { accounts: [main], errors: [], accounts_refreshed_at: '2026-11-16T12:00:00Z' }
      },
    })
    renderDialog()
    expect(await screen.findByText(/Leave these empty for a Personal API key/)).toBeInTheDocument()
    // Only one of the user fields: refused before calling the backend.
    await userEvent.type(screen.getByLabelText('Client ID'), 'cid')
    await userEvent.type(screen.getByLabelText('Consumer key'), 'ckey')
    await userEvent.type(screen.getByLabelText('User ID'), 'uid')
    await userEvent.click(screen.getByRole('button', { name: 'Connect' }))
    expect(screen.getByRole('alert')).toHaveTextContent('or leave both empty for a Personal API key')
    expect(saved).toBeUndefined()

    await userEvent.clear(screen.getByLabelText('User ID'))
    await userEvent.click(screen.getByRole('button', { name: 'Connect' }))
    expect(await screen.findByText(/Connected\. 1 account found/)).toBeInTheDocument()
    expect(saved).toEqual({ client_id: 'cid', consumer_key: 'ckey', user_id: '', user_secret: '' })
  })

  it('shows a Personal key without user rows', async () => {
    mockApi({
      'GET /brokers/snaptrade/settings': { configured: true, personal: true, client_id: 'cid', user_id: null, consumer_key_hint: '9876', user_secret_hint: null },
    })
    renderDialog()
    expect(await screen.findByText('Personal API key')).toBeInTheDocument()
    expect(screen.getByText('••••9876')).toBeInTheDocument()
    expect(screen.queryByText('User secret')).not.toBeInTheDocument()
  })

  it('shows SnapTrade’s rejection and keeps the form', async () => {
    mockApi({
      'GET /brokers/snaptrade/settings': notConfigured,
      'PUT /brokers/snaptrade/settings': apiError(422, 'SnapTrade rejected the request: Unable to verify signature sent. Check the four values.', 'snaptrade_credentials_rejected'),
    })
    renderDialog()
    for (const label of ['Client ID', 'Consumer key', 'User ID', 'User secret']) {
      await userEvent.type(await screen.findByLabelText(label), 'x')
    }
    await userEvent.click(screen.getByRole('button', { name: 'Connect' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to verify signature sent')
    expect(screen.getByLabelText('Client ID')).toBeInTheDocument()
  })

  it('shows the stored settings without secrets, and disconnects after confirmation', async () => {
    let deleted = false
    mockApi({
      'GET /brokers/snaptrade/settings': () =>
        deleted ? notConfigured : { configured: true, personal: false, client_id: 'cid', user_id: 'uid', consumer_key_hint: '9876', user_secret_hint: '4321' },
      'DELETE /brokers/snaptrade/settings': () => {
        deleted = true
        return undefined
      },
    })
    renderDialog()
    expect(await screen.findByText('••••4321')).toBeInTheDocument()
    expect(screen.getByText('cid')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Disconnect…' }))
    await userEvent.click(within(screen.getByRole('dialog', { name: 'Disconnect SnapTrade?' })).getByRole('button', { name: 'Disconnect' }))
    expect(await screen.findByRole('button', { name: 'Connect' })).toBeInTheDocument() // back to the setup form
  })
})
