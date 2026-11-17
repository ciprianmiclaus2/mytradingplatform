import { useCallback, useState } from 'react'
import type { DashboardApi } from '../dashboard/useDashboard'
import type { BackendHealthState } from '../hooks/useBackendHealth'
import { SnapTradeSettingsDialog } from '../panes/broker/SnapTradeSettingsDialog'
import { paneDefinitions } from '../panes/registry'
import { dashboardExtraTickers } from '../refresh/dashboardTickers'
import { useMarketRefresh } from '../refresh/useMarketRefresh'
import { BackendStatus } from './BackendStatus'
import { ConfirmDialog } from './ConfirmDialog'
import { Menu } from './Menu'
import { RefreshControl } from './RefreshControl'

interface Props {
  dashboard: DashboardApi
  health: BackendHealthState
  onRetryHealth: () => void
}

export function Header({ dashboard, health, onRetryHealth }: Props) {
  const [confirmReset, setConfirmReset] = useState(false)
  const [snapTradeOpen, setSnapTradeOpen] = useState(false)
  const { state } = dashboard
  const getExtraTickers = useCallback(() => dashboardExtraTickers(state), [state])
  const refresh = useMarketRefresh(getExtraTickers)

  return (
    <header className="flex flex-wrap items-center gap-3 border-b border-slate-200 bg-white px-4 py-2">
      <h1 className="mr-2 text-lg font-semibold text-slate-900">My Trading Platform</h1>
      <Menu
        label="Menu"
        items={[
          {
            key: 'snaptrade',
            label: 'SnapTrade settings…',
            description: 'Connect broker accounts; add a positions pane per account',
            onSelect: () => setSnapTradeOpen(true),
          },
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
      <RefreshControl {...refresh} onRefresh={refresh.refresh} />
      <div className="ml-auto">
        <BackendStatus state={health} onRetry={onRetryHealth} />
      </div>
      {snapTradeOpen && <SnapTradeSettingsDialog onClose={() => setSnapTradeOpen(false)} />}
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
