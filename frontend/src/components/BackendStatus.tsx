import type { BackendHealthState } from '../hooks/useBackendHealth'

interface Props {
  state: BackendHealthState
  onRetry: () => void
}

export function BackendStatus({ state, onRetry }: Props) {
  if (state.status === 'checking') {
    return (
      <span role="status" className="text-sm text-slate-500">
        Connecting to backend…
      </span>
    )
  }

  if (state.status === 'error') {
    return (
      <span role="alert" className="flex items-center gap-2 text-sm text-red-600">
        <span className="h-2 w-2 rounded-full bg-red-600" aria-hidden />
        {state.message}
        <button
          type="button"
          onClick={onRetry}
          className="rounded border border-red-300 px-2 py-0.5 text-xs hover:bg-red-50"
        >
          Retry
        </button>
      </span>
    )
  }

  const { health } = state
  return (
    <span role="status" className="flex items-center gap-2 text-sm text-slate-600">
      <span className="h-2 w-2 rounded-full bg-emerald-500" aria-hidden />
      Backend connected · v{health.version} · {health.environment}
    </span>
  )
}
