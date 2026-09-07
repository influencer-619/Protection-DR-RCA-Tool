import { useState } from 'react';
import { api } from '@/services/api';
import type { SettingSourceInfo } from '@/types';
import styles from './VerifyActiveSettingsCard.module.css';

interface Props {
  eventId: string;
  source?: SettingSourceInfo | null;
  /** True when event.extra shows a settings package was bound. */
  settingsLoaded?: boolean;
  fileNote?: string | null;
  onVerified?: () => void;
}

function isPlaceholder(v?: string | null): boolean {
  if (!v) return true;
  const u = v.toUpperCase();
  return u === 'NOT VERIFIED' || u === 'NOT AVAILABLE' || u === 'UNKNOWN';
}

export function VerifyActiveSettingsCard({
  eventId,
  source,
  settingsLoaded,
  fileNote,
  onVerified,
}: Props) {
  const [note, setNote] = useState('');
  const [alsoVerifyGroup, setAlsoVerifyGroup] = useState(true);
  const [busy, setBusy] = useState<'approve' | 'confirm' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [doneApprove, setDoneApprove] = useState(false);
  const [doneConfirm, setDoneConfirm] = useState(false);

  const activeStatus =
    source?.active_group_status ?? source?.verification_state ?? 'NOT VERIFIED';
  const approval = (source?.approval_status ?? 'NOT VERIFIED').toUpperCase();
  const approved = approval === 'APPROVED' || doneApprove;
  const groupVerified = activeStatus === 'VERIFIED' || doneConfirm;
  const hasPackage =
    !!settingsLoaded ||
    !isPlaceholder(source?.source) ||
    !isPlaceholder(source?.group) ||
    !isPlaceholder(source?.version) ||
    !!fileNote;

  const afterSuccess = async () => {
    try {
      await api.startAnalysis(eventId, true);
    } catch (e) {
      // Approval/verify already saved — do not present analysis queue failure as API down.
      setError(
        e instanceof Error
          ? `Settings saved, but analysis did not start: ${e.message}`
          : 'Settings saved, but analysis did not start.',
      );
    }
    onVerified?.();
  };

  const approveFile = async () => {
    if (
      !window.confirm(
        'Approve this uploaded settings package for analysis?\n\nThis marks the file as APPROVED (engineer attestation).' +
          (alsoVerifyGroup
            ? '\n\nActive setting group will also be marked VERIFIED.'
            : ''),
      )
    ) {
      return;
    }
    setBusy('approve');
    setError(null);
    try {
      await api.approveSettingsFile(eventId, {
        note: note.trim() || undefined,
        alsoVerifyActiveGroup: alsoVerifyGroup,
      });
      setDoneApprove(true);
      if (alsoVerifyGroup) setDoneConfirm(true);
      await afterSuccess();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Approval failed');
    } finally {
      setBusy(null);
    }
  };

  const confirmGroup = async () => {
    if (
      !window.confirm(
        'Confirm that the uploaded setting group was the ACTIVE group on the relay at the time of this disturbance?\n\nThis is an engineer attestation. Re-run analysis afterward so Consistency uses VERIFIED.',
      )
    ) {
      return;
    }
    setBusy('confirm');
    setError(null);
    try {
      await api.verifyActiveSettings(eventId, note.trim() || undefined);
      setDoneConfirm(true);
      await afterSuccess();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Verification failed');
    } finally {
      setBusy(null);
    }
  };

  if (!hasPackage && !approved && !groupVerified) {
    return (
      <div className={`alert alert-warn ${styles.card}`} role="status">
        <strong>Settings not loaded</strong>
        <p>
          Upload a relay settings package first, then approve the file and confirm which group was
          active when the fault occurred.
        </p>
      </div>
    );
  }

  if (approved && groupVerified) {
    return (
      <div className={`alert alert-ok ${styles.card}`} role="status">
        <strong>Settings APPROVED · Active group VERIFIED</strong>
        <p>
          Source {source?.source ?? '—'} · Version {source?.version ?? '—'} · Group{' '}
          {source?.group ?? '—'}
        </p>
      </div>
    );
  }

  return (
    <div className={`alert alert-warn ${styles.card}`} role="status">
      <strong>Settings need engineer action</strong>
      <p>
        Approve the uploaded settings file for use in analysis
        {!groupVerified ? ', and confirm the active group on the relay at fault time' : ''}. Or
        upload a file named <span className="mono">APPROVED_RELAY_BASE_SETTINGS</span> to
        auto-approve.
      </p>
      {fileNote && <p className={styles.note}>File note: {fileNote}</p>}
      <div className={styles.statusRow}>
        <span>
          Approval: <strong className="mono">{approved ? 'APPROVED' : approval}</strong>
        </span>
        <span>
          Active group:{' '}
          <strong className="mono">{groupVerified ? 'VERIFIED' : activeStatus}</strong>
        </span>
      </div>
      <label className={styles.label} htmlFor={`verify-note-${eventId}`}>
        Note (optional)
      </label>
      <input
        id={`verify-note-${eventId}`}
        className="form-control"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="e.g. Approved from station export / Confirmed GROUP-1 on HMI"
        disabled={busy != null}
      />
      {!approved && (
        <label className={styles.check}>
          <input
            type="checkbox"
            checked={alsoVerifyGroup}
            onChange={(e) => setAlsoVerifyGroup(e.target.checked)}
            disabled={busy != null || groupVerified}
          />
          Also confirm active group as VERIFIED
        </label>
      )}
      {error && (
        <div className="alert alert-error" style={{ marginTop: 8 }} role="alert">
          {error}
        </div>
      )}
      <div className={styles.actions}>
        {!approved && (
          <button
            type="button"
            className="btn btn-sm btn-primary"
            disabled={busy != null}
            onClick={() => void approveFile()}
          >
            {busy === 'approve' ? 'Approving…' : 'Approve settings file'}
          </button>
        )}
        {!groupVerified && (
          <button
            type="button"
            className="btn btn-sm"
            disabled={busy != null}
            onClick={() => void confirmGroup()}
          >
            {busy === 'confirm' ? 'Confirming…' : 'Confirm active group only'}
          </button>
        )}
      </div>
    </div>
  );
}
