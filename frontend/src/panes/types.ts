import type { ComponentType } from 'react'
import type { Pane } from '../dashboard/types'

export interface PaneProps {
  pane: Pane
  /** Replace the pane's configuration (persisted with the layout). */
  onConfigChange: (config: Record<string, unknown>) => void
}

export interface PaneDefinition {
  type: string
  /** Default title for new panes of this type. */
  title: string
  description: string
  component: ComponentType<PaneProps>
  defaultSize: { w: number; h: number }
  minSize: { w: number; h: number }
  defaultConfig: () => Record<string, unknown>
}
