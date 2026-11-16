import { act, render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { Dashboard } from './Dashboard'
import { STORAGE_KEY } from './storage'
import { useDashboard } from './useDashboard'

// Capture the grid's props so drag/resize results can be simulated.
interface GridProps {
  children: ReactNode
  layout: { i: string; x: number; y: number; w: number; h: number; isResizable?: boolean; minW?: number }[]
  onLayoutChange: (layout: { i: string; x: number; y: number; w: number; h: number }[]) => void
  dragConfig: { handle?: string }
}
const grid: { props: GridProps | null } = { props: null }

vi.mock('react-grid-layout', () => ({
  default: (props: GridProps) => {
    grid.props = props
    return <div data-testid="grid">{props.children}</div>
  },
  useContainerWidth: () => ({ width: 1200, containerRef: { current: null }, mounted: true, measureWidth: () => {} }),
}))

function Harness() {
  return <Dashboard dashboard={useDashboard()} />
}

const saved = () => JSON.parse(window.localStorage.getItem(STORAGE_KEY)!)

describe('Dashboard grid integration', () => {
  it('passes the layout, size limits and drag handle to the grid', () => {
    render(<Harness />)
    expect(grid.props!.dragConfig.handle).toBe('.pane-drag-handle')
    expect(grid.props!.layout).toHaveLength(2)
    expect(grid.props!.layout[0]).toMatchObject({ x: 0, y: 0, w: 6, h: 10, minW: 3, isResizable: true })
  })

  it('saves moved and resized panes', () => {
    render(<Harness />)
    const [a, b] = grid.props!.layout
    act(() =>
      grid.props!.onLayoutChange([
        { i: a.i, x: 6, y: 0, w: 6, h: 10 }, // moved right
        { i: b.i, x: 0, y: 0, w: 4, h: 16 }, // moved left and resized
      ]),
    )
    expect(saved().layouts).toEqual([
      { i: a.i, x: 6, y: 0, w: 6, h: 10 },
      { i: b.i, x: 0, y: 0, w: 4, h: 16 },
    ])
    expect(grid.props!.layout[1]).toMatchObject({ x: 0, w: 4, h: 16 })
  })

  it('restores the moved layout on the next start', () => {
    const first = render(<Harness />)
    const [a] = grid.props!.layout
    act(() => grid.props!.onLayoutChange([{ ...a, x: 3, y: 2, w: 9, h: 7 }, grid.props!.layout[1]]))
    first.unmount()

    render(<Harness />)
    expect(grid.props!.layout[0]).toMatchObject({ i: a.i, x: 3, y: 2, w: 9, h: 7 })
    expect(screen.getAllByRole('region')).toHaveLength(2)
  })

  it('marks minimised panes as not resizable', () => {
    render(<Harness />)
    act(() => screen.getByRole('button', { name: 'Minimise Portfolio' }).click())
    expect(grid.props!.layout[0]).toMatchObject({ h: 1, isResizable: false })
  })
})
