import { useState, type FormEvent, type ReactNode } from 'react'
import { closePosition, createPosition, updatePosition } from '../../api/positions'
import { DialogButtons, FormError, Modal, inputClass } from '../../components/Modal'
import { TickerSearch } from '../../components/TickerSearch'
import { errorMessage } from '../../hooks/useApiData'
import type { PositionUpdate, PositionView } from '../../types/api'
import { todayIso } from '../../utils/format'
import { decimalError } from './validation'

/** Number to an input value without float noise (e.g. 0.1 + 0.2). */
function toInput(value: number | null | undefined): string {
  if (value === null || value === undefined) return ''
  return String(Number(value.toFixed(8)))
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="mb-3 block text-sm">
      <span className="mb-1 block text-slate-600">{label}</span>
      {children}
      {hint && <span className="mt-0.5 block text-xs text-slate-400">{hint}</span>}
    </label>
  )
}

function useSubmit(onDone: () => void) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const run = async (validate: () => string | null, action: () => Promise<unknown>) => {
    const problem = validate()
    if (problem) {
      setError(problem)
      return
    }
    setBusy(true)
    setError(null)
    try {
      await action()
      onDone()
    } catch (err) {
      setError(errorMessage(err))
      setBusy(false)
    }
  }
  return { busy, error, run }
}

const firstError = (...errors: (string | null)[]) => errors.find((e) => e !== null) ?? null

interface AddProps {
  portfolioId: string
  onDone: () => void
  onCancel: () => void
}

export function AddPositionDialog({ portfolioId, onDone, onCancel }: AddProps) {
  const [ticker, setTicker] = useState('')
  const [quantity, setQuantity] = useState('')
  const [entryPrice, setEntryPrice] = useState('')
  const [entryDate, setEntryDate] = useState(todayIso())
  const [notes, setNotes] = useState('')
  const { busy, error, run } = useSubmit(onDone)

  const submit = (e: FormEvent) => {
    e.preventDefault()
    void run(
      () =>
        firstError(
          ticker.trim() ? null : 'Ticker is required.',
          decimalError(quantity, 'Quantity', true),
          decimalError(entryPrice, 'Entry price', false),
        ),
      () =>
        createPosition(portfolioId, {
          ticker: ticker.trim(),
          quantity: quantity.trim(),
          ...(entryPrice.trim() ? { entry_price: entryPrice.trim() } : {}),
          ...(entryDate ? { entry_date: entryDate } : {}),
          notes,
        }),
    )
  }

  return (
    <Modal title="Add position" onClose={onCancel}>
      <form onSubmit={submit} noValidate>
        <Field label="Ticker">
          <TickerSearch keepValue label="Ticker" placeholder="e.g. AAPL" onSelect={setTicker} />
        </Field>
        <Field label="Quantity">
          <input aria-label="Quantity" inputMode="decimal" value={quantity} onChange={(e) => setQuantity(e.target.value)} className={inputClass} />
        </Field>
        <Field label="Entry price" hint="Leave blank to use the latest market price.">
          <input
            aria-label="Entry price"
            inputMode="decimal"
            placeholder="Latest price"
            value={entryPrice}
            onChange={(e) => setEntryPrice(e.target.value)}
            className={inputClass}
          />
        </Field>
        <Field label="Entry date">
          <input aria-label="Entry date" type="date" value={entryDate} onChange={(e) => setEntryDate(e.target.value)} className={inputClass} />
        </Field>
        <Field label="Notes">
          <textarea aria-label="Notes" rows={2} maxLength={1000} value={notes} onChange={(e) => setNotes(e.target.value)} className={inputClass} />
        </Field>
        <FormError message={error} />
        <DialogButtons onCancel={onCancel} submitLabel="Add" busy={busy} />
      </form>
    </Modal>
  )
}

interface PositionProps {
  position: PositionView
  onDone: () => void
  onCancel: () => void
}

/** Edit an open position (quantity, entry) or a closed one (exit). Only changed fields are sent. */
export function EditPositionDialog({ position, onDone, onCancel }: PositionProps) {
  const open = position.status === 'OPEN'
  const [quantity, setQuantity] = useState(toInput(position.quantity))
  const [entryPrice, setEntryPrice] = useState(toInput(position.entry_price))
  const [entryDate, setEntryDate] = useState(position.entry_date ?? '')
  const [exitPrice, setExitPrice] = useState(toInput(position.exit_price))
  const [exitDate, setExitDate] = useState(position.exit_date ?? '')
  const [notes, setNotes] = useState(position.notes)
  const { busy, error, run } = useSubmit(onDone)

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const body: PositionUpdate = {}
    if (open) {
      if (quantity.trim() !== toInput(position.quantity)) body.quantity = quantity.trim()
      if (entryPrice.trim() !== toInput(position.entry_price)) body.entry_price = entryPrice.trim()
      if (entryDate && entryDate !== (position.entry_date ?? '')) body.entry_date = entryDate
    } else {
      if (exitPrice.trim() !== toInput(position.exit_price)) body.exit_price = exitPrice.trim()
      if (exitDate && exitDate !== (position.exit_date ?? '')) body.exit_date = exitDate
    }
    if (notes !== position.notes) body.notes = notes
    void run(
      () =>
        open
          ? firstError(decimalError(quantity, 'Quantity', true), decimalError(entryPrice, 'Entry price', true))
          : decimalError(exitPrice, 'Exit price', true),
      () => (Object.keys(body).length > 0 ? updatePosition(position.id, body) : Promise.resolve()),
    )
  }

  return (
    <Modal title={`Edit ${position.ticker}${open ? '' : ' (closed)'}`} onClose={onCancel}>
      <form onSubmit={submit} noValidate>
        {open ? (
          <>
            <Field label="Quantity">
              <input aria-label="Quantity" inputMode="decimal" value={quantity} onChange={(e) => setQuantity(e.target.value)} className={inputClass} />
            </Field>
            <Field label="Entry price">
              <input aria-label="Entry price" inputMode="decimal" value={entryPrice} onChange={(e) => setEntryPrice(e.target.value)} className={inputClass} />
            </Field>
            <Field label="Entry date">
              <input aria-label="Entry date" type="date" value={entryDate} onChange={(e) => setEntryDate(e.target.value)} className={inputClass} />
            </Field>
          </>
        ) : (
          <>
            <Field label="Exit price">
              <input aria-label="Exit price" inputMode="decimal" value={exitPrice} onChange={(e) => setExitPrice(e.target.value)} className={inputClass} />
            </Field>
            <Field label="Exit date">
              <input aria-label="Exit date" type="date" value={exitDate} onChange={(e) => setExitDate(e.target.value)} className={inputClass} />
            </Field>
          </>
        )}
        <Field label="Notes">
          <textarea aria-label="Notes" rows={2} maxLength={1000} value={notes} onChange={(e) => setNotes(e.target.value)} className={inputClass} />
        </Field>
        <FormError message={error} />
        <DialogButtons onCancel={onCancel} submitLabel="Save" busy={busy} />
      </form>
    </Modal>
  )
}

/** Close a position. The dialog itself is the confirmation step. */
export function ClosePositionDialog({ position, onDone, onCancel }: PositionProps) {
  const [exitPrice, setExitPrice] = useState(toInput(position.current_price))
  const [exitDate, setExitDate] = useState(todayIso())
  const { busy, error, run } = useSubmit(onDone)

  const submit = (e: FormEvent) => {
    e.preventDefault()
    void run(
      () => decimalError(exitPrice, 'Exit price', false),
      () =>
        closePosition(position.id, {
          ...(exitPrice.trim() ? { exit_price: exitPrice.trim() } : {}),
          ...(exitDate ? { exit_date: exitDate } : {}),
        }),
    )
  }

  return (
    <Modal title={`Close ${position.ticker}?`} onClose={onCancel}>
      <form onSubmit={submit} noValidate>
        <p className="mb-3 text-sm text-slate-600">
          The whole position will be closed and moved to the closed history.
        </p>
        <Field label="Exit price" hint="Defaults to the latest market price.">
          <input
            aria-label="Exit price"
            inputMode="decimal"
            placeholder="Latest price"
            value={exitPrice}
            onChange={(e) => setExitPrice(e.target.value)}
            className={inputClass}
          />
        </Field>
        <Field label="Exit date">
          <input aria-label="Exit date" type="date" value={exitDate} onChange={(e) => setExitDate(e.target.value)} className={inputClass} />
        </Field>
        <FormError message={error} />
        <DialogButtons onCancel={onCancel} submitLabel="Close position" busy={busy} />
      </form>
    </Modal>
  )
}
