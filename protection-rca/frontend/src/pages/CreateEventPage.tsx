import { useMemo, useState, type DragEvent, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '@/services/api';
import { UPLOAD_ACCEPT, UPLOAD_ACCEPT_HINT } from '@/utils/uploadAccept';
import styles from './CreateEventPage.module.css';

const STEPS = [
  'Event information',
  'File upload',
  'Detection',
  'Validation',
  'Analysis',
] as const;

type PlantForm = {
  event_id: string;
  substation_name: string;
  bay_name: string;
  feeder: string;
  asset_name: string;
  relay_tag: string;
  breaker_tag: string;
  event_datetime: string;
  nominal_voltage_kv: string;
  nominal_frequency_hz: string;
  description: string;
};

const emptyForm = (): PlantForm => ({
  event_id: '',
  substation_name: '',
  bay_name: '',
  feeder: '',
  asset_name: '',
  relay_tag: '',
  breaker_tag: '',
  event_datetime: new Date().toISOString().slice(0, 16),
  nominal_voltage_kv: '',
  nominal_frequency_hz: '50',
  description: '',
});

export function CreateEventPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<PlantForm>(emptyForm);
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [eventPk, setEventPk] = useState<string | null>(null);
  const [eventBizId, setEventBizId] = useState<string | null>(null);
  const [detection, setDetection] = useState<Record<string, unknown> | null>(null);
  const [validation, setValidation] = useState<Record<string, unknown> | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);

  const setField = (key: keyof PlantForm, value: string) =>
    setForm((f) => ({ ...f, [key]: value }));

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    setFiles((prev) => [...prev, ...Array.from(e.dataTransfer.files)]);
  };

  const createEvent = async () => {
    setBusy(true);
    setError(null);
    try {
      const payload: Record<string, unknown> = {
        event_id: form.event_id.trim() || undefined,
        feeder: form.feeder.trim() || undefined,
        description: form.description.trim() || undefined,
        nominal_voltage_kv: form.nominal_voltage_kv
          ? Number(form.nominal_voltage_kv)
          : undefined,
        nominal_frequency_hz: form.nominal_frequency_hz
          ? Number(form.nominal_frequency_hz)
          : 50,
        event_datetime: form.event_datetime
          ? new Date(form.event_datetime).toISOString()
          : new Date().toISOString(),
        substation_name: form.substation_name.trim() || 'UNKNOWN',
        bay_name: form.bay_name.trim() || 'NOT VERIFIED',
        relay_tag: form.relay_tag.trim() || 'NOT VERIFIED',
        breaker_tag: form.breaker_tag.trim() || undefined,
        asset_name: form.asset_name.trim() || undefined,
      };
      const ev = await api.createEvent(payload);
      setEventPk(ev.id);
      setEventBizId(ev.event_id);
      setStep(1);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create event');
    } finally {
      setBusy(false);
    }
  };

  const uploadFiles = async () => {
    if (!eventPk) return;
    if (!files.length) {
      setError('Add at least one disturbance file (.cfg/.dat/.cff preferred)');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.uploadEventFiles(eventPk, files);
      setStep(2);
      const det = await api.detectComtrade(files);
      setDetection(det);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload / detection failed');
    } finally {
      setBusy(false);
    }
  };

  const runValidation = async () => {
    if (!files.length) return;
    setBusy(true);
    setError(null);
    try {
      const val = await api.validateComtrade(files);
      setValidation(val);
      setStep(3);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Validation failed');
    } finally {
      setBusy(false);
    }
  };

  const startAnalysis = async () => {
    if (!eventPk) return;
    setBusy(true);
    setError(null);
    try {
      const job = await api.startAnalysis(eventPk);
      setJobId(job.id);
      setStep(4);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start analysis');
    } finally {
      setBusy(false);
    }
  };

  const onInfoSubmit = (e: FormEvent) => {
    e.preventDefault();
    void createEvent();
  };

  const detectStatus = String(detection?.status ?? '—');
  const validateStatus = String(validation?.status ?? '—');

  const workflowHint = useMemo(
    () => [
      'Create Event',
      'Upload Records',
      'Validate COMTRADE',
      'Run Analysis',
      'Review Consistency',
      'Review RCA',
      'Generate Report',
    ],
    [],
  );

  return (
    <div className={`page ${styles.wrap}`}>
      <div className="page-header">
        <div>
          <h1>Create event</h1>
          <p className="subtitle">
            Guided disturbance package workflow · unknown values allowed
          </p>
        </div>
        <Link to="/events" className="btn">
          Cancel
        </Link>
      </div>

      <ol className={styles.steps}>
        {STEPS.map((label, i) => (
          <li
            key={label}
            className={`${styles.step} ${i === step ? styles.active : ''} ${
              i < step ? styles.done : ''
            }`}
          >
            <span className={styles.num}>{i + 1}</span>
            {label}
          </li>
        ))}
      </ol>

      {error && (
        <div className="alert alert-error" role="alert">
          {error}
        </div>
      )}

      {step === 0 && (
        <form className="panel" onSubmit={onInfoSubmit}>
          <div className="panel-header">Step 1 — Event information</div>
          <div className={`panel-body ${styles.formGrid}`}>
            <label>
              Event ID
              <input
                className="form-control"
                value={form.event_id}
                onChange={(e) => setField('event_id', e.target.value)}
                placeholder="Auto-generated if blank"
              />
            </label>
            <label>
              Substation
              <input
                className="form-control"
                value={form.substation_name}
                onChange={(e) => setField('substation_name', e.target.value)}
                placeholder="UNKNOWN"
              />
            </label>
            <label>
              Bay
              <input
                className="form-control"
                value={form.bay_name}
                onChange={(e) => setField('bay_name', e.target.value)}
                placeholder="NOT VERIFIED"
              />
            </label>
            <label>
              Feeder
              <input
                className="form-control"
                value={form.feeder}
                onChange={(e) => setField('feeder', e.target.value)}
              />
            </label>
            <label>
              Asset
              <input
                className="form-control"
                value={form.asset_name}
                onChange={(e) => setField('asset_name', e.target.value)}
                placeholder="OPTIONAL"
              />
            </label>
            <label>
              Relay
              <input
                className="form-control"
                value={form.relay_tag}
                onChange={(e) => setField('relay_tag', e.target.value)}
                placeholder="NOT VERIFIED"
              />
            </label>
            <label>
              Breaker
              <input
                className="form-control"
                value={form.breaker_tag}
                onChange={(e) => setField('breaker_tag', e.target.value)}
                placeholder="OPTIONAL"
              />
            </label>
            <label>
              Event date/time
              <input
                className="form-control"
                type="datetime-local"
                value={form.event_datetime}
                onChange={(e) => setField('event_datetime', e.target.value)}
              />
            </label>
            <label>
              Nominal voltage (kV)
              <input
                className="form-control"
                value={form.nominal_voltage_kv}
                onChange={(e) => setField('nominal_voltage_kv', e.target.value)}
                placeholder="UNKNOWN"
              />
            </label>
            <label>
              Nominal frequency (Hz)
              <input
                className="form-control"
                value={form.nominal_frequency_hz}
                onChange={(e) => setField('nominal_frequency_hz', e.target.value)}
              />
            </label>
            <label className={styles.full}>
              Description
              <textarea
                className="form-control"
                rows={3}
                value={form.description}
                onChange={(e) => setField('description', e.target.value)}
              />
            </label>
          </div>
          <div className={styles.footer}>
            <p className={styles.hint}>
              Never invent plant data. Leave blank → stored as UNKNOWN / NOT VERIFIED.
            </p>
            <button type="submit" className="btn btn-primary" disabled={busy}>
              {busy ? 'Creating…' : 'Continue to upload'}
            </button>
          </div>
        </form>
      )}

      {step === 1 && (
        <div className="panel">
          <div className="panel-header">
            Step 2 — File upload · {eventBizId}
          </div>
          <div className="panel-body">
            <div
              className={`dropzone ${dragging ? 'active' : ''}`}
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              onClick={() => document.getElementById('create-upload')?.click()}
            >
              <strong>Drag & drop disturbance package</strong>
              <div className="hint">{UPLOAD_ACCEPT_HINT}</div>
              <input
                id="create-upload"
                type="file"
                multiple
                hidden
                accept={UPLOAD_ACCEPT}
                onChange={(e) =>
                  e.target.files && setFiles((p) => [...p, ...Array.from(e.target.files!)])
                }
              />
            </div>
            {files.length > 0 && (
              <ul className={`mono ${styles.fileList}`}>
                {files.map((f) => (
                  <li key={`${f.name}-${f.size}`}>
                    {f.name} · {(f.size / 1024).toFixed(1)} KB
                  </li>
                ))}
              </ul>
            )}
            <div className={styles.footer}>
              <button type="button" className="btn" onClick={() => setStep(0)}>
                Back
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy}
                onClick={() => void uploadFiles()}
              >
                {busy ? 'Uploading…' : 'Upload & detect'}
              </button>
            </div>
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="panel">
          <div className="panel-header">Step 3 — Detection</div>
          <div className="panel-body">
            <table className="data-table">
              <tbody>
                <tr>
                  <td>Status</td>
                  <td className="mono">{detectStatus}</td>
                </tr>
                <tr>
                  <td>Is COMTRADE</td>
                  <td>{String(detection?.is_comtrade ?? '—')}</td>
                </tr>
                <tr>
                  <td>Revision</td>
                  <td className="mono">{String(detection?.revision_year ?? '—')}</td>
                </tr>
                <tr>
                  <td>Container</td>
                  <td className="mono">{String(detection?.container ?? '—')}</td>
                </tr>
                <tr>
                  <td>Data format</td>
                  <td className="mono">{String(detection?.data_format ?? '—')}</td>
                </tr>
                <tr>
                  <td>Encoding</td>
                  <td className="mono">{String(detection?.encoding ?? '—')}</td>
                </tr>
              </tbody>
            </table>
            <div className={styles.footer}>
              <button type="button" className="btn" onClick={() => setStep(1)}>
                Back
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy}
                onClick={() => void runValidation()}
              >
                {busy ? 'Validating…' : 'Validate COMTRADE'}
              </button>
            </div>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="panel">
          <div className="panel-header">Step 4 — Validation</div>
          <div className="panel-body">
            <table className="data-table">
              <tbody>
                <tr>
                  <td>Validation status</td>
                  <td className="mono">{validateStatus}</td>
                </tr>
                <tr>
                  <td>Data quality</td>
                  <td className="mono">{String(validation?.data_quality ?? '—')}</td>
                </tr>
              </tbody>
            </table>
            {Array.isArray(validation?.warnings) && validation.warnings.length > 0 && (
              <div className="alert alert-warn" style={{ marginTop: 12 }}>
                {(validation.warnings as string[]).join('; ')}
              </div>
            )}
            <div className={styles.footer}>
              <button type="button" className="btn" onClick={() => setStep(2)}>
                Back
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy}
                onClick={() => void startAnalysis()}
              >
                {busy ? 'Starting…' : 'Start analysis'}
              </button>
            </div>
          </div>
        </div>
      )}

      {step === 4 && (
        <div className="panel">
          <div className="panel-header">Step 5 — Analysis</div>
          <div className="panel-body">
            <p>
              Analysis job queued for <span className="mono">{eventBizId}</span>
              {jobId && (
                <>
                  {' '}
                  · job <span className="mono">{jobId}</span>
                </>
              )}
              .
            </p>
            <p className={styles.hint}>
              Pipeline: parse → signal → timeline → protection → consistency → fault → RCA →
              evidence → report. No generative AI.
            </p>
            <ol className={styles.workflow}>
              {workflowHint.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ol>
            <div className={styles.footer}>
              {eventPk && (
                <>
                  <Link className="btn" to={`/events/${eventPk}/files`}>
                    Open files
                  </Link>
                  <Link className="btn btn-primary" to={`/events/${eventPk}/overview`}>
                    Open event workspace
                  </Link>
                  <button
                    type="button"
                    className="btn"
                    onClick={() => navigate(`/events/${eventPk}/consistency`)}
                  >
                    Consistency
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
