import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '@/services/api';
import type { ComtradeFile } from '@/types';
import { StatusBadge } from '@/components/StatusBadge';
import { DataQualityBadge } from '@/components/DataQualityBadge';
import { useEventOrWorkspace } from '@/context/EventWorkspaceContext';

export function EventComtradePage() {
  const { id } = useParams<{ id: string }>();
  const { analysisRevision, reloadJob } = useEventOrWorkspace(id);
  const [ct, setCt] = useState<ComtradeFile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const load = () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    void api
      .getComtrade(id)
      .then(setCt)
      .catch((e: unknown) => {
        setCt(null);
        setError(e instanceof Error ? e.message : 'COMTRADE metadata not available');
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, analysisRevision]);

  const startAnalysis = async () => {
    if (!id) return;
    setStarting(true);
    try {
      await api.startAnalysis(id, true);
      await reloadJob();
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start analysis');
    } finally {
      setStarting(false);
    }
  };

  if (loading) return <div className="empty-state">Loading COMTRADE metadata…</div>;

  if (!ct) {
    const isMissing =
      (error || '').toLowerCase().includes('not available') ||
      (error || '').includes('404') ||
      (error || '').toLowerCase().includes('comtrade');
    return (
      <div className="empty-state" style={{ maxWidth: 560, margin: '40px auto' }}>
        <p style={{ marginBottom: 8, fontWeight: 600 }}>
          {isMissing ? 'No COMTRADE record for this event' : 'COMTRADE page error'}
        </p>
        <p style={{ marginBottom: 12, color: 'var(--text-secondary)' }}>
          {error && !error.startsWith('Request failed')
            ? error
            : 'Upload a CFG+DAT pair (or CFF/ZIP). If the format is unsupported or invalid, analysis may finish without saving COMTRADE metadata — this page then has nothing to show.'}
        </p>
        <div style={{ display: 'flex', gap: 10, justifyContent: 'center', flexWrap: 'wrap' }}>
          <button
            type="button"
            className="btn btn-primary"
            disabled={starting}
            onClick={() => void startAnalysis()}
          >
            {starting ? 'Starting…' : 'Start analysis'}
          </button>
          <Link className="btn btn-ghost" to={`/events/${id}/files`}>
            Check files
          </Link>
        </div>
      </div>
    );
  }

  const displayWarnings = (ct.parse_warnings ?? []).filter(
    (w) => !w.includes('Ambiguous numeric dates are interpreted as dd/mm/yyyy'),
  );

  return (
    <div>
      <div className="badge-row" style={{ marginBottom: 16 }}>
        {ct.validation_status && <StatusBadge status={ct.validation_status} />}
        {ct.data_quality && <DataQualityBadge quality={ct.data_quality} />}
        {ct.support_status && <StatusBadge status={ct.support_status} />}
      </div>

      <div className="two-col">
        <div className="panel">
          <div className="panel-header">Detection result</div>
          <div className="panel-body">
            <table className="data-table">
              <tbody>
                <tr>
                  <td>Format detected</td>
                  <td className="mono">{ct.format_detected ?? '—'}</td>
                </tr>
                <tr>
                  <td>Revision year</td>
                  <td className="num">{ct.revision_year ?? '—'}</td>
                </tr>
                <tr>
                  <td>Station</td>
                  <td>{ct.station_name ?? '—'}</td>
                </tr>
                <tr>
                  <td>Recording device</td>
                  <td className="mono">{ct.recording_device ?? '—'}</td>
                </tr>
                <tr>
                  <td>Sample rate</td>
                  <td className="num">{ct.sample_rate_hz ?? '—'} Hz</td>
                </tr>
                <tr>
                  <td>Total samples</td>
                  <td className="num">{ct.total_samples ?? '—'}</td>
                </tr>
                <tr>
                  <td>Analog / Digital</td>
                  <td className="num">
                    {ct.analog_channel_count ?? 0} / {ct.digital_channel_count ?? 0}
                  </td>
                </tr>
                <tr>
                  <td>Line frequency</td>
                  <td className="num">{ct.line_frequency_hz ?? ct.frequency_hz ?? '—'} Hz</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">Timestamps</div>
          <div className="panel-body">
            <table className="data-table">
              <tbody>
                <tr>
                  <td>Start</td>
                  <td className="mono">
                    {ct.start_timestamp
                      ? new Date(ct.start_timestamp).toISOString().replace('T', ' ').replace('Z', ' UTC')
                      : '—'}
                  </td>
                </tr>
                <tr>
                  <td>Trigger</td>
                  <td className="mono">
                    {ct.trigger_timestamp
                      ? new Date(ct.trigger_timestamp).toISOString().replace('T', ' ').replace('Z', ' UTC')
                      : '—'}
                  </td>
                </tr>
              </tbody>
            </table>
            {displayWarnings.length > 0 && (
              <div style={{ marginTop: 14 }}>
                <div className="alert alert-warn">
                  <strong>Validation warnings</strong>
                  <ul style={{ margin: '8px 0 0', paddingLeft: 18 }}>
                    {displayWarnings.map((w) => (
                      <li key={w}>{w}</li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
