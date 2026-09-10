import { useCallback, useEffect, useState, type DragEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { format } from 'date-fns';
import { api } from '@/services/api';
import type { EventFile, SettingSourceInfo } from '@/types';
import { StatusBadge } from '@/components/StatusBadge';
import { VerifyActiveSettingsCard } from '@/components/VerifyActiveSettingsCard';
import { useEventOrWorkspace } from '@/context/EventWorkspaceContext';
import { UPLOAD_ACCEPT, UPLOAD_ACCEPT_HINT } from '@/utils/uploadAccept';

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

function looksLikeSettings(name: string): boolean {
  const n = name.toLowerCase();
  return (
    n.includes('setting') ||
    n.includes('relay') ||
    n.endsWith('.set') ||
    (n.endsWith('.json') && (n.includes('param') || n.includes('relay')))
  );
}

function packageReady(files: EventFile[]): boolean {
  const names = files.map((f) => (f.original_filename || '').toLowerCase());
  const hasCff = names.some((n) => n.endsWith('.cff'));
  const hasCfg = names.some((n) => n.endsWith('.cfg'));
  const hasDat = names.some((n) => n.endsWith('.dat'));
  const hasSettings = files.some(
    (f) =>
      f.source_type === 'SETTINGS' || looksLikeSettings(f.original_filename || ''),
  );
  return (hasCff || (hasCfg && hasDat)) && hasSettings;
}

export function EventFilesPage() {
  const { id } = useParams<{ id: string }>();
  const { event, reload: reloadEvent, reloadJob, analysisRevision, analysisBusy } =
    useEventOrWorkspace(id);
  const [files, setFiles] = useState<EventFile[]>([]);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [settingsHint, setSettingsHint] = useState(false);
  const [analysing, setAnalysing] = useState(false);
  const [settingSource, setSettingSource] = useState<SettingSourceInfo | null>(null);
  const [autoMsg, setAutoMsg] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!id) return;
    void api.getEventFiles(id).then(setFiles);
    void api.getConsistency(id).then((r) => setSettingSource(r.setting_source)).catch(() => {});
  }, [id]);

  useEffect(() => {
    load();
  }, [load, analysisRevision]);

  const upload = async (list: FileList | File[]) => {
    if (!id || !list.length) return;
    setUploading(true);
    setError(null);
    setAutoMsg(null);
    const arr = Array.from(list);
    const hadSettings = arr.some((f) => looksLikeSettings(f.name));
    try {
      const uploaded = await api.uploadEventFiles(id, arr);
      const nextFiles = [...uploaded, ...files];
      setFiles(nextFiles);
      // Refresh full file list from server
      const all = await api.getEventFiles(id);
      setFiles(all);
      if (
        hadSettings ||
        uploaded.some(
          (f) =>
            f.source_type === 'SETTINGS' || looksLikeSettings(f.original_filename || ''),
        )
      ) {
        setSettingsHint(true);
      }
      // Auto-start full analysis when COMTRADE + settings package is complete
      if (packageReady(all)) {
        setAnalysing(true);
        try {
          await api.startAnalysis(id, true);
          await reloadJob();
          await reloadEvent();
          setSettingsHint(false);
          setAutoMsg(
            'Files look complete — full analysis started. Watch the progress bar, then walk each tab.',
          );
        } catch (e) {
          setError(e instanceof Error ? e.message : 'Failed to start analysis');
        } finally {
          setAnalysing(false);
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    void upload(e.dataTransfer.files);
  };

  const reAnalyse = async () => {
    if (!id) return;
    setAnalysing(true);
    setError(null);
    setAutoMsg(null);
    try {
      await api.startAnalysis(id, true);
      setSettingsHint(false);
      await reloadJob();
      setAutoMsg('Analysis started — all tabs will refresh when it completes.');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start analysis');
    } finally {
      setAnalysing(false);
    }
  };

  return (
    <div>
      <div className="page-header" style={{ padding: 0 }}>
        <div>
          <h1 style={{ fontSize: '1.1rem' }}>Event files</h1>
          <p className="subtitle">
            Immutable uploads · SHA-256 integrity · settings JSON applied on analysis
          </p>
        </div>
      </div>

      {error && (
        <div className="alert alert-error" role="alert">
          {error}
        </div>
      )}

      {autoMsg && (
        <div className="alert alert-ok" role="status">
          {autoMsg}
        </div>
      )}

      {settingsHint && (
        <div className="alert alert-warn" role="status">
          Settings file stored. Run analysis — uploaded settings are treated as{' '}
          <strong>APPROVED</strong> automatically.
          <div style={{ marginTop: 10, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button
              type="button"
              className="btn btn-sm btn-primary"
              disabled={analysing || analysisBusy}
              onClick={() => void reAnalyse()}
            >
              {analysing || analysisBusy ? 'Starting…' : 'Re-run analysis'}
            </button>
            <Link className="btn btn-sm" to={`/events/${id}/consistency`}>
              Open Consistency
            </Link>
          </div>
        </div>
      )}

      {id && (
        <VerifyActiveSettingsCard
          eventId={id}
          source={settingSource}
          settingsLoaded={Boolean(
            (event?.extra as Record<string, unknown> | undefined)?.setting_source ||
              (event?.extra as Record<string, unknown> | undefined)?.setting_param_count ||
              (event?.extra as Record<string, unknown> | undefined)?.setting_group ||
              (event?.extra as { settings_file_verification_note?: string } | undefined)
                ?.settings_file_verification_note,
          )}
          fileNote={
            (event?.extra as { settings_file_verification_note?: string } | undefined)
              ?.settings_file_verification_note
          }
          onVerified={() => {
            void reloadEvent();
            load();
          }}
        />
      )}

      {files.length === 0 ? (
        <div
          className={`dropzone ${dragging ? 'active' : ''}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => document.getElementById('file-input')?.click()}
        >
          <strong>
            {uploading
              ? 'Uploading…'
              : 'Drop COMTRADE / settings / SOE / vendor package / PDF / ZIP here'}
          </strong>
          <div className="hint">{UPLOAD_ACCEPT_HINT}</div>
        </div>
      ) : null}

      <input
        id="file-input"
        type="file"
        multiple
        hidden
        accept={UPLOAD_ACCEPT}
        onChange={(e) => {
          if (e.target.files) void upload(e.target.files);
          e.target.value = '';
        }}
      />

      <div className="panel" style={{ marginTop: files.length === 0 ? 16 : 0 }}>
        <div
          className="panel-header"
          style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}
        >
          <span>Uploaded files{files.length ? ` (${files.length})` : ''}</span>
          {files.length > 0 && (
            <button
              type="button"
              className="btn btn-sm"
              disabled={uploading}
              onClick={() => document.getElementById('file-input')?.click()}
            >
              {uploading ? 'Uploading…' : 'Add files'}
            </button>
          )}
        </div>
        <div className="panel-body" style={{ padding: 0 }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Filename</th>
                <th>Source</th>
                <th title="LOCAL or REMOTE end — applies to COMTRADE, settings, SOE, and other uploads">
                  End
                </th>
                <th>Size</th>
                <th>SHA-256</th>
                <th>Uploaded</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {files.length === 0 && (
                <tr>
                  <td colSpan={7} style={{ textAlign: 'center', padding: 20, color: 'var(--text-muted)' }}>
                    No files yet. Use the drop zone above to upload COMTRADE, settings, and SOE/CSV.
                  </td>
                </tr>
              )}
              {files.map((f) => (
                <tr key={f.id}>
                  <td className="mono">{f.original_filename}</td>
                  <td>{f.source_type}</td>
                  <td>
                    <select
                      className="input"
                      title="Which line end this file belongs to (LOCAL / REMOTE)"
                      defaultValue={f.file_metadata?.end_label || 'LOCAL'}
                      onChange={(e) => {
                        if (!id) return;
                        void api.setEndLabel(id, f.id, e.target.value).catch(() => {});
                      }}
                      onClick={(e) => e.stopPropagation()}
                    >
                      <option value="LOCAL">LOCAL</option>
                      <option value="REMOTE">REMOTE</option>
                    </select>
                  </td>
                  <td className="num">{formatBytes(f.file_size)}</td>
                  <td className="mono" title={f.sha256} style={{ fontSize: '0.72rem' }}>
                    {f.sha256.length > 20 ? `${f.sha256.slice(0, 20)}…` : f.sha256}
                  </td>
                  <td className="num">
                    {format(new Date(f.upload_timestamp), 'yyyy-MM-dd HH:mm')}
                  </td>
                  <td>
                    <StatusBadge status={f.status ?? 'STORED'} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
