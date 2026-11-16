import { Header } from './components/Header'
import { Dashboard } from './dashboard/Dashboard'
import { useDashboard } from './dashboard/useDashboard'
import { useBackendHealth } from './hooks/useBackendHealth'

export default function App() {
  const { state: health, recheck } = useBackendHealth()
  const dashboard = useDashboard()

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <Header dashboard={dashboard} health={health} onRetryHealth={recheck} />
      {dashboard.warning && (
        <div role="alert" className="flex items-center gap-3 border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800">
          <span>{dashboard.warning}</span>
          <button type="button" onClick={dashboard.dismissWarning} className="ml-auto underline">
            Dismiss
          </button>
        </div>
      )}
      {!dashboard.saveOk && (
        <div className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800">
          The layout cannot be saved in this browser; changes will be lost when the page is closed.
        </div>
      )}
      <main className="p-1">
        <Dashboard dashboard={dashboard} />
      </main>
    </div>
  )
}
