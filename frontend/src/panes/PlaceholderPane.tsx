import type { PaneProps } from './types'

/** Temporary pane body until the pane is implemented (Phase 9). */
export function PlaceholderPane({ pane }: PaneProps) {
  return (
    <div className="flex h-full items-center justify-center p-4 text-sm text-slate-400">
      {pane.title} content will appear here.
    </div>
  )
}
