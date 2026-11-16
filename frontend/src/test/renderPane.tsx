import { render } from '@testing-library/react'
import { useState } from 'react'
import type { Pane } from '../dashboard/types'
import type { PaneProps } from '../panes/types'

/** Render a pane component with its configuration held in state, like the dashboard does. */
export function renderPane(
  Component: (props: PaneProps) => React.ReactNode,
  { id = 'pane-1', type = 'x', config = {} }: { id?: string; type?: string; config?: Record<string, unknown> } = {},
) {
  const configs: Record<string, unknown>[] = []
  function Harness() {
    const [current, setCurrent] = useState(config)
    const pane: Pane = { id, type, title: type, config: current }
    return (
      <Component
        pane={pane}
        onConfigChange={(next) => {
          configs.push(next)
          setCurrent(next)
        }}
      />
    )
  }
  const result = render(<Harness />)
  return { ...result, configs, lastConfig: () => configs[configs.length - 1] }
}
