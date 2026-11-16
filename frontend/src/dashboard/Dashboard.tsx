import { useMemo } from 'react'
import ReactGridLayout, { useContainerWidth, type Layout, type LayoutItem } from 'react-grid-layout'
import { PaneGroupFrame } from './PaneGroupFrame'
import { GRID_COLS, GRID_MARGIN, ROW_HEIGHT } from './grid'
import { groupMinSize } from './reducer'
import type { Pane } from './types'
import type { DashboardApi } from './useDashboard'
import { usePaneLabels } from './usePaneLabels'

interface Props {
  dashboard: DashboardApi
}

export function Dashboard({ dashboard }: Props) {
  const { state, layoutChange, removePane, toggleMinimise, updateConfig, selectTab, moveToGroup, detachPane, reorderTab } = dashboard
  // Measure before the first render so tiles do not jump from a default width.
  const { width, containerRef, mounted } = useContainerWidth({ measureBeforeMount: true })
  const labels = usePaneLabels(state)

  const layout: Layout = useMemo(
    () =>
      state.layouts.map((l): LayoutItem => {
        const group = state.groups.find((g) => g.id === l.i)
        const min = group ? groupMinSize(state, group) : { w: 2, h: 2 }
        const minimised = l.i in state.minimised
        return { ...l, minW: min.w, minH: minimised ? 1 : min.h, isResizable: !minimised }
      }),
    [state],
  )

  const paneById = useMemo(() => new Map(state.panes.map((p) => [p.id, p])), [state.panes])
  const groupLabel = (groupId: string) => {
    const group = state.groups.find((g) => g.id === groupId)
    if (!group) return groupId
    // Named after the first tab (stable while tabs are switched or added), plus a count.
    const first = group.paneIds[0]
    const name = labels[first] ?? paneById.get(first)?.title ?? groupId
    return group.paneIds.length > 1 ? `${name} (+${group.paneIds.length - 1} more)` : name
  }

  return (
    <div ref={containerRef} className="w-full">
      {state.groups.length === 0 ? (
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
            {state.groups.map((group) => (
              <div key={group.id} data-testid={`tile-${group.id}`}>
                <PaneGroupFrame
                  group={group}
                  panes={group.paneIds.map((id) => paneById.get(id)).filter((p): p is Pane => p !== undefined)}
                  labels={labels}
                  targets={state.groups.filter((g) => g.id !== group.id).map((g) => ({ id: g.id, label: groupLabel(g.id) }))}
                  minimised={group.id in state.minimised}
                  onSelect={(paneId) => selectTab(group.id, paneId)}
                  onRemove={removePane}
                  onToggleMinimise={() => toggleMinimise(group.id)}
                  onConfigChange={updateConfig}
                  onMoveTo={moveToGroup}
                  onDetach={detachPane}
                  onReorder={reorderTab}
                />
              </div>
            ))}
          </ReactGridLayout>
        )
      )}
    </div>
  )
}
