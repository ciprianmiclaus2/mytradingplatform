import { useState } from 'react'
import { getBrokerPositions, refreshAllBrokerAccounts, refreshBrokerAccount } from '../../api/brokers'
import { DataGrid, type Column, type FooterRow } from '../../components/DataGrid'
import { TickerLink } from '../../components/TickerLink'
import { buttonClass } from '../../components/Modal'
import { notifyDataChanged } from '../../hooks/dataVersion'
import { errorMessage, useApiData } from '../../hooks/useApiData'
import { accountLabel, useBrokerAccounts } from '../../hooks/useBrokerAccounts'
import type { BrokerAccount, BrokerAccountView, BrokerCurrencyTotals, BrokerPositionView } from '../../types/api'
import {
  formatMoney,
  formatPercent,
  formatPrice,
  formatQuantity,
  formatSigned,
  formatTime,
  gainLossClass,
} from '../../utils/format'
import { PaneMessage, PaneToolbar, StaleMarker } from '../common'
import { readString } from '../config'
import type { PaneProps } from '../types'
import { yahooTickerForPosition } from '../../utils/yahoo'
import { SnapTradeSettingsDialog } from './SnapTradeSettingsDialog'

/** Positions of one broker account (via SnapTrade), valued with live market prices. */
export function BrokerPositionsPane({ pane, onConfigChange }: PaneProps) {
  const accounts = useBrokerAccounts()
  const [settingsOpen, setSettingsOpen] = useState(false)
  const savedId = readString(pane.config, 'accountId')
  const settings = settingsOpen && <SnapTradeSettingsDialog onClose={() => setSettingsOpen(false)} />

  if (!accounts.data) {
    return <PaneMessage loading={accounts.loading} error={accounts.error} onRetry={accounts.reload} />
  }
  if (!accounts.data.configured) {
    return (
      <div className="space-y-2 p-4 text-sm text-slate-600">
        <p>Positions come from your brokerage accounts through SnapTrade, which is not set up yet.</p>
        <button type="button" className={buttonClass} onClick={() => setSettingsOpen(true)}>
          Set up SnapTrade…
        </button>
        {settings}
      </div>
    )
  }

  const list = accounts.data.accounts
  const account = savedId ? list.find((a) => a.id === savedId) : list[0]

  return (
    <div className="flex h-full flex-col">
      <PaneToolbar>
        <label className="flex items-center gap-1.5 text-sm text-slate-600">
          Account
          <select
            aria-label="Account"
            value={account?.id ?? ''}
            onChange={(e) => onConfigChange({ ...pane.config, accountId: e.target.value })}
            className="max-w-64 rounded border border-slate-300 px-1.5 py-0.5 text-sm"
          >
            {!account && <option value="">Choose…</option>}
            {list.map((a) => (
              <option key={a.id} value={a.id}>
                {accountLabel(a)}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={() => setSettingsOpen(true)}
          className="ml-auto text-xs text-slate-500 hover:text-slate-800"
          title="SnapTrade settings"
        >
          SnapTrade…
        </button>
      </PaneToolbar>
      {account ? (
        <AccountPositions key={account.id} account={account} />
      ) : (
        <NoAccount missing={Boolean(savedId)} empty={list.length === 0} />
      )}
      {settings}
    </div>
  )
}

function NoAccount({ missing, empty }: { missing: boolean; empty: boolean }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const refresh = async () => {
    setBusy(true)
    setError(null)
    try {
      await refreshAllBrokerAccounts()
      notifyDataChanged()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="space-y-2 p-4 text-sm text-slate-600">
      <p>
        {missing
          ? 'This account is no longer listed by SnapTrade. Choose another account, or refresh the account list.'
          : empty
            ? 'SnapTrade has no accounts for this user. Connect a brokerage at SnapTrade, then refresh.'
            : 'Choose an account.'}
      </p>
      <button type="button" className={buttonClass} disabled={busy} onClick={refresh}>
        {busy ? 'Refreshing…' : '↻ Refresh accounts'}
      </button>
      {error && (
        <p role="alert" className="text-red-600">
          {error}
        </p>
      )}
    </div>
  )
}

function ccy(currency: string | null) {
  return currency ? <span className="ml-1 text-xs text-slate-400">{currency}</span> : null
}

function PriceCell({ row, account }: { row: BrokerPositionView; account: BrokerAccount }) {
  if (row.current_price === null) return <span className="text-slate-400">No price</span>
  const broker = row.price_source === 'broker'
  return (
    <>
      {row.stale && <StaleMarker />}
      {broker && (
        <span
          role="img"
          aria-label="Broker price"
          title={`Broker's price at the last refresh${account.data_as_of ? ` (as of ${formatTime(account.data_as_of)})` : ''}; no live market price is available for this position.`}
          className="mr-1 cursor-help text-xs text-slate-400"
        >
          ⓑ
        </span>
      )}
      {formatPrice(row.current_price)}
    </>
  )
}

function AccountPositions({ account }: { account: BrokerAccountView }) {
  const positions = useApiData(`broker-positions:${account.id}`, (signal) => getBrokerPositions(account.id, signal))
  const [refreshing, setRefreshing] = useState(false)
  const [refreshError, setRefreshError] = useState<string | null>(null)
  // The latest account details: from the positions response once loaded (it includes refresh times).
  const current: BrokerAccount = positions.data?.account ?? account

  const refresh = async () => {
    setRefreshing(true)
    setRefreshError(null)
    try {
      await refreshBrokerAccount(account.id)
      notifyDataChanged()
    } catch (err) {
      setRefreshError(errorMessage(err))
    } finally {
      setRefreshing(false)
    }
  }

  const columns: Column<BrokerPositionView>[] = [
    {
      key: 'symbol',
      header: 'Symbol',
      sortValue: (p) => p.ticker ?? p.symbol,
      render: (p) => (
        <TickerLink
          label={p.symbol}
          ticker={yahooTickerForPosition(p)}
          title={[p.description, p.ticker && p.ticker !== p.symbol ? `Market data: ${p.ticker}` : null, p.kind].filter(Boolean).join(' · ')}
        />
      ),
    },
    { key: 'quantity', header: 'Quantity', align: 'right', sortValue: (p) => p.quantity, render: (p) => formatQuantity(p.quantity) },
    { key: 'average_cost', header: 'Avg Cost', align: 'right', sortValue: (p) => p.average_cost, render: (p) => formatPrice(p.average_cost) },
    { key: 'price', header: 'Price', align: 'right', sortValue: (p) => p.current_price, render: (p) => <PriceCell row={p} account={current} /> },
    {
      key: 'market_value',
      header: 'Market Value',
      align: 'right',
      sortValue: (p) => p.market_value,
      render: (p) => (
        <>
          {formatMoney(p.market_value)}
          {ccy(p.currency)}
        </>
      ),
    },
    {
      key: 'daily_change',
      header: 'Daily Change',
      align: 'right',
      sortValue: (p) => p.daily_change,
      cellClassName: (p) => gainLossClass(p.daily_change),
      render: (p) => formatSigned(p.daily_change, formatPrice),
    },
    {
      key: 'daily_pnl',
      header: 'Daily P&L',
      align: 'right',
      sortValue: (p) => p.daily_pnl,
      cellClassName: (p) => gainLossClass(p.daily_pnl),
      render: (p) => formatSigned(p.daily_pnl),
    },
    {
      key: 'unrealised_pnl',
      header: 'Unrealised P&L',
      align: 'right',
      sortValue: (p) => p.unrealised_pnl,
      cellClassName: (p) => gainLossClass(p.unrealised_pnl),
      render: (p) => formatSigned(p.unrealised_pnl),
    },
    {
      key: 'unrealised_pnl_pct',
      header: 'Unrealised P&L %',
      align: 'right',
      sortValue: (p) => p.unrealised_pnl_pct,
      cellClassName: (p) => gainLossClass(p.unrealised_pnl_pct),
      render: (p) => formatPercent(p.unrealised_pnl_pct),
    },
  ]

  const footer: FooterRow[] = (positions.data?.totals ?? []).map((t) => ({
    key: t.currency,
    cells: {
      symbol: <TotalLabel totals={t} />,
      market_value: (
        <>
          {formatMoney(t.market_value)}
          {ccy(t.currency)}
        </>
      ),
      daily_pnl: <span className={gainLossClass(t.daily_pnl)}>{formatSigned(t.daily_pnl)}</span>,
      unrealised_pnl: <span className={gainLossClass(t.unrealised_pnl)}>{formatSigned(t.unrealised_pnl)}</span>,
      unrealised_pnl_pct: <span className={gainLossClass(t.unrealised_pnl_pct)}>{formatPercent(t.unrealised_pnl_pct)}</span>,
    },
  }))

  return (
    <div className="min-h-0 flex-1">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-2 py-1.5 text-xs text-slate-500">
        <button type="button" onClick={refresh} disabled={refreshing} className={buttonClass} title="Fetch this account's positions from SnapTrade">
          {refreshing ? 'Refreshing…' : '↻ Refresh'}
        </button>
        <span>
          Last refresh: <span className="text-slate-700">{current.positions_refreshed_at ? formatTime(current.positions_refreshed_at) : 'never'}</span>
        </span>
        {current.data_as_of && (
          <span title="When SnapTrade last fetched this account's data from the broker">
            Broker data as of {formatTime(current.data_as_of)}
          </span>
        )}
        {refreshError && (
          <span role="alert" className="text-red-600">
            {refreshError}
          </span>
        )}
      </div>
      <DataGrid
        label={`${accountLabel(account)} positions`}
        columns={columns}
        rows={positions.data?.positions}
        rowKey={(p) => `${p.symbol}|${p.kind}|${p.currency}`}
        loading={positions.loading}
        error={positions.error}
        onRetry={positions.reload}
        footerRows={footer}
        defaultSort={{ key: 'market_value', direction: 'desc' }}
        emptyMessage={current.positions_refreshed_at ? 'No positions in this account.' : 'Not refreshed yet. Use ↻ Refresh to load the positions.'}
      />
    </div>
  )
}

function TotalLabel({ totals }: { totals: BrokerCurrencyTotals }) {
  return (
    <span>
      Total {totals.currency}
      {totals.incomplete && (
        <span className="ml-1 cursor-help text-amber-600" title="Some positions have no price, cost or daily change and are left out of those totals.">
          (incomplete)
        </span>
      )}
    </span>
  )
}
