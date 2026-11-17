import { useEffect, useId, useState } from 'react'
import { searchTickers } from '../api/marketData'
import type { TickerSearchResult } from '../types/api'
import { inputClass } from './Modal'

interface Props {
  /** Called with the chosen symbol (a search result, or the typed text on Enter). */
  onSelect: (ticker: string) => void
  placeholder?: string
  disabled?: boolean
  label?: string
  /** Keep the chosen symbol in the box (forms) instead of clearing it (quick add). */
  keepValue?: boolean
}

const SEARCH_DELAY_MS = 300

/** Ticker input with provider search suggestions. */
export function TickerSearch({ onSelect, placeholder = 'Add ticker…', disabled, label = 'Ticker', keepValue = false }: Props) {
  const [text, setText] = useState('')
  const [results, setResults] = useState<TickerSearchResult[]>([])
  const [open, setOpen] = useState(false)
  const listId = useId()
  const query = text.trim()

  useEffect(() => {
    if (query.length < 1) return
    const controller = new AbortController()
    const timer = setTimeout(() => {
      searchTickers(query, controller.signal)
        .then((found) => {
          setResults(found)
          setOpen(true)
        })
        .catch(() => setResults([]))
    }, SEARCH_DELAY_MS)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [query])

  const choose = (ticker: string) => {
    const symbol = ticker.trim().toUpperCase()
    if (!symbol) return
    setOpen(false)
    setResults([])
    setText(keepValue ? symbol : '')
    onSelect(symbol)
  }

  const visible = open && query.length > 0 && results.length > 0

  return (
    <div className="relative">
      <input
        type="text"
        aria-label={label}
        role="combobox"
        aria-expanded={visible}
        aria-controls={listId}
        aria-autocomplete="list"
        value={text}
        disabled={disabled}
        placeholder={placeholder}
        autoComplete="off"
        onChange={(e) => {
          setText(e.target.value)
          if (keepValue) onSelect(e.target.value.trim().toUpperCase())
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            choose(text)
          } else if (e.key === 'Escape') {
            setOpen(false)
          }
        }}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        className={inputClass}
      />
      {visible && (
        <ul id={listId} role="listbox" className="absolute z-30 mt-1 max-h-60 w-full min-w-64 overflow-auto rounded border border-slate-200 bg-white shadow-lg">
          {results.map((r) => (
            <li key={r.ticker} role="option" aria-selected={false}>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => choose(r.ticker)}
                className="flex w-full items-baseline gap-2 px-2 py-1.5 text-left text-sm hover:bg-slate-100"
              >
                <span className="font-medium">{r.ticker}</span>
                <span className="min-w-0 flex-1 truncate text-slate-600">{r.name}</span>
                {r.instrument_type === 'FUTURE' && (
                  <span className="rounded bg-amber-100 px-1 text-xs text-amber-800">Future</span>
                )}
                <span className="text-xs text-slate-400">{r.exchange ?? ''}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
