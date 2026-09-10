import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '@/services/api';
import type { WaveformChannelData, WaveformMarker } from '@/types';
import { WaveformViewer } from '@/components/WaveformViewer';
import { EmptyState } from '@/components/EmptyState';
import { ThemeToggle } from '@/components/ThemeToggle';
import { QuantitySideToggle } from '@/components/QuantitySideToggle';
import { useQuantitySide } from '@/hooks/useQuantitySide';
import {
  detectAvailableSides,
  filterWaveformChannelsBySide,
  sideLabel,
} from '@/utils/quantitySide';

interface Props {
  /** Full-window analysis mode (no app chrome). */
  popout?: boolean;
}

export function WaveformPage({ popout = false }: Props) {
  const { id } = useParams<{ id: string }>();
  const { mode: quantitySide, setMode: setQuantitySide } = useQuantitySide(id);
  const [channels, setChannels] = useState<WaveformChannelData[]>([]);
  const [markers, setMarkers] = useState<WaveformMarker[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [ends, setEnds] = useState<Array<{ comtrade_file_id: string; end_label?: string; station_name?: string }>>([]);
  const [selectedEnd, setSelectedEnd] = useState<string>('');

  const sides = useMemo(
    () =>
      detectAvailableSides(
        channels.map((c) => ({
          name: c.channel.name,
          units: c.channel.units,
          ps: c.channel.ps,
          channel_type: c.channel.channel_type,
        })),
      ),
    [channels],
  );
  const dualSide = sides.hasPrimary && sides.hasSecondary;
  const viewChannels = useMemo(
    () => filterWaveformChannelsBySide(channels, dualSide ? quantitySide : 'both'),
    [channels, quantitySide, dualSide],
  );

  const load = (fileId?: string) => {
    if (!id) return;
    setLoading(true);
    setError(null);
    void api
      .getWaveforms(id, fileId ? { comtradeFileId: fileId } : undefined)
      .then((r) => {
        setChannels(r.channels);
        setMarkers(r.markers);
        setNote(r.note ?? null);
      })
      .catch((e: unknown) => {
        setChannels([]);
        setMarkers([]);
        setError(e instanceof Error ? e.message : 'Waveforms not available');
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (!id) return;
    void api
      .getComtradeEnds(id)
      .then((r) => {
        const list = (r.ends || []) as Array<{
          comtrade_file_id: string;
          end_label?: string;
          station_name?: string;
        }>;
        setEnds(list);
        const first = list[0]?.comtrade_file_id ? String(list[0].comtrade_file_id) : '';
        setSelectedEnd(first);
        load(first || undefined);
      })
      .catch(() => {
        setEnds([]);
        load();
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    if (!popout) return;
    const prev = document.title;
    document.title = 'Waveform viewer · Protection RCA';
    return () => {
      document.title = prev;
    };
  }, [popout]);

  const startAnalysis = async () => {
    if (!id) return;
    setStarting(true);
    setError(null);
    try {
      await api.startAnalysis(id, true);
      for (let i = 0; i < 40; i++) {
        await new Promise((r) => setTimeout(r, 500));
        const r = await api.getWaveforms(id);
        if (r.channels.length) {
          setChannels(r.channels);
          setMarkers(r.markers);
          setNote(r.note ?? null);
          return;
        }
      }
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start analysis');
    } finally {
      setStarting(false);
    }
  };

  const openInNewWindow = () => {
    if (!id) return;
    const target = `${window.location.origin}/events/${id}/waveforms/popout`;
    const w = Math.max(1024, window.screen.availWidth);
    const h = Math.max(700, window.screen.availHeight);
    window.open(
      target,
      `waveform-${id}`,
      `noopener,noreferrer,width=${w},height=${h},left=0,top=0`,
    );
  };

  if (loading) {
    return (
      <div style={popout ? { padding: 20, minHeight: '100vh' } : undefined}>
        <div className="empty-state">Loading waveform data…</div>
      </div>
    );
  }

  if (!channels.length) {
    return (
      <div style={popout ? { padding: 20, minHeight: '100vh' } : undefined}>
        <EmptyState
          title="No waveform samples yet"
          description={
            error ||
            note ||
            'Upload COMTRADE CFG+DAT (or ZIP), then run analysis. Waveforms are the starting point for fault review.'
          }
          tips={[
            'CFG and DAT must pair (same stem)',
            'Markers (fault / trip / breaker) appear after analysis',
            'Scroll to zoom · Shift+drag to pan',
          ]}
          actions={[
            {
              label: starting ? 'Analysing…' : 'Start / Re-run analysis',
              primary: true,
              disabled: starting,
              onClick: () => void startAnalysis(),
            },
            { label: 'Check files', to: id ? `/events/${id}/files` : '/events' },
            { label: 'COMTRADE meta', to: id ? `/events/${id}/comtrade` : '/events' },
          ]}
        />
      </div>
    );
  }

  if (popout) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          height: '100vh',
          width: '100vw',
          maxWidth: 'none',
          boxSizing: 'border-box',
          background: 'var(--bg-app)',
          overflow: 'hidden',
        }}
      >
        <div
          className="page-header"
          style={{
            padding: '10px 14px',
            marginBottom: 0,
            flexShrink: 0,
            borderBottom: '1px solid var(--border)',
          }}
        >
          <div>
            <h1 style={{ fontSize: '1.1rem' }}>Waveform viewer</h1>
            <p className="subtitle">
              {channels.length} channels
              {markers.length ? ` · ${markers.length} markers` : ''} · Zoom, pan, time cursor ·
              Pop-out
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <QuantitySideToggle
              mode={quantitySide}
              onChange={setQuantitySide}
              show={dualSide}
              compact
            />
            <ThemeToggle />
            <button type="button" className="btn btn-sm" onClick={() => window.close()}>
              Close window
            </button>
            <button
              type="button"
              className="btn btn-sm"
              disabled={starting}
              onClick={() => void startAnalysis()}
            >
              {starting ? 'Refreshing…' : 'Re-run analysis'}
            </button>
          </div>
        </div>
        {note && (
          <div className="alert alert-info" style={{ margin: '8px 14px 0', flexShrink: 0 }}>
            {note}
          </div>
        )}
        <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
          <WaveformViewer channels={viewChannels} markers={markers} fill />
        </div>
        {markers.length > 0 && (
          <div
            className="panel"
            style={{
              margin: 0,
              borderRadius: 0,
              borderLeft: 'none',
              borderRight: 'none',
              borderBottom: 'none',
              flexShrink: 0,
              maxHeight: 120,
              overflow: 'auto',
            }}
          >
            <div className="panel-header">Event markers</div>
            <div className="panel-body" style={{ fontSize: '0.85rem', paddingTop: 8, paddingBottom: 8 }}>
              {markers.map((m, i) => (
                <div key={`${m.label}-${i}`} style={{ display: 'flex', gap: 12, marginBottom: 2 }}>
                  <span className="mono" style={{ color: m.color || 'var(--wf-marker)', minWidth: 90 }}>
                    {m.t_us != null ? `${(m.t_us / 1000).toFixed(2)} ms` : '—'}
                  </span>
                  <span>{m.label}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div>
      <div className="page-header" style={{ padding: 0, marginBottom: 12 }}>
        <div>
          <h1 style={{ fontSize: '1.1rem' }}>Waveform viewer</h1>
          <p className="subtitle">
            {channels.length} channels
            {markers.length ? ` · ${markers.length} markers` : ''} · Zoom, pan, time cursor
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          {ends.length > 1 && (
            <label style={{ fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: 6 }}>
              End
              <select
                className="input"
                value={selectedEnd}
                onChange={(e) => {
                  setSelectedEnd(e.target.value);
                  load(e.target.value);
                }}
              >
                {ends.map((en) => (
                  <option key={en.comtrade_file_id} value={en.comtrade_file_id}>
                    {en.end_label || 'END'}
                    {en.station_name ? ` · ${en.station_name}` : ''}
                  </option>
                ))}
              </select>
            </label>
          )}
          <QuantitySideToggle
            mode={quantitySide}
            onChange={setQuantitySide}
            show={dualSide}
            compact
          />
          <button
            type="button"
            className="btn btn-sm"
            onClick={openInNewWindow}
            title="Open in a separate window"
          >
            Open in new window
          </button>
          <button type="button" className="btn btn-sm" disabled={starting} onClick={() => void startAnalysis()}>
            {starting ? 'Refreshing…' : 'Re-run analysis'}
          </button>
        </div>
      </div>
      {dualSide && (
        <div className="alert alert-info">
          Viewing <strong>{sideLabel(quantitySide)}</strong> — switch to Primary for kA/kV (`*_PRI`)
          channels, or Both to compare.
        </div>
      )}
      {note && <div className="alert alert-info">{note}</div>}
      <WaveformViewer channels={viewChannels} markers={markers} height={460} />
      {markers.length > 0 && (
        <div className="panel" style={{ marginTop: 12 }}>
          <div className="panel-header">Event markers</div>
          <div className="panel-body" style={{ fontSize: '0.85rem' }}>
            {markers.map((m, i) => (
              <div key={`${m.label}-${i}`} style={{ display: 'flex', gap: 12, marginBottom: 4 }}>
                <span className="mono" style={{ color: m.color || 'var(--wf-marker)', minWidth: 90 }}>
                  {m.t_us != null ? `${(m.t_us / 1000).toFixed(2)} ms` : '—'}
                </span>
                <span>{m.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
