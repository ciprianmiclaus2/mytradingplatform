import { useState } from 'react'
import { deletePosition, listPositions } from '../../api/positions'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { DataGrid, type Column, type FooterRow } from '../../components/DataGrid'
import { buttonClass } from '../../components/Modal'
import { PortfolioPicker } from '../../components/PortfolioPicker'
import { notifyDataChanged } from '../../hooks/dataVersion'
import { errorMessage, useApiData } from '../../hooks/useApiData'
import { selectPortfolio, usePortfolios } from '../../hooks/usePortfolios'
import type { CurrencyTotals, Portfolio, PositionView } from '../../types/api'
import {
  formatDate,
  formatMoney,
  formatPercent,
  formatPrice,
  formatQuantity,
  formatSigned,
  gainLossClass,
} from '../../utils/format'
import { PaneMessage, PaneToolbar, StaleMarker } from '../common'
import { readBoolean, readString } from '../config'
import type { PaneProps } from '../types'
import { AddPositionDialog, ClosePositionDialog, EditPositionDialog } from './PositionDialogs'

const TYPES = ['positions'] as const

/** Open positions with valuation and P&L, per-currency totals and (optionally) closed history. */
export function PositionsPane({ pane, onConfigChange }: PaneProps) {
  const portfolios = usePortfolios()
  const savedId = readString(pane.config, 'portfolioId')
  const showClosed = readBoolean(pane.config, 'showClosed')
  const { portfolio, missing } = selectPortfolio(portfolios.data, savedId, TYPES)

  if (!portfolios.data) {
    return <PaneMessage loading={portfolios.loading} error={portfolios.error} onRetry={portfolios.reload} />
  }

  return (
    <div className="flex h-full flex-col">
      <PaneToolbar>
        <PortfolioPicker
          portfolios={portfolios.data}
          value={portfolio?.id}
          types={TYPES}
          label="Positions list"
          onChange={(id) => onConfigChange({ ...pane.config, portfolioId: id })}
        />
        <label className="ml-auto flex items-center gap-1.5 text-sm text-slate-600">
          <input
            type="checkbox"
            checked={showClosed}
            onChange={(e) => onConfigChange({ ...pane.config, showClosed: e.target.checked })}
          />
          Show closed
        </label>
      </PaneToolbar>
      {portfolio ? (
        <PositionsTables key={portfolio.id} portfolio={portfolio} showClosed={showClosed} />
      ) : (
        <p className="p-4 text-sm text-slate-500">
          {missing && portfolios.loading ? 'Loading…' : missing ? 'The selected positions list no longer exists. Choose another one.' : 'Create a positions list to get started.'}
        </p>
      )}
    </div>
  )
}

type Dialog =
  | { kind: 'add' }
  | { kind: 'edit'; position: PositionView }
  | { kind: 'close'; position: PositionView }
  | { kind: 'delete'; position: PositionView }
  | null

function ccy(currency: string) {
  return <span className="ml-1 text-xs text-slate-400">{currency}</span>
}

function PositionsTables({ portfolio, showClosed }: { portfolio: Portfolio; showClosed: boolean }) {
  const positions = useApiData(`positions:${portfolio.id}`, (signal) => listPositions(portfolio.id, signal))
  const [dialog, setDialog] = useState<Dialog>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const all = positions.data?.positions
  const open = all?.filter((p) => p.status === 'OPEN')
  const closed = all?.filter((p) => p.status === 'CLOSED')
  const totals = positions.data?.totals ?? []

  const done = () => {
    setDialog(null)
    setActionError(null)
    notifyDataChanged()
  }

  const remove = async (position: PositionView) => {
    try {
      await deletePosition(position.id)
      done()
    } catch (err) {
      setDialog(null)
      setActionError(errorMessage(err))
    }
  }

  const actions = (p: PositionView) => (
    <span className="inline-flex gap-1">
      <button type="button" aria-label={`Edit ${p.ticker}`} onClick={() => setDialog({ kind: 'edit', position: p })} className="px-1 text-xs text-slate-500 hover:text-slate-900">
        Edit
      </button>
      {p.status === 'OPEN' && (
        <button type="button" aria-label={`Close ${p.ticker}`} onClick={() => setDialog({ kind: 'close', position: p })} className="px-1 text-xs text-slate-500 hover:text-slate-900">
          Close
        </button>
      )}
      <button type="button" aria-label={`Delete ${p.ticker}`} onClick={() => setDialog({ kind: 'delete', position: p })} className="px-1 text-xs text-slate-400 hover:text-red-600">
        Delete
      </button>
    </span>
  )

  const openColumns: Column<PositionView>[] = [
    { key: 'ticker', header: 'Ticker', sortValue: (p) => p.ticker, render: (p) => <span className="font-medium">{p.ticker}</span> },
    { key: 'quantity', header: 'Quantity', align: 'right', sortValue: (p) => p.quantity, render: (p) => formatQuantity(p.quantity) },
    { key: 'entry_price', header: 'Entry Price', align: 'right', sortValue: (p) => p.entry_price, render: (p) => formatPrice(p.entry_price) },
    {
      key: 'price',
      header: 'Price',
      align: 'right',
      sortValue: (p) => p.current_price,
      render: (p) =>
        p.current_price === null ? (
          <span className="text-slate-400">No price</span>
        ) : (
          <>
            {p.stale && <StaleMarker />}
            {formatPrice(p.current_price)}
          </>
        ),
    },
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
    { key: 'actions', header: '', label: 'Actions', align: 'right', render: actions },
  ]

  const closedColumns: Column<PositionView>[] = [
    { key: 'ticker', header: 'Ticker', sortValue: (p) => p.ticker, render: (p) => <span className="font-medium">{p.ticker}</span> },
    { key: 'quantity', header: 'Quantity', align: 'right', sortValue: (p) => p.quantity, render: (p) => formatQuantity(p.quantity) },
    { key: 'entry_price', header: 'Entry Price', align: 'right', sortValue: (p) => p.entry_price, render: (p) => formatPrice(p.entry_price) },
    { key: 'exit_price', header: 'Exit Price', align: 'right', sortValue: (p) => p.exit_price, render: (p) => formatPrice(p.exit_price) },
    { key: 'exit_date', header: 'Exit Date', align: 'right', sortValue: (p) => p.exit_date, render: (p) => formatDate(p.exit_date) },
    {
      key: 'realised_pnl',
      header: 'Realised P&L',
      align: 'right',
      sortValue: (p) => p.realised_pnl,
      cellClassName: (p) => gainLossClass(p.realised_pnl),
      render: (p) => (
        <>
          {formatSigned(p.realised_pnl)}
          {ccy(p.currency)}
        </>
      ),
    },
    {
      key: 'realised_pnl_pct',
      header: 'Realised P&L %',
      align: 'right',
      sortValue: (p) => p.realised_pnl_pct,
      cellClassName: (p) => gainLossClass(p.realised_pnl_pct),
      render: (p) => formatPercent(p.realised_pnl_pct),
    },
    { key: 'actions', header: '', label: 'Actions', align: 'right', render: actions },
  ]

  const openTotals: FooterRow[] = totals
    .filter((t) => t.open_positions > 0)
    .map((t) => ({
      key: `open-${t.currency}`,
      cells: {
        ticker: <TotalLabel totals={t} />,
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

  const closedTotals: FooterRow[] = totals
    .filter((t) => t.closed_positions > 0)
    .map((t) => ({
      key: `closed-${t.currency}`,
      cells: {
        ticker: `Total ${t.currency}`,
        realised_pnl: (
          <span className={gainLossClass(t.realised_pnl)}>
            {formatSigned(t.realised_pnl)}
            {ccy(t.currency)}
          </span>
        ),
      },
    }))

  return (
    <div className="min-h-0 flex-1">
      <div className="flex items-center gap-2 px-2 py-1.5">
        <button type="button" onClick={() => setDialog({ kind: 'add' })} className={buttonClass}>
          + Add position
        </button>
        {actionError && (
          <span role="alert" className="text-xs text-red-600">
            {actionError}
          </span>
        )}
      </div>
      <DataGrid
        label={`${portfolio.name} open positions`}
        columns={openColumns}
        rows={open}
        rowKey={(p) => p.id}
        loading={positions.loading}
        error={positions.error}
        onRetry={positions.reload}
        footerRows={openTotals}
        emptyMessage="No open positions."
      />
      {showClosed && all && (
        <section aria-label="Closed positions" className="mt-3">
          <h3 className="px-2 py-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Closed positions</h3>
          <DataGrid
            label={`${portfolio.name} closed positions`}
            columns={closedColumns}
            rows={closed}
            rowKey={(p) => p.id}
            footerRows={closedTotals}
            defaultSort={{ key: 'exit_date', direction: 'desc' }}
            emptyMessage="No closed positions."
          />
        </section>
      )}
      {dialog?.kind === 'add' && <AddPositionDialog portfolioId={portfolio.id} onDone={done} onCancel={() => setDialog(null)} />}
      {dialog?.kind === 'edit' && <EditPositionDialog position={dialog.position} onDone={done} onCancel={() => setDialog(null)} />}
      {dialog?.kind === 'close' && <ClosePositionDialog position={dialog.position} onDone={done} onCancel={() => setDialog(null)} />}
      {dialog?.kind === 'delete' && (
        <ConfirmDialog
          title={`Delete ${dialog.position.ticker}?`}
          message={`This ${dialog.position.status === 'OPEN' ? 'open' : 'closed'} position will be deleted permanently (a backup is taken first). To record a sale, close the position instead.`}
          confirmLabel="Delete"
          onConfirm={() => remove(dialog.position)}
          onCancel={() => setDialog(null)}
        />
      )}
    </div>
  )
}

function TotalLabel({ totals }: { totals: CurrencyTotals }) {
  return (
    <span>
      Total {totals.currency}
      {totals.incomplete && (
        <span className="ml-1 cursor-help text-amber-600" title="Some positions have no current price and are left out of the market totals.">
          (incomplete)
        </span>
      )}
    </span>
  )
}
