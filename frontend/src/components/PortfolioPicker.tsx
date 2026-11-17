import { useState, type FormEvent } from 'react'
import { createPortfolio, deletePortfolio, updatePortfolio } from '../api/portfolios'
import { errorMessage } from '../hooks/useApiData'
import { notifyDataChanged } from '../hooks/dataVersion'
import type { Portfolio, PortfolioType } from '../types/api'
import { ConfirmDialog } from './ConfirmDialog'
import { DialogButtons, FormError, Modal, inputClass } from './Modal'
import { Menu } from './Menu'

const TYPE_LABEL: Record<PortfolioType, string> = { watchlist: 'Watchlist' }
const NEW_LABEL: Record<PortfolioType, string> = { watchlist: 'watchlist' }

interface Props {
  portfolios: Portfolio[]
  value: string | undefined
  onChange: (id: string) => void
  /** Portfolio types that can be chosen (and created) here. */
  types: readonly PortfolioType[]
  label?: string
}

type Dialog = { kind: 'create'; type: PortfolioType } | { kind: 'rename' } | { kind: 'delete' } | null

/** Portfolio selector with create, rename and delete. */
export function PortfolioPicker({ portfolios, value, onChange, types, label = 'Portfolio' }: Props) {
  const [dialog, setDialog] = useState<Dialog>(null)
  const [error, setError] = useState<string | null>(null)
  const choices = portfolios.filter((p) => types.includes(p.type))
  const current = choices.find((p) => p.id === value)

  const remove = async () => {
    if (!current) return
    try {
      await deletePortfolio(current.id)
      setDialog(null)
      notifyDataChanged()
    } catch (err) {
      setDialog(null)
      setError(errorMessage(err))
    }
  }

  const menuItems = [
    ...types.map((type) => ({
      key: `new-${type}`,
      label: `New ${NEW_LABEL[type]}…`,
      onSelect: () => setDialog({ kind: 'create', type }),
    })),
    ...(current
      ? [
          { key: 'rename', label: 'Rename…', onSelect: () => setDialog({ kind: 'rename' }) },
          { key: 'delete', label: 'Delete…', onSelect: () => setDialog({ kind: 'delete' }) },
        ]
      : []),
  ]

  return (
    <div className="flex min-w-0 items-center gap-1">
      <select
        aria-label={label}
        value={current?.id ?? ''}
        onChange={(e) => {
          setError(null)
          onChange(e.target.value)
        }}
        className="min-w-0 max-w-56 rounded border border-slate-300 bg-white px-1.5 py-1 text-sm"
      >
        {!current && <option value="">Choose…</option>}
        {choices.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
            {types.length > 1 ? ` (${TYPE_LABEL[p.type]})` : ''}
          </option>
        ))}
      </select>
      <Menu label="⋯" ariaLabel={`Manage ${label.toLowerCase()}`} items={menuItems} compact />
      {error && (
        <span role="alert" className="truncate text-xs text-red-600" title={error}>
          {error}
        </span>
      )}
      {dialog?.kind === 'create' && (
        <NameDialog
          title={`New ${NEW_LABEL[dialog.type]}`}
          initial=""
          submitLabel="Create"
          onCancel={() => setDialog(null)}
          onSubmit={async (name) => {
            const created = await createPortfolio({ name, type: dialog.type })
            setDialog(null)
            notifyDataChanged()
            onChange(created.id)
          }}
        />
      )}
      {dialog?.kind === 'rename' && current && (
        <NameDialog
          title={`Rename “${current.name}”`}
          initial={current.name}
          submitLabel="Rename"
          onCancel={() => setDialog(null)}
          onSubmit={async (name) => {
            await updatePortfolio(current.id, { name })
            setDialog(null)
            notifyDataChanged()
          }}
        />
      )}
      {dialog?.kind === 'delete' && current && (
        <ConfirmDialog
          title="Delete portfolio?"
          message={`“${current.name}” and its tickers will be deleted. A backup is taken first.`}
          confirmLabel="Delete"
          onConfirm={remove}
          onCancel={() => setDialog(null)}
        />
      )}
    </div>
  )
}

function NameDialog({
  title,
  initial,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  title: string
  initial: string
  submitLabel: string
  onSubmit: (name: string) => Promise<void>
  onCancel: () => void
}) {
  const [name, setName] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!name.trim()) {
      setError('Name is required.')
      return
    }
    setBusy(true)
    try {
      await onSubmit(name.trim())
    } catch (err) {
      setError(errorMessage(err))
      setBusy(false)
    }
  }

  return (
    <Modal title={title} onClose={onCancel}>
      <form onSubmit={submit}>
        <label className="block text-sm">
          <span className="mb-1 block text-slate-600">Name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={100} className={inputClass} />
        </label>
        <FormError message={error} />
        <DialogButtons onCancel={onCancel} submitLabel={submitLabel} busy={busy} />
      </form>
    </Modal>
  )
}
