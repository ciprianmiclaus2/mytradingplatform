import { useState } from 'react'
import { addTicker, getQuotes, removeTicker, setFavourite } from '../api/portfolios'
import { DataGrid, type Column } from '../components/DataGrid'
import { PortfolioPicker } from '../components/PortfolioPicker'
import { TickerSearch } from '../components/TickerSearch'
import { notifyDataChanged } from '../hooks/dataVersion'
import { errorMessage, useApiData } from '../hooks/useApiData'
import { selectPortfolio, usePortfolios } from '../hooks/usePortfolios'
import type { Portfolio, QuoteRow } from '../types/api'
import { formatPercent, formatPrice, formatSigned, formatTime, gainLossClass } from '../utils/format'
import { readString } from './config'
import { PaneMessage, PaneToolbar, StaleMarker } from './common'
import type { PaneProps } from './types'

const TYPES = ['watchlist'] as const

/** Prices and daily change for one portfolio (watchlist). */
export function PortfolioPane({ pane, onConfigChange }: PaneProps) {
  const portfolios = usePortfolios()
  const savedId = readString(pane.config, 'portfolioId')
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
          onChange={(id) => onConfigChange({ ...pane.config, portfolioId: id })}
        />
      </PaneToolbar>
      {portfolio ? (
        <PortfolioQuotes key={portfolio.id} portfolio={portfolio} />
      ) : (
        <p className="p-4 text-sm text-slate-500">
          {missing && portfolios.loading ? 'Loading…' : missing ? 'The selected portfolio no longer exists. Choose another one.' : 'Create a portfolio to get started.'}
        </p>
      )}
    </div>
  )
}

function PortfolioQuotes({ portfolio }: { portfolio: Portfolio }) {
  const quotes = useApiData(`quotes:${portfolio.id}`, (signal) => getQuotes(portfolio.id, signal))
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const act = async (action: () => Promise<unknown>) => {
    setBusy(true)
    setActionError(null)
    try {
      await action()
      notifyDataChanged()
    } catch (err) {
      setActionError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const columns: Column<QuoteRow>[] = [
      {
        key: 'favourite',
        header: '★',
        label: 'Favourite',
        align: 'center',
        sortValue: (r) => (r.favourite ? 0 : 1),
        render: (r) => (
          <button
            type="button"
            disabled={busy}
            aria-pressed={r.favourite}
            aria-label={r.favourite ? `Unmark ${r.ticker} as favourite` : `Mark ${r.ticker} as favourite`}
            onClick={() => act(() => setFavourite(portfolio.id, r.ticker, !r.favourite))}
            className={r.favourite ? 'text-amber-500' : 'text-slate-300 hover:text-amber-400'}
          >
            {r.favourite ? '★' : '☆'}
          </button>
        ),
      },
      { key: 'ticker', header: 'Ticker', sortValue: (r) => r.ticker, render: (r) => <span className="font-medium">{r.ticker}</span> },
      {
        key: 'price',
        header: 'Price',
        align: 'right',
        sortValue: (r) => r.price,
        render: (r) =>
          r.price === null ? (
            <span className="text-slate-400" title={r.last_error ?? 'No price available yet'}>
              No price
            </span>
          ) : (
            <span title={r.timestamp ? `As of ${formatTime(r.timestamp)}` : undefined}>
              {r.stale && <StaleMarker error={r.last_error} />}
              {formatPrice(r.price)}
              {r.currency && <span className="ml-1 text-xs text-slate-400">{r.currency}</span>}
            </span>
          ),
      },
      {
        key: 'daily_change',
        header: 'Daily Change',
        align: 'right',
        sortValue: (r) => r.daily_change,
        cellClassName: (r) => gainLossClass(r.daily_change),
        render: (r) => formatSigned(r.daily_change, formatPrice),
      },
      {
        key: 'daily_change_pct',
        header: 'Daily Change %',
        align: 'right',
        sortValue: (r) => r.daily_change_pct,
        cellClassName: (r) => gainLossClass(r.daily_change_pct),
        render: (r) => formatPercent(r.daily_change_pct),
      },
      {
        key: 'actions',
        header: '',
        label: 'Actions',
        align: 'right',
        render: (r) => (
          <button
            type="button"
            disabled={busy}
            aria-label={`Remove ${r.ticker}`}
            title="Remove from watchlist"
            onClick={() => act(() => removeTicker(portfolio.id, r.ticker))}
            className="px-1 text-slate-400 hover:text-red-600"
          >
            ×
          </button>
        ),
      },
  ]

  return (
    <div className="min-h-0 flex-1">
      <div className="flex items-center gap-2 px-2 py-1.5">
        <div className="w-48">
          <TickerSearch disabled={busy} label={`Add ticker to ${portfolio.name}`} onSelect={(t) => act(() => addTicker(portfolio.id, t))} />
        </div>
        {busy && <span role="status" className="text-xs text-slate-500">Saving…</span>}
        {actionError && (
          <span role="alert" className="text-xs text-red-600">
            {actionError}
          </span>
        )}
      </div>
      <DataGrid
        label={`${portfolio.name} prices`}
        columns={columns}
        rows={quotes.data?.rows}
        rowKey={(r) => r.ticker}
        loading={quotes.loading}
        error={quotes.error}
        onRetry={quotes.reload}
        emptyMessage="No tickers yet. Add one above."
      />
    </div>
  )
}
