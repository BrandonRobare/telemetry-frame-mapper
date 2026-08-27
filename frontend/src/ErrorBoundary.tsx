import { Component } from 'react'
import type { ReactNode, ErrorInfo } from 'react'

interface Props {
  children: ReactNode
  /**
   * Render the fallback scoped to the space this boundary occupies instead of
   * the full-viewport panel. Used by the per-tab boundaries (#649) so a bad
   * tab degrades in place and the shell — nav, pickers, HUD — stays usable.
   * Omitted, the behaviour is the app-level last-resort panel, unchanged.
   */
  inline?: boolean
}
interface State { error: Error | null }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  private reset = () => {
    this.setState({ error: null })
  }

  private reload = () => {
    window.location.reload()
  }

  render() {
    if (this.state.error) {
      const { inline } = this.props
      return (
        <div style={{
          padding: 24,
          fontFamily: 'var(--font-mono)',
          color: 'var(--danger)',
          background: 'var(--bg)',
          ...(inline ? { flex: 1, overflow: 'auto' } : { minHeight: '100vh' }),
        }}>
          <strong>
            {inline
              ? 'This tab failed to render. The rest of the app still works'
              : 'Render error. Check console for details'}
          </strong>
          <pre style={{ marginTop: 12, whiteSpace: 'pre-wrap', fontSize: 13 }}>
            {this.state.error.message}
          </pre>
          <div style={{ display: 'flex', gap: 12, marginTop: 16 }}>
            <button type="button" onClick={this.reset}>
              Try again
            </button>
            <button type="button" onClick={this.reload}>
              Reload app
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
