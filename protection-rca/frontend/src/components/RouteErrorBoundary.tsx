import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

type Props = { children: ReactNode };
type State = { error: Error | null; reloading: boolean };

const RELOAD_KEY = 'pes_chunk_reload';

function isChunkLoadError(error: Error): boolean {
  const msg = (error?.message || '').toLowerCase();
  return (
    msg.includes('dynamically imported module') ||
    msg.includes('failed to fetch') ||
    msg.includes('loading chunk') ||
    msg.includes('importing a module script failed')
  );
}

/** Keeps a failed lazy route from blanking the whole SPA. */
export class RouteErrorBoundary extends Component<Props, State> {
  state: State = { error: null, reloading: false };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('Route render failed', error, info.componentStack);
    // After a rebuild, old tabs request missing hashed chunks — one hard reload fixes it.
    if (isChunkLoadError(error) && typeof sessionStorage !== 'undefined') {
      const already = sessionStorage.getItem(RELOAD_KEY);
      if (!already) {
        sessionStorage.setItem(RELOAD_KEY, '1');
        this.setState({ reloading: true });
        window.location.reload();
      }
    }
  }

  componentDidMount(): void {
    // Clear one-shot reload guard after a successful mount.
    try {
      sessionStorage.removeItem(RELOAD_KEY);
    } catch {
      /* ignore */
    }
  }

  render() {
    if (this.state.reloading) {
      return (
        <div className="page">
          <p className="subtitle">Updating UI after a rebuild…</p>
        </div>
      );
    }
    if (!this.state.error) return this.props.children;

    const chunkMiss = isChunkLoadError(this.state.error);
    return (
      <div className="page">
        <div className="page-header">
          <div>
            <h1>Page failed to load</h1>
            <p className="subtitle">
              {chunkMiss
                ? 'The UI was rebuilt — your browser still had an old page open.'
                : 'The UI hit an error instead of going blank.'}
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => {
                try {
                  sessionStorage.removeItem(RELOAD_KEY);
                } catch {
                  /* ignore */
                }
                window.location.href = '/';
              }}
            >
              Reload app
            </button>
            <Link
              className="btn"
              to="/plant"
              onClick={() => this.setState({ error: null })}
            >
              Back to Plant
            </Link>
          </div>
        </div>
        <div className="alert alert-error" role="alert">
          {this.state.error.message || 'Unknown error'}
        </div>
        <p style={{ color: 'var(--text-muted)' }}>
          {chunkMiss ? (
            <>
              Click <strong>Reload app</strong>, or close the tab and open{' '}
              <span className="mono">http://127.0.0.1:8001/</span> again after restarting
              ProtectionRCA.exe.
            </>
          ) : (
            <>
              Try refreshing the browser. If this keeps happening, check that the API is still
              running in the Protection RCA control window.
            </>
          )}
        </p>
      </div>
    );
  }
}
