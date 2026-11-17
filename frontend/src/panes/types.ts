import type { ComponentType } from 'react'
import type { Pane } from '../dashboard/types'
import type { BrokerAccountView, Portfolio, StrategySchema } from '../types/api'

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
  /**
   * Automatic tab label from the pane's configuration, e.g. "RSI · Main Portfolio".
   * Return undefined when it cannot be worked out yet; the pane title is used instead.
   */
  label?: (pane: Pane, data: LabelData) => string | undefined
}

/** Backend data available for building labels (undefined while loading). */
export interface LabelData {
  portfolios: Portfolio[] | undefined
  strategies: StrategySchema[] | undefined
  /** Broker accounts as of the last SnapTrade refresh ([] when SnapTrade is not set up). */
  accounts: BrokerAccountView[] | undefined
}
