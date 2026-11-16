import { useEffect, useRef } from 'react'

interface Props {
  title: string
  message: string
  confirmLabel?: string
  destructive?: boolean
  onConfirm: () => void
  onCancel: () => void
}

/** Modal confirmation for destructive actions. Escape or Cancel dismisses it. */
export function ConfirmDialog({ title, message, confirmLabel = 'Confirm', destructive = true, onConfirm, onCancel }: Props) {
  const cancelRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    cancelRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onCancel])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" onMouseDown={onCancel}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        className="w-full max-w-sm rounded-lg bg-white p-5 shadow-xl"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h2 id="confirm-title" className="text-base font-semibold text-slate-900">
          {title}
        </h2>
        <p className="mt-2 text-sm text-slate-600">{message}</p>
        <div className="mt-5 flex justify-end gap-2">
          <button
            ref={cancelRef}
            type="button"
            onClick={onCancel}
            className="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className={`rounded px-3 py-1.5 text-sm text-white ${destructive ? 'bg-red-600 hover:bg-red-700' : 'bg-slate-800 hover:bg-slate-900'}`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
