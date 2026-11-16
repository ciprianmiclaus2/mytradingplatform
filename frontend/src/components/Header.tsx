import { useState } from 'react'
import type { DashboardApi } from '../dashboard/useDashboard'
import type { BackendHealthState } from '../hooks/useBackendHealth'
import { paneDefinitions } from '../panes/registry'
import { BackendStatus } from './BackendStatus'
import { ConfirmDialog } from './ConfirmDialog'
import { Menu } from './Menu'

interface Props {
  dashboard: DashboardApi
  health: BackendHealthState
  onRetryHealth: () => void
}

export function Header({ dashboard, health, onRetryHealth }: Props) {
  const [confirmReset, setConfirmReset] = useState(false)

  return (
    <header className="flex flex-wrap items-center gap-3 border-b border-slate-200 bg-white px-4 py-2">
      <h1 className="mr-2 text-lg font-semibold text-slate-900">My Trading Platform</h1>
      <Menu
        label="Menu"
        items={[
          {
            key: 'reset',
            label: 'Reset layout',
            description: 'Restore the default panes and positions',
            onSelect: () => setConfirmReset(true),
          },
        ]}
      />
      <Menu
        label="Add pane"
        items={paneDefinitions().map((def) => ({
          key: def.type,
          label: def.title,
          description: def.description,
          onSelect: () => dashboard.addPane(def.type),
        }))}
      />
      <div className="ml-auto">
        <BackendStatus state={health} onRetry={onRetryHealth} />
      </div>
      {confirmReset && (
        <ConfirmDialog
          title="Reset layout?"
          message="All panes and their settings will be replaced by the default layout."
          confirmLabel="Reset"
          onConfirm={() => {
            setConfirmReset(false)
            dashboard.resetLayout()
          }}
          onCancel={() => setConfirmReset(false)}
        />
      )}
    </header>
  )
}
