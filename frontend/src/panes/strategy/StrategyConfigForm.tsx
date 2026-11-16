import { inputClass } from '../../components/Modal'
import type { StrategyParameter } from '../../types/api'
import type { FormValues } from './config'

interface Props {
  /** Unique prefix for element ids (several forms can be open at once). */
  idPrefix: string
  parameters: StrategyParameter[]
  values: FormValues
  errors: Record<string, string>
  onChange: (name: string, value: string | boolean) => void
}

function rangeHint(param: StrategyParameter): string | null {
  const { minimum: min, maximum: max } = param
  if (min !== null && max !== null) return `${min} – ${max}`
  if (min !== null) return `≥ ${min}`
  if (max !== null) return `≤ ${max}`
  return null
}

/**
 * Configuration form generated from a strategy's parameter schema. Nothing
 * here is specific to any strategy: integer, number, string (optionally
 * with choices) and boolean parameters are supported.
 */
export function StrategyConfigForm({ idPrefix, parameters, values, errors, onChange }: Props) {
  if (parameters.length === 0) return <p className="text-sm text-slate-500">This strategy has no settings.</p>
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {parameters.map((param) => {
        const id = `${idPrefix}-param-${param.name}`
        const error = errors[param.name]
        const hint = rangeHint(param)
        const describedBy = `${id}-help`
        const value = values[param.name]
        return (
          <div key={param.name} className="text-sm">
            {param.type === 'boolean' ? (
              <label className="flex items-center gap-2 pt-5">
                <input
                  id={id}
                  type="checkbox"
                  checked={value === true}
                  aria-describedby={describedBy}
                  onChange={(e) => onChange(param.name, e.target.checked)}
                />
                {param.title}
              </label>
            ) : (
              <>
                <label htmlFor={id} className="mb-1 block text-slate-600">
                  {param.title}
                  {hint && <span className="ml-1 text-xs text-slate-400">({hint})</span>}
                </label>
                {param.type === 'string' && param.choices ? (
                  <select id={id} value={String(value)} aria-describedby={describedBy} aria-invalid={!!error} onChange={(e) => onChange(param.name, e.target.value)} className={inputClass}>
                    {param.choices.map((choice) => (
                      <option key={choice} value={choice}>
                        {choice}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    id={id}
                    type={param.type === 'string' ? 'text' : 'number'}
                    step={param.type === 'integer' ? 1 : 'any'}
                    min={param.minimum ?? undefined}
                    max={param.maximum ?? undefined}
                    value={String(value ?? '')}
                    aria-describedby={describedBy}
                    aria-invalid={!!error}
                    onChange={(e) => onChange(param.name, e.target.value)}
                    className={`${inputClass} ${error ? 'border-red-400' : ''}`}
                  />
                )}
              </>
            )}
            <p id={describedBy} className="mt-0.5 text-xs text-slate-400">
              {param.description}
              {` Default: ${String(param.default)}.`}
            </p>
            {error && <p className="mt-0.5 text-xs text-red-600">{error}</p>}
          </div>
        )
      })}
    </div>
  )
}
