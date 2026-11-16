import { useState } from 'react'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { getPaneDefinition } from '../panes/registry'
import type { Pane } from './types'

interface Props {
  pane: Pane
  minimised: boolean
  onRemove: () => void
  onToggleMinimise: () => void
  onConfigChange: (config: Record<string, unknown>) => void
}

/** Pane chrome: draggable title bar, minimise and remove controls, and the pane body. */
export function PaneFrame({ pane, minimised, onRemove, onToggleMinimise, onConfigChange }: Props) {
  const [confirming, setConfirming] = useState(false)
  const def = getPaneDefinition(pane.type)
  const Body = def?.component

  return (
    <section aria-label={pane.title} className="flex h-full flex-col overflow-hidden rounded-md border border-slate-200 bg-white shadow-sm">
      <header className="flex h-8 shrink-0 items-center border-b border-slate-200 bg-slate-50">
        <h2 className="pane-drag-handle min-w-0 flex-1 cursor-move truncate px-3 text-sm font-medium text-slate-700" title="Drag to move">
          {pane.title}
        </h2>
        <button
          type="button"
          onClick={onToggleMinimise}
          aria-label={minimised ? `Restore ${pane.title}` : `Minimise ${pane.title}`}
          title={minimised ? 'Restore' : 'Minimise'}
          className="h-8 w-8 text-slate-500 hover:bg-slate-200 hover:text-slate-800"
        >
          {minimised ? '▢' : '–'}
        </button>
        <button
          type="button"
          onClick={() => setConfirming(true)}
          aria-label={`Remove ${pane.title}`}
          title="Remove pane"
          className="h-8 w-8 text-slate-500 hover:bg-red-50 hover:text-red-600"
        >
          ×
        </button>
      </header>
      {!minimised && (
        <div className="min-h-0 flex-1 overflow-auto">
          {Body ? (
            <Body pane={pane} onConfigChange={onConfigChange} />
          ) : (
            <p className="p-4 text-sm text-red-600">Unknown pane type “{pane.type}”.</p>
          )}
        </div>
      )}
      {confirming && (
        <ConfirmDialog
          title="Remove pane?"
          message={`“${pane.title}” and its settings will be removed from the dashboard.`}
          confirmLabel="Remove"
          onConfirm={() => {
            setConfirming(false)
            onRemove()
          }}
          onCancel={() => setConfirming(false)}
        />
      )}
    </section>
  )
}
