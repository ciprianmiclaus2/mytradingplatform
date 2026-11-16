import { useId, useRef, useState, type DragEvent, type KeyboardEvent } from 'react'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { Menu, type MenuItem } from '../components/Menu'
import { getPaneDefinition } from '../panes/registry'
import { PaneErrorBoundary } from './PaneErrorBoundary'
import type { Pane, PaneGroup } from './types'

interface Props {
  group: PaneGroup
  panes: Pane[]
  labels: Record<string, string>
  /** Other tiles a tab can move to, with a label for each. */
  targets: { id: string; label: string }[]
  minimised: boolean
  onSelect: (paneId: string) => void
  onRemove: (paneId: string) => void
  onToggleMinimise: () => void
  onConfigChange: (paneId: string, config: Record<string, unknown>) => void
  onMoveTo: (paneId: string, groupId: string) => void
  onDetach: (paneId: string) => void
  onReorder: (paneId: string, index: number) => void
}

const DRAG_TYPE = 'application/x-mtp-tab'

/**
 * A grid tile: a tab bar and one panel per pane. Every pane stays mounted
 * (inactive ones are hidden), so hidden strategies keep refreshing.
 * The grip and the empty part of the header move the tile.
 */
export function PaneGroupFrame({
  group,
  panes,
  labels,
  targets,
  minimised,
  onSelect,
  onRemove,
  onToggleMinimise,
  onConfigChange,
  onMoveTo,
  onDetach,
  onReorder,
}: Props) {
  const uid = useId()
  const [confirmRemove, setConfirmRemove] = useState<Pane | null>(null)
  const [dragging, setDragging] = useState<string | null>(null)
  const [dropIndex, setDropIndex] = useState<number | null>(null)
  const tabRefs = useRef(new Map<string, HTMLButtonElement>())
  const active = panes.find((p) => p.id === group.active) ?? panes[0]
  const label = (pane: Pane) => labels[pane.id] ?? pane.title
  const tabId = (pane: Pane) => `${uid}-tab-${pane.id}`
  const panelId = (pane: Pane) => `${uid}-panel-${pane.id}`

  const focusTab = (index: number) => {
    const pane = panes[(index + panes.length) % panes.length]
    onSelect(pane.id)
    tabRefs.current.get(pane.id)?.focus()
  }

  const onTabKey = (e: KeyboardEvent, index: number) => {
    const moves: Record<string, number> = { ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: panes.length - 1 }
    if (e.key in moves) {
      e.preventDefault()
      focusTab(moves[e.key])
    } else if (e.key === 'Delete') {
      e.preventDefault()
      setConfirmRemove(panes[index])
    }
  }

  // Reordering by dragging a tab within this tab bar (native drag and drop).
  const onDragOver = (e: DragEvent, index: number) => {
    if (!dragging) return
    e.preventDefault()
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    setDropIndex(e.clientX < rect.left + rect.width / 2 ? index : index + 1)
  }
  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    if (dragging && dropIndex !== null) {
      const from = group.paneIds.indexOf(dragging)
      onReorder(dragging, from < dropIndex ? dropIndex - 1 : dropIndex)
    }
    setDragging(null)
    setDropIndex(null)
  }

  const menuItems: MenuItem[] = active
    ? [
        ...targets.map((t) => ({
          key: `move-${t.id}`,
          label: `Move “${label(active)}” to: ${t.label}`,
          onSelect: () => onMoveTo(active.id, t.id),
        })),
        ...(panes.length > 1
          ? [{ key: 'detach', label: `Detach “${label(active)}” into its own pane`, onSelect: () => onDetach(active.id) }]
          : []),
        { key: 'remove', label: `Remove “${label(active)}”…`, onSelect: () => setConfirmRemove(active) },
      ]
    : []

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-md border border-slate-200 bg-white shadow-sm">
      <header className="flex h-8 shrink-0 items-stretch border-b border-slate-200 bg-slate-50">
        <span className="pane-drag-handle flex cursor-move items-center px-1.5 text-slate-400 select-none" title="Drag to move" aria-hidden>
          ⠿
        </span>
        <div role="tablist" aria-label="Panes in this tile" className="flex min-w-0 overflow-x-auto" onDrop={onDrop}>
          {panes.map((pane, index) => {
            const selected = pane.id === active?.id
            return (
              <div
                key={pane.id}
                draggable={panes.length > 1}
                onDragStart={(e) => {
                  e.dataTransfer.setData(DRAG_TYPE, pane.id)
                  e.dataTransfer.effectAllowed = 'move'
                  setDragging(pane.id)
                }}
                onDragEnd={() => {
                  setDragging(null)
                  setDropIndex(null)
                }}
                onDragOver={(e) => onDragOver(e, index)}
                className={`group/tab relative flex max-w-60 min-w-0 shrink-0 items-center border-r border-slate-200 ${
                  selected ? 'bg-white text-slate-900' : 'text-slate-500 hover:bg-slate-100 hover:text-slate-800'
                } ${dragging === pane.id ? 'opacity-50' : ''}`}
              >
                {dropIndex === index && dragging && <span aria-hidden className="absolute inset-y-1 left-0 w-0.5 bg-sky-500" />}
                {dropIndex === index + 1 && index === panes.length - 1 && dragging && (
                  <span aria-hidden className="absolute inset-y-1 right-0 w-0.5 bg-sky-500" />
                )}
                <button
                  ref={(el) => {
                    if (el) tabRefs.current.set(pane.id, el)
                    else tabRefs.current.delete(pane.id)
                  }}
                  type="button"
                  role="tab"
                  id={tabId(pane)}
                  aria-selected={selected}
                  aria-controls={panelId(pane)}
                  tabIndex={selected ? 0 : -1}
                  title={label(pane)}
                  onClick={() => onSelect(pane.id)}
                  onKeyDown={(e) => onTabKey(e, index)}
                  className={`min-w-0 truncate py-1 pr-1 pl-3 text-sm ${selected ? 'font-medium' : ''} ${selected && !minimised ? 'border-b-2 border-sky-500' : 'border-b-2 border-transparent'}`}
                >
                  {label(pane)}
                </button>
                <button
                  type="button"
                  tabIndex={-1}
                  aria-label={`Remove ${label(pane)}`}
                  title="Remove"
                  onClick={() => setConfirmRemove(pane)}
                  className="mr-1 rounded px-1 text-slate-400 hover:bg-red-50 hover:text-red-600"
                >
                  ×
                </button>
              </div>
            )
          })}
        </div>
        <div className="pane-drag-handle min-w-6 flex-1 cursor-move" title="Drag to move" aria-hidden />
        {active && <Menu label="⋯" ariaLabel={`Tab options for ${label(active)}`} items={menuItems} align="right" compact />}
        <button
          type="button"
          onClick={onToggleMinimise}
          aria-label={minimised ? `Restore ${active ? label(active) : 'tile'}` : `Minimise ${active ? label(active) : 'tile'}`}
          title={minimised ? 'Restore' : 'Minimise'}
          className="w-8 text-slate-500 hover:bg-slate-200 hover:text-slate-800"
        >
          {minimised ? '▢' : '–'}
        </button>
      </header>
      {panes.map((pane) => {
        const def = getPaneDefinition(pane.type)
        const Body = def?.component
        return (
          <section
            key={pane.id}
            id={panelId(pane)}
            role="tabpanel"
            aria-labelledby={tabId(pane)}
            hidden={minimised || pane.id !== active?.id}
            className="min-h-0 flex-1 overflow-auto"
          >
            {Body ? (
              <PaneErrorBoundary>
                <Body pane={pane} onConfigChange={(config) => onConfigChange(pane.id, config)} />
              </PaneErrorBoundary>
            ) : (
              <p className="p-4 text-sm text-red-600">Unknown pane type “{pane.type}”.</p>
            )}
          </section>
        )
      })}
      {confirmRemove && (
        <ConfirmDialog
          title="Remove pane?"
          message={`“${label(confirmRemove)}” and its settings will be removed from the dashboard.`}
          confirmLabel="Remove"
          onConfirm={() => {
            const pane = confirmRemove
            setConfirmRemove(null)
            onRemove(pane.id)
          }}
          onCancel={() => setConfirmRemove(null)}
        />
      )}
    </div>
  )
}
