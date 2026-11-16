import { useEffect, useId, useRef, useState } from 'react'

export interface MenuItem {
  key: string
  label: string
  description?: string
  onSelect: () => void
}

interface Props {
  label: string
  items: MenuItem[]
  align?: 'left' | 'right'
  /** Accessible name when the visible label is a symbol. */
  ariaLabel?: string
  /** Small button without the ▾ marker (pane toolbars). */
  compact?: boolean
}

/** Simple dropdown menu; closes on selection, outside click or Escape. */
export function Menu({ label, items, align = 'left', ariaLabel, compact = false }: Props) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const menuId = useId()

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        aria-label={ariaLabel}
        onClick={() => setOpen((v) => !v)}
        className={`rounded border border-slate-300 bg-white text-sm hover:bg-slate-50 ${compact ? 'px-2 py-1' : 'px-3 py-1.5'}`}
      >
        {compact ? label : `${label} ▾`}
      </button>
      {open && (
        <ul
          id={menuId}
          role="menu"
          aria-label={ariaLabel ?? label}
          className={`absolute z-40 mt-1 min-w-56 rounded-md border border-slate-200 bg-white py-1 shadow-lg ${align === 'right' ? 'right-0' : 'left-0'}`}
        >
          {items.map((item) => (
            <li key={item.key} role="none">
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setOpen(false)
                  item.onSelect()
                }}
                className="block w-full px-3 py-2 text-left text-sm hover:bg-slate-100"
              >
                <span className="block text-slate-900">{item.label}</span>
                {item.description && <span className="block text-xs text-slate-500">{item.description}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
