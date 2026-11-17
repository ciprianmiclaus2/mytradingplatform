import { useId, useState, type FormEvent } from 'react'
import { ApiError } from '../../api/client'
import { runStrategy } from '../../api/strategies'
import { buttonClass, FormError, inputClass, primaryButtonClass } from '../../components/Modal'
import { errorMessage } from '../../hooks/useApiData'
import { accountLabel } from '../../hooks/useBrokerAccounts'
import type { BrokerAccountView, Portfolio, StrategySchema } from '../../types/api'
import {
  initialFormValues,
  parseTickerList,
  validateParameters,
  type FormValues,
  type StrategyPaneConfig,
  type TickerSource,
} from './config'
import { StrategyConfigForm } from './StrategyConfigForm'
import { StrategyExplanation } from './StrategyExplanation'

interface Props {
  strategies: StrategySchema[]
  portfolios: Portfolio[]
  /** Broker accounts ([] when SnapTrade is not set up). */
  accounts: BrokerAccountView[]
  initial: StrategyPaneConfig | undefined
  onSave: (config: StrategyPaneConfig) => void
  /** Present when the pane already has a configuration to go back to. */
  onCancel?: () => void
}

type SourceKind = TickerSource['kind']

/** Choose a strategy, its settings (form generated from the schema) and the ticker source. */
export function StrategySetup({ strategies, portfolios, accounts, initial, onSave, onCancel }: Props) {
  const uid = useId()
  const initialSchema = strategies.find((s) => s.name === initial?.strategy) ?? strategies[0]
  const [strategyName, setStrategyName] = useState(initialSchema?.name ?? '')
  const schema = strategies.find((s) => s.name === strategyName)
  const [values, setValues] = useState<FormValues>(() =>
    initialSchema ? initialFormValues(initialSchema.parameters, initial?.strategy === initialSchema.name ? initial.params : {}) : {},
  )
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  const initialSource = initial?.source
  const [sourceKind, setSourceKind] = useState<SourceKind>(initialSource?.kind ?? 'portfolio')
  const [portfolioId, setPortfolioId] = useState(
    initialSource && (initialSource.kind === 'portfolio' || initialSource.kind === 'favourites')
      ? initialSource.portfolioId
      : (portfolios[0]?.id ?? ''),
  )
  const [accountId, setAccountId] = useState(initialSource?.kind === 'account' ? initialSource.accountId : (accounts[0]?.id ?? ''))
  const [manualText, setManualText] = useState(initialSource?.kind === 'manual' ? initialSource.tickers.join(', ') : '')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const chooseStrategy = (name: string) => {
    setStrategyName(name)
    const next = strategies.find((s) => s.name === name)
    setValues(next ? initialFormValues(next.parameters, {}) : {})
    setFieldErrors({})
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!schema) {
      setError('Choose a strategy.')
      return
    }
    const { params, errors } = validateParameters(schema.parameters, values)
    setFieldErrors(errors)
    if (Object.keys(errors).length > 0) return

    let source: TickerSource
    if (sourceKind === 'manual') {
      const { tickers, invalid } = parseTickerList(manualText)
      if (invalid.length > 0) {
        setError(`Invalid ticker symbol${invalid.length > 1 ? 's' : ''}: ${invalid.join(', ')}`)
        return
      }
      if (tickers.length === 0) {
        setError('Enter at least one ticker.')
        return
      }
      source = { kind: 'manual', tickers }
    } else if (sourceKind === 'account') {
      if (!accounts.some((a) => a.id === accountId)) {
        setError('Choose a broker account.')
        return
      }
      source = { kind: 'account', accountId }
    } else {
      if (!portfolios.some((p) => p.id === portfolioId)) {
        setError('Choose a portfolio.')
        return
      }
      source = { kind: sourceKind, portfolioId }
    }

    // Let the backend check cross-field rules (e.g. buy threshold below sell threshold)
    // with a run over no tickers, before saving.
    setBusy(true)
    try {
      await runStrategy(schema.name, { tickers: [], config: params })
    } catch (err) {
      setBusy(false)
      if (err instanceof ApiError && err.details && typeof err.details === 'object' && !Array.isArray(err.details)) {
        setFieldErrors(Object.fromEntries(Object.entries(err.details).map(([k, v]) => [k, String(v)])))
      }
      setError(errorMessage(err))
      return
    }
    setBusy(false)
    onSave({ strategy: schema.name, params, source })
  }

  if (strategies.length === 0) return <p className="p-4 text-sm text-slate-500">No strategies are available.</p>

  return (
    <form onSubmit={submit} noValidate className="space-y-4 p-3" aria-label="Strategy settings">
      <div className="text-sm">
        <label htmlFor={`${uid}-strategy`} className="mb-1 block font-medium text-slate-700">
          Strategy
        </label>
        <select id={`${uid}-strategy`} value={strategyName} onChange={(e) => chooseStrategy(e.target.value)} className={`${inputClass} max-w-xs`}>
          {strategies.map((s) => (
            <option key={s.name} value={s.name}>
              {s.title}
            </option>
          ))}
        </select>
        {schema && <p className="mt-1 text-xs text-slate-500">{schema.description}</p>}
        {schema?.explanation && (
          <details key={schema.name} className="mt-2 max-w-3xl rounded border border-slate-200 bg-slate-50 px-3 py-2">
            <summary className="cursor-pointer text-sm font-medium text-slate-700">How this strategy works</summary>
            <StrategyExplanation text={schema.explanation} />
          </details>
        )}
      </div>

      {schema && (
        <fieldset>
          <legend className="mb-2 text-sm font-medium text-slate-700">Settings</legend>
          <StrategyConfigForm
            idPrefix={uid}
            parameters={schema.parameters}
            values={values}
            errors={fieldErrors}
            onChange={(name, value) => setValues((v) => ({ ...v, [name]: value }))}
          />
        </fieldset>
      )}

      <fieldset className="text-sm">
        <legend className="mb-2 font-medium text-slate-700">Tickers</legend>
        <div className="flex flex-wrap gap-4">
          {(
            [
              ['portfolio', 'Portfolio'],
              ['favourites', 'Portfolio favourites'],
              ['account', 'Broker account'],
              ['manual', 'Manual selection'],
            ] as const
          )
            // Offer broker accounts only when there are some (or the saved source is one).
            .filter(([kind]) => kind !== 'account' || accounts.length > 0 || initialSource?.kind === 'account')
            .map(([kind, text]) => (
            <label key={kind} className="flex items-center gap-1.5">
              <input type="radio" name={`${uid}-source`} checked={sourceKind === kind} onChange={() => setSourceKind(kind)} />
              {text}
            </label>
          ))}
        </div>
        <div className="mt-2 max-w-md">
          {sourceKind === 'manual' ? (
            <textarea
              aria-label="Manual tickers"
              rows={2}
              value={manualText}
              placeholder="AAPL, MSFT, VOD.L"
              onChange={(e) => setManualText(e.target.value)}
              className={inputClass}
            />
          ) : sourceKind === 'account' ? (
            <>
              <select aria-label="Source account" value={accountId} onChange={(e) => setAccountId(e.target.value)} className={inputClass}>
                {!accounts.some((a) => a.id === accountId) && <option value="">Choose…</option>}
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {accountLabel(a)} ({a.tickers.length} ticker{a.tickers.length === 1 ? '' : 's'})
                  </option>
                ))}
              </select>
              <p className="mt-1 text-xs text-slate-500">
                The account&apos;s stocks and funds as of its last SnapTrade refresh. Options and cash are not included.
              </p>
            </>
          ) : (
            <select aria-label="Source portfolio" value={portfolioId} onChange={(e) => setPortfolioId(e.target.value)} className={inputClass}>
              {!portfolios.some((p) => p.id === portfolioId) && <option value="">Choose…</option>}
              {portfolios.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          )}
        </div>
      </fieldset>

      <FormError message={error} />
      <div className="flex gap-2">
        <button type="submit" disabled={busy} className={primaryButtonClass}>
          {busy ? 'Checking…' : 'Save'}
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel} className={buttonClass}>
            Cancel
          </button>
        )}
      </div>
    </form>
  )
}
