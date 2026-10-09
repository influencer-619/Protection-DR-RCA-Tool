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
import { CombinedPageHeader } from '@/components/CombinedPageHeader';
import { useEventOrWorkspace } from '@/context/EventWorkspaceContext';
import {
  alignRemoteMarkers,
  alignRemoteToLocal,
} from '@/utils/dualEndWaveforms';

interface Props {
  /** Full-window analysis mode (no app chrome). */
  popout?: boolean;
}

export function WaveformPage({ popout = false }: Props) {
  const { id } = useParams<{ id: string }>();
  useEventOrWorkspace(id);
  const { mode: quantitySide, setMode: setQuantitySide } = useQuantitySide(id);
  const [channels, setChannels] = useState<WaveformChannelData[]>([]);
  const [markers, setMarkers] = useState<WaveformMarker[]>([]);
  const [channelsPeer, setChannelsPeer] = useState<WaveformChannelData[]>([]);
  const [markersPeer, setMarkersPeer] = useState<WaveformMarker[]>([]);
  const [syncUs, setSyncUs] = useState<number | null>(null);
  const [dualStacked, setDualStacked] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [ends, setEnds] = useState<Array<{ comtrade_file_id: string; end_label?: string; station_name?: string }>>([]);
  const [selectedEnd, setSelectedEnd] = useState<string>('');
  const [peerEnd, setPeerEnd] = useState<string>('');

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
  const peerViewRaw = useMemo(
    () => filterWaveformChannelsBySide(channelsPeer, dualSide ? quantitySide : 'both'),
    [channelsPeer, quantitySide, dualSide],
  );
  const peerView = useMemo(
    () => alignRemoteToLocal(peerViewRaw, syncUs),
    [peerViewRaw, syncUs],
  );
  const peerMarkersAligned = useMemo(
    () => alignRemoteMarkers(markersPeer, syncUs),
    [markersPeer, syncUs],
  );
  const showDual = dualStacked && peerView.length > 0;
  const leftEndLabel =
    ends.find((e) => e.comtrade_file_id === selectedEnd)?.end_label || 'Primary';
  const rightEndLabel =
    ends.find((e) => e.comtrade_file_id === peerEnd)?.end_label || 'Peer';

  const load = (fileId?: string, peerId?: string) => {
    if (!id) return;
    setLoading(true);
    setError(null);
    void Promise.all([
      api.getWaveforms(id, fileId ? { comtradeFileId: fileId } : undefined),
      peerId && peerId !== fileId
        ? api.getWaveforms(id, { comtradeFileId: peerId })
        : Promise.resolve(null),
    ])
      .then(([r, peer]) => {
        setChannels(r.channels);
        setMarkers(r.markers);
        setNote(r.note ?? null);
        if (peer) {
          setChannelsPeer(peer.channels);
          setMarkersPeer(peer.markers || []);
        } else {
          setChannelsPeer([]);
          setMarkersPeer([]);
        }
      })
      .catch((e: unknown) => {
        setChannels([]);
        setMarkers([]);
        setChannelsPeer([]);
        setMarkersPeer([]);
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
        setSyncUs(
          typeof r.computed_sync_offset_us === 'number' ? r.computed_sync_offset_us : null,
        );
        const lab = (e: { end_label?: string }) => String(e.end_label || '').toUpperCase();
        const primary =
          list.find((e) => lab(e) === 'INITIATOR' || lab(e) === 'LOCAL') || list[0];
        const secondary =
          list.find((e) => lab(e) === 'BACKUP' || lab(e).startsWith('REMOTE')) || list[1];
        const first = primary?.comtrade_file_id ? String(primary.comtrade_file_id) : '';
        const second =
          secondary?.comtrade_file_id && secondary.comtrade_file_id !== first
            ? String(secondary.comtrade_file_id)
            : '';
        setSelectedEnd(first);
        setPeerEnd(second);
        setDualStacked(Boolean(second && list.length > 1));
        load(first || undefined, second || undefined);
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
    document.title = 'Waveform viewer · Protection Expert System';
    // Browser zoom enlarges content past the viewport — allow document scroll
    // (default #root { height:100% } + overflow:hidden would trap the view).
    const root = document.getElementById('root');
    const html = document.documentElement;
    const prevHtmlOverflow = html.style.overflow;
    const prevBodyOverflow = document.body.style.overflow;
    const prevBodyHeight = document.body.style.height;
    const prevRootHeight = root?.style.height ?? '';
    const prevRootMinHeight = root?.style.minHeight ?? '';
    const prevRootOverflow = root?.style.overflow ?? '';
    html.style.overflow = 'auto';
    document.body.style.overflow = 'auto';
    document.body.style.height = 'auto';
    if (root) {
      root.style.height = 'auto';
      root.style.minHeight = '100%';
      root.style.overflow = 'auto';
    }
    return () => {
      document.title = prev;
      html.style.overflow = prevHtmlOverflow;
      document.body.style.overflow = prevBodyOverflow;
      document.body.style.height = prevBodyHeight;
      if (root) {
        root.style.height = prevRootHeight;
        root.style.minHeight = prevRootMinHeight;
        root.style.overflow = prevRootOverflow;
      }
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
          minHeight: '100dvh',
          width: '100%',
          maxWidth: 'none',
          boxSizing: 'border-box',
          background: 'var(--bg-app)',
          overflowX: 'auto',
          overflowY: 'auto',
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
          <div style={{ flex: 1 }}>
            <CombinedPageHeader
              title="Waveform viewer"
              subtitle={`${channels.length} channels${markers.length ? ` · ${markers.length} markers` : ''} · Zoom, pan, time cursor · Pop-out · Scroll page when browser-zoomed`}
            />
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            {peerView.length > 0 && (
              <label style={{ fontSize: '0.82rem', display: 'flex', alignItems: 'center', gap: 6 }}>
                <input
                  type="checkbox"
                  checked={dualStacked}
                  onChange={(e) => setDualStacked(e.target.checked)}
                />
                Both ends (SIGRA-style)
              </label>
            )}
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
        <div
          style={{
            flex: '1 1 auto',
            minHeight: 'min(70dvh, 720px)',
            height: 'max(520px, calc(100dvh - 140px))',
            display: 'flex',
            flexDirection: 'column',
            gap: 10,
            padding: '0 14px 10px',
          }}
        >
          {showDual ? (
            <>
              <div style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-muted)' }}>
                {leftEndLabel}
              </div>
              <WaveformViewer channels={viewChannels} markers={markers} height={320} />
              <div style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-muted)' }}>
                {rightEndLabel}
                {syncUs != null ? ' · time-aligned' : ''}
              </div>
              <WaveformViewer channels={peerView} markers={peerMarkersAligned} height={320} />
            </>
          ) : (
            <WaveformViewer channels={viewChannels} markers={markers} fill />
          )}
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
              maxHeight: 160,
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

  const endSelectLabel = ends.length > 1 ? 'COMTRADE end' : 'End';

  return (
    <div>
      <div className="page-header" style={{ padding: 0, marginBottom: 12 }}>
        <div style={{ flex: 1 }}>
          <CombinedPageHeader
            title="Waveform viewer"
            subtitle={`${channels.length} channels${markers.length ? ` · ${markers.length} markers` : ''} · Zoom, pan, time cursor`}
          />
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          {peerView.length > 0 && (
            <label style={{ fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: 6 }}>
              <input
                type="checkbox"
                checked={dualStacked}
                onChange={(e) => setDualStacked(e.target.checked)}
              />
              Both ends (SIGRA-style)
            </label>
          )}
          {ends.length > 1 && !dualStacked && (
            <label style={{ fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: 6 }}>
              {endSelectLabel}
              <select
                className="input"
                value={selectedEnd}
                onChange={(e) => {
                  setSelectedEnd(e.target.value);
                  load(e.target.value, peerEnd || undefined);
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
          {syncUs != null && (
            <span className="mono" style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
              sync Δ {(syncUs / 1000).toFixed(2)} ms
            </span>
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
      {showDual ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <div style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)', marginBottom: 4 }}>
              {leftEndLabel}
            </div>
            <WaveformViewer channels={viewChannels} markers={markers} height={360} />
          </div>
          <div>
            <div style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)', marginBottom: 4 }}>
              {rightEndLabel}
              {syncUs != null ? ' · time-aligned to initiator/local' : ''}
            </div>
            <WaveformViewer channels={peerView} markers={peerMarkersAligned} height={360} />
          </div>
        </div>
      ) : (
        <WaveformViewer channels={viewChannels} markers={markers} height={460} />
      )}
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
