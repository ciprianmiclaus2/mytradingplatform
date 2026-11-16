import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

/** Keeps a failure inside one pane from taking down the whole dashboard. */
export class PaneErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('Pane failed to render', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div role="alert" className="p-4 text-sm text-red-700">
          <p>This pane hit an unexpected error: {this.state.error.message}</p>
          <button
            type="button"
            onClick={() => this.setState({ error: null })}
            className="mt-2 rounded border border-red-300 px-2 py-0.5 text-xs hover:bg-red-50"
          >
            Try again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
