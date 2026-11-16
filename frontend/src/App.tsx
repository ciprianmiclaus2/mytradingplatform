import { BackendStatus } from './components/BackendStatus'
import { useBackendHealth } from './hooks/useBackendHealth'

export default function App() {
  const { state, recheck } = useBackendHealth()

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-white px-4 py-3">
        <h1 className="text-lg font-semibold">My Trading Platform</h1>
        <BackendStatus state={state} onRetry={recheck} />
      </header>
      <main className="p-4">
        <p className="text-sm text-slate-500">Dashboard coming soon.</p>
      </main>
    </div>
  )
}
