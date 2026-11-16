import { useState } from 'react'
import { runStrategy } from '../../api/strategies'
import { DataGrid, type Column } from '../../components/DataGrid'
import { buttonClass, Modal } from '../../components/Modal'
import { useApiData } from '../../hooks/useApiData'
import { usePortfolios } from '../../hooks/usePortfolios'
import { useStrategies } from '../../hooks/useStrategies'
import type { CalculationStatus, OutputColumn, Portfolio, StrategySchema, TickerResult } from '../../types/api'
import { formatNumber, formatPercent, formatPrice, formatSigned, formatTime, gainLossClass } from '../../utils/format'
import { PaneMessage, PaneToolbar, StaleMarker } from '../common'
import type { PaneProps } from '../types'
import { describeSource, readStrategyConfig, resolveTickers, type StrategyPaneConfig } from './config'
import { StrategyExplanation } from './StrategyExplanation'
import { StrategySetup } from './StrategySetup'


/** Runs a configured strategy over its tickers and shows metrics and signals. */
export function StrategyPane({ pane, onConfigChange }: PaneProps) {
  const strategies = useStrategies()
  const portfolios = usePortfolios()
  const config = readStrategyConfig(pane.config)
  const [editing, setEditing] = useState(false)

  if (!strategies.data || !portfolios.data) {
    const failed = strategies.error ?? portfolios.error
    return (
      <PaneMessage
        loading={strategies.loading || portfolios.loading}
        error={failed}
        onRetry={() => {
          strategies.reload()
          portfolios.reload()
        }}
      />
    )
  }

  const schema = config ? strategies.data.find((s) => s.name === config.strategy) : undefined

  if (!config || editing) {
    return (
      <StrategySetup
        strategies={strategies.data}
        portfolios={portfolios.data}
        initial={config}
        onSave={(next) => {
          onConfigChange({ ...next })
          setEditing(false)
        }}
        onCancel={config ? () => setEditing(false) : undefined}
      />
    )
  }

  if (!schema) {
    return (
      <div className="p-4 text-sm">
        <p className="text-red-700">The strategy “{config.strategy}” is no longer available.</p>
        <button type="button" onClick={() => setEditing(true)} className={`${buttonClass} mt-2`}>
          Choose another strategy
        </button>
      </div>
    )
  }

  return (
    <StrategyResults
      paneId={pane.id}
      config={config}
      schema={schema}
      portfolios={portfolios.data}
      onEdit={() => setEditing(true)}
    />
  )
}

const STATUS_TEXT: Record<CalculationStatus, string> = {
  OK: '',
  NO_PRICE: 'No price',
  INSUFFICIENT_DATA: 'Insufficient data',
  INVALID_CALCULATION: 'Invalid calculation',
  DATA_ERROR: 'Data error',
}

function formatMetric(value: number | null | undefined, format: OutputColumn['format']): string {
  switch (format) {
    case 'price':
      return formatPrice(value)
    case 'percent':
      return formatPercent(value)
    case 'integer':
      return formatNumber(value, 0)
    case 'text':
      return value === null || value === undefined ? '—' : String(value)
    default:
      return formatNumber(value)
  }
}

function settingsSummary(schema: StrategySchema, config: StrategyPaneConfig): string {
  return schema.parameters
    .map((p) => {
      const value = config.params[p.name] ?? p.default
      return `${p.title}: ${typeof value === 'boolean' ? (value ? 'Yes' : 'No') : String(value)}`
    })
    .join(' · ')
}

interface ResultsProps {
  paneId: string
  config: StrategyPaneConfig
  schema: StrategySchema
  portfolios: Portfolio[]
  onEdit: () => void
}

function StrategyResults({ paneId, config, schema, portfolios, onEdit }: ResultsProps) {
  const [showAbout, setShowAbout] = useState(false)
  const { tickers, error: sourceError } = resolveTickers(config.source, portfolios)
  // Re-run whenever the strategy, its settings or the resolved tickers change.
  const runKey = tickers.length > 0 ? JSON.stringify([paneId, config.strategy, config.params, tickers]) : null
  const run = useApiData(runKey, (signal) =>
    runStrategy(config.strategy, { tickers, config: config.params, instance_id: paneId }, signal),
  )

  const columns: Column<TickerResult>[] = [
    { key: 'ticker', header: 'Ticker', sortValue: (r) => r.ticker, render: (r) => <span className="font-medium">{r.ticker}</span> },
    {
      key: 'price',
      header: 'Price',
      align: 'right',
      sortValue: (r) => r.current_price,
      render: (r) => (
        <>
          {r.stale && <StaleMarker />}
          {formatPrice(r.current_price)}
        </>
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
    // Strategy-specific metric columns, from the schema.
    ...schema.outputs.map(
      (output): Column<TickerResult> => ({
        key: `metric:${output.name}`,
        header: output.title,
        label: output.description || output.title,
        align: 'right',
        sortValue: (r) => (r.status === 'OK' ? r.metrics[output.name] : null),
        // Never show numbers from a failed calculation.
        render: (r) => (r.status === 'OK' ? formatMetric(r.metrics[output.name], output.format) : '—'),
      }),
    ),
    {
      key: 'signal',
      header: 'Signal',
      align: 'center',
      sortValue: (r) => r.signal ?? null,
      render: (r) =>
        r.signal ? (
          <span
            className={`rounded px-1.5 py-0.5 text-xs font-semibold ${r.signal === 'BUY' ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}
            title={r.signal_changed_at ? `Since ${formatTime(r.signal_changed_at)}` : undefined}
          >
            {r.signal}
            {r.is_new_signal && <span className="ml-1 font-normal">· new</span>}
          </span>
        ) : (
          ''
        ),
    },
    {
      key: 'status',
      header: 'Status',
      sortValue: (r) => (r.status === 'OK' ? '' : STATUS_TEXT[r.status]),
      render: (r) =>
        r.status === 'OK' ? (
          <span className="text-slate-400">OK</span>
        ) : (
          <span className="cursor-help text-amber-700" title={r.message ?? undefined}>
            {STATUS_TEXT[r.status]}
          </span>
        ),
    },
  ]

  const empty = sourceError ?? (tickers.length === 0 ? 'No tickers to evaluate. Add tickers to the source, or change the settings.' : 'No results.')

  return (
    <div className="flex h-full flex-col">
      <PaneToolbar>
        <span className="text-sm font-medium text-slate-700">{schema.title}</span>
        <span className="text-xs text-slate-500">{describeSource(config.source, portfolios)}</span>
        <span className="hidden truncate text-xs text-slate-400 md:inline">{settingsSummary(schema, config)}</span>
        <span className="ml-auto text-xs text-slate-400">{run.data ? `Calculated ${formatTime(run.data.calculated_at)}` : ''}</span>
        <button type="button" onClick={run.reload} disabled={!runKey || run.loading} className={buttonClass} aria-label="Recalculate">
          ↻
        </button>
        <button type="button" onClick={() => setShowAbout(true)} className={buttonClass} aria-label={`About ${schema.title}`} title="How this strategy works">
          About
        </button>
        <button type="button" onClick={onEdit} className={buttonClass}>
          Settings
        </button>
      </PaneToolbar>
      {showAbout && (
        <Modal title={`${schema.title}: how it works`} onClose={() => setShowAbout(false)} wide>
          <StrategyExplanation text={schema.explanation} />
          <p className="mt-4 border-t border-slate-200 pt-2 text-xs text-slate-500">
            This pane's settings: {settingsSummary(schema, config)}. Signals describe current conditions and are not trading advice.
          </p>
          <div className="mt-4 flex justify-end">
            <button type="button" onClick={() => setShowAbout(false)} className={buttonClass}>
              Close
            </button>
          </div>
        </Modal>
      )}
      <div className="min-h-0 flex-1">
        <DataGrid
          label={`${schema.title} results`}
          columns={columns}
          rows={runKey ? run.data?.results : []}
          rowKey={(r) => r.ticker}
          loading={run.loading}
          error={run.error}
          onRetry={run.reload}
          emptyMessage={empty}
        />
      </div>
    </div>
  )
}
