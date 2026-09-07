import { useEffect, useState } from 'react';
import { api } from '@/services/api';
import type { Event } from '@/types';

interface Props {
  event: Event;
  onSaved?: (event: Event) => void;
}

function blankIfPlaceholder(v?: string | null): string {
  if (!v) return '';
  const u = v.toUpperCase();
  if (u === 'UNKNOWN' || u === 'NOT VERIFIED' || u === 'NOT AVAILABLE') return '';
  return v;
}

export function PlantLabelsEditor({ event, onSaved }: Props) {
  const extra = (event.extra as Record<string, string> | undefined) ?? {};
  const labels =
    (event.extra as { plant_labels?: Record<string, string> } | undefined)?.plant_labels ?? {};

  const [substation, setSubstation] = useState(
    blankIfPlaceholder(event.substation_name ?? labels.substation_name ?? extra.substation_name),
  );
  const [bay, setBay] = useState(
    blankIfPlaceholder(event.bay_name ?? labels.bay_name ?? extra.bay_name),
  );
  const [relay, setRelay] = useState(
    blankIfPlaceholder(event.relay_tag ?? labels.relay_tag ?? extra.relay_tag),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);

  useEffect(() => {
    setSubstation(
      blankIfPlaceholder(event.substation_name ?? labels.substation_name ?? extra.substation_name),
    );
    setBay(blankIfPlaceholder(event.bay_name ?? labels.bay_name ?? extra.bay_name));
    setRelay(blankIfPlaceholder(event.relay_tag ?? labels.relay_tag ?? extra.relay_tag));
    setOk(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    event.id,
    event.substation_name,
    event.bay_name,
    event.relay_tag,
    labels.substation_name,
    labels.bay_name,
    labels.relay_tag,
    extra.substation_name,
    extra.bay_name,
    extra.relay_tag,
  ]);

  const save = async () => {
    setBusy(true);
    setError(null);
    setOk(false);
    try {
      const updated = await api.updateEvent(event.id, {
        substation_name: substation.trim() || 'UNKNOWN',
        bay_name: bay.trim() || 'NOT VERIFIED',
        relay_tag: relay.trim() || 'NOT VERIFIED',
      });
      setOk(true);
      onSaved?.(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save plant labels');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel" style={{ marginBottom: 14 }}>
      <div className="panel-header">Plant labels</div>
      <div className="panel-body">
        <p className="subtitle" style={{ marginBottom: 12 }}>
          Substation / bay / relay shown in the event header. Fill these to replace UNKNOWN / NOT
          VERIFIED.
        </p>
        <div className="form-grid-3" style={{ marginBottom: 12 }}>
          <label>
            <span className="form-label">Substation</span>
            <input
              className="form-control"
              value={substation}
              onChange={(e) => setSubstation(e.target.value)}
              placeholder="e.g. North Grid SS"
              disabled={busy}
            />
          </label>
          <label>
            <span className="form-label">Bay</span>
            <input
              className="form-control"
              value={bay}
              onChange={(e) => setBay(e.target.value)}
              placeholder="e.g. Bay-12"
              disabled={busy}
            />
          </label>
          <label>
            <span className="form-label">Relay tag</span>
            <input
              className="form-control"
              value={relay}
              onChange={(e) => setRelay(e.target.value)}
              placeholder="e.g. REL-L12-P1"
              disabled={busy}
            />
          </label>
        </div>
        {error && (
          <div className="alert alert-error" style={{ marginBottom: 8 }} role="alert">
            {error}
          </div>
        )}
        {ok && (
          <div className="alert alert-ok" style={{ marginBottom: 8 }} role="status">
            Plant labels saved
          </div>
        )}
        <button type="button" className="btn btn-sm btn-primary" disabled={busy} onClick={() => void save()}>
          {busy ? 'Saving…' : 'Save plant labels'}
        </button>
      </div>
    </div>
  );
}
