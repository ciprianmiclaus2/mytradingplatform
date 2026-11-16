import { useEffect, useId, useRef, type ReactNode } from 'react'

interface Props {
  title: string
  children: ReactNode
  onClose: () => void
}

/** Modal dialog shell. Escape or a click on the backdrop closes it. */
export function Modal({ title, children, onClose }: Props) {
  const titleId = useId()
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    panelRef.current?.querySelector<HTMLElement>('input, select, textarea, button')?.focus()
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" onMouseDown={onClose}>
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="max-h-full w-full max-w-md overflow-auto rounded-lg bg-white p-5 shadow-xl"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h2 id={titleId} className="text-base font-semibold text-slate-900">
          {title}
        </h2>
        <div className="mt-3">{children}</div>
      </div>
    </div>
  )
}

export const inputClass =
  'w-full rounded border border-slate-300 px-2 py-1 text-sm focus:border-slate-500 focus:outline-none disabled:bg-slate-100'
export const buttonClass = 'rounded border border-slate-300 bg-white px-2.5 py-1 text-sm hover:bg-slate-50 disabled:opacity-50'
export const primaryButtonClass = 'rounded bg-slate-800 px-3 py-1 text-sm text-white hover:bg-slate-900 disabled:opacity-50'

export function DialogButtons({ onCancel, submitLabel, busy }: { onCancel: () => void; submitLabel: string; busy?: boolean }) {
  return (
    <div className="mt-5 flex justify-end gap-2">
      <button type="button" onClick={onCancel} className={buttonClass}>
        Cancel
      </button>
      <button type="submit" disabled={busy} className={primaryButtonClass}>
        {busy ? 'Saving…' : submitLabel}
      </button>
    </div>
  )
}

export function FormError({ message }: { message: string | null }) {
  if (!message) return null
  return (
    <p role="alert" className="mt-3 rounded bg-red-50 px-2 py-1.5 text-sm text-red-700">
      {message}
    </p>
  )
}
