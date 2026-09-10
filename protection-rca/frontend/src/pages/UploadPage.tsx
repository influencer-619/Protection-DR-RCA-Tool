import { useState, type DragEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '@/services/api';
import { UPLOAD_ACCEPT, UPLOAD_ACCEPT_HINT } from '@/utils/uploadAccept';

export function UploadPage() {
  const [dragging, setDragging] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [createdId, setCreatedId] = useState<string | null>(null);
  const navigate = useNavigate();

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    setFiles(Array.from(e.dataTransfer.files));
  };

  const submit = async () => {
    setBusy(true);
    try {
      const ev = await api.createEvent({
        event_id: `EVT-${Date.now()}`,
        description: `Upload batch: ${files.map((f) => f.name).join(', ')}`,
        event_datetime: new Date().toISOString(),
      });
      if (files.length) {
        await api.uploadEventFiles(ev.id, files);
      }
      setCreatedId(ev.id);
      navigate(`/events/${ev.id}/files`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Upload disturbance records</h1>
          <p className="subtitle">
            COMTRADE CFG/DAT/CFF, settings, SOE/SCADA, PDF, ZIP (auto-extract)
          </p>
        </div>
        <Link to="/events/new" className="btn">
          Prefer guided create
        </Link>
      </div>

      <div className="alert alert-warn" style={{ marginBottom: 16 }}>
        Quick upload creates an event with a generated ID and blank plant fields (UNKNOWN / NOT
        VERIFIED). For better reports and consistency checks, use{' '}
        <Link to="/events/new">Create event</Link> to enter substation, bay, and relay first.
      </div>

      <div
        className={`dropzone ${dragging ? 'active' : ''}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => document.getElementById('upload-input')?.click()}
      >
        <strong>Drop files to create a new event</strong>
        <div className="hint">Allowed: {UPLOAD_ACCEPT_HINT}</div>
        <input
          id="upload-input"
          type="file"
          multiple
          hidden
          accept={UPLOAD_ACCEPT}
          onChange={(e) => e.target.files && setFiles(Array.from(e.target.files))}
        />
      </div>

      {files.length > 0 && (
        <div className="panel" style={{ marginTop: 16 }}>
          <div className="panel-header">Selected files ({files.length})</div>
          <div className="panel-body">
            <ul className="mono" style={{ margin: 0, paddingLeft: 18, fontSize: '0.85rem' }}>
              {files.map((f) => (
                <li key={f.name}>
                  {f.name} ({(f.size / 1024).toFixed(1)} KB)
                </li>
              ))}
            </ul>
            <button
              type="button"
              className="btn btn-primary"
              style={{ marginTop: 14 }}
              disabled={busy}
              onClick={() => void submit()}
            >
              {busy ? 'Creating event…' : 'Create event & upload'}
            </button>
          </div>
        </div>
      )}

      {createdId && (
        <div className="alert alert-ok" style={{ marginTop: 12 }}>
          Event created — <Link to={`/events/${createdId}/overview`}>{createdId}</Link>
        </div>
      )}
    </div>
  );
}
