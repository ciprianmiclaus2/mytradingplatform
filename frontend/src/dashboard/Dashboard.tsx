import { useMemo } from 'react'
import ReactGridLayout, { useContainerWidth, type Layout, type LayoutItem } from 'react-grid-layout'
import { getPaneDefinition } from '../panes/registry'
import { PaneFrame } from './PaneFrame'
import { GRID_COLS, GRID_MARGIN, ROW_HEIGHT } from './grid'
import type { DashboardApi } from './useDashboard'

interface Props {
  dashboard: DashboardApi
}

export function Dashboard({ dashboard }: Props) {
  const { state, layoutChange, removePane, toggleMinimise, updateConfig } = dashboard
  // Measure before the first render so panes do not jump from a default width.
  const { width, containerRef, mounted } = useContainerWidth({ measureBeforeMount: true })

  const layout: Layout = useMemo(
    () =>
      state.layouts.map((l): LayoutItem => {
        const pane = state.panes.find((p) => p.id === l.i)
        const def = pane ? getPaneDefinition(pane.type) : undefined
        const minimised = l.i in state.minimised
        return {
          ...l,
          minW: def?.minSize.w ?? 2,
          minH: minimised ? 1 : (def?.minSize.h ?? 2),
          isResizable: !minimised,
        }
      }),
    [state.layouts, state.panes, state.minimised],
  )

  return (
    <div ref={containerRef} className="w-full">
      {state.panes.length === 0 ? (
        <div className="m-6 rounded-md border border-dashed border-slate-300 p-10 text-center text-sm text-slate-500">
          The dashboard is empty. Use <strong>Add pane</strong> to add a portfolio, positions or strategy pane.
        </div>
      ) : (
        mounted && (
          <ReactGridLayout
            width={width}
            layout={layout}
            gridConfig={{ cols: GRID_COLS, rowHeight: ROW_HEIGHT, margin: GRID_MARGIN }}
            dragConfig={{ enabled: true, handle: '.pane-drag-handle' }}
            resizeConfig={{ enabled: true }}
            onLayoutChange={layoutChange}
          >
            {state.panes.map((pane) => (
              <div key={pane.id} data-testid={`pane-${pane.id}`}>
                <PaneFrame
                  pane={pane}
                  minimised={pane.id in state.minimised}
                  onRemove={() => removePane(pane.id)}
                  onToggleMinimise={() => toggleMinimise(pane.id)}
                  onConfigChange={(config) => updateConfig(pane.id, config)}
                />
              </div>
            ))}
          </ReactGridLayout>
        )
      )}
    </div>
  )
}
