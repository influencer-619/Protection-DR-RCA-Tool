import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

type Props = { children: ReactNode };
type State = { error: Error | null };

/** Keeps a failed lazy route from blanking the whole SPA. */
export class RouteErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('Route render failed', error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="page">
        <div className="page-header">
          <div>
            <h1>Page failed to load</h1>
            <p className="subtitle">The UI hit an error instead of going blank.</p>
          </div>
          <Link className="btn btn-primary" to="/plant" onClick={() => this.setState({ error: null })}>
            Back to Plant
          </Link>
        </div>
        <div className="alert alert-error" role="alert">
          {this.state.error.message || 'Unknown error'}
        </div>
        <p style={{ color: 'var(--text-muted)' }}>
          Try refreshing the browser. If this keeps happening after a portable rebuild, check that
          the API is still running in the Protection RCA control window.
        </p>
      </div>
    );
  }
}
