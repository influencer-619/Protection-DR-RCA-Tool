import { useState } from 'react';
import { apiClient, getStoredToken } from '@/services/api';

interface Props {
  eventId: string;
  eventCode?: string;
  className?: string;
  size?: 'sm' | 'md';
}

/**
 * One-click ops handoff: generate RCA PDF (if needed) + download + open printable summary.
 */
export function SharePackButton({ eventId, eventCode, className, size = 'sm' }: Props) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setErr(null);
    try {
      const { data: created } = await apiClient.post<{ id: string }>('/reports', {
        event_id: eventId,
        report_type: 'RCA',
        format: 'PDF',
      });
      const token = getStoredToken();
      const res = await fetch(`/api/reports/${created.id}/download`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`Download failed (${res.status})`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${eventCode || eventId}_share_pack.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      // Open summary for print companion
      window.open(`/events/${eventId}/summary`, '_blank', 'noopener');
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Share pack failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <span className={className} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      <button
        type="button"
        className={`btn ${size === 'sm' ? 'btn-sm' : ''} btn-primary`}
        disabled={busy}
        onClick={() => void run()}
        title="Download RCA PDF and open printable summary"
      >
        {busy ? 'Preparing…' : 'Share pack'}
      </button>
      {err && (
        <span style={{ fontSize: '0.75rem', color: 'var(--status-error)' }} title={err}>
          Failed
        </span>
      )}
    </span>
  );
}
