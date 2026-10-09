import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '@/services/api';
import type {
  FaultClassification,
  ProtectionOperation,
  TimelineEntry,
  WaveformChannelData,
  WaveformMarker,
} from '@/types';
import { WaveformViewer } from '@/components/WaveformViewer';
import { PhasorDiagram, type PhasorVector } from '@/components/PhasorDiagram';
import { RXPlot } from '@/components/RXPlot';
import { HarmonicsBars } from '@/components/HarmonicsBars';
import { HarmonicsHeatmap } from '@/components/HarmonicsHeatmap';
import { CursorReadout } from '@/components/CursorReadout';
import { OneLineBay } from '@/components/OneLineBay';
import { SettingsObservedStrip } from '@/components/SettingsObservedStrip';
import { Skeleton } from '@/components/Skeleton';
import { EmptyState } from '@/components/EmptyState';
import { useEventOrWorkspace } from '@/context/EventWorkspaceContext';
import { unitLabel } from '@/utils/formatElectrical';
import { loadEventDistanceZones } from '@/utils/distanceZones';
import {
  loadProfiles,
  upsertProfile,
  type DrDisplayProfile,
} from '@/utils/displayProfiles';
import { loadDrSession, markDrVisited, saveDrSession } from '@/utils/drSession';
import { useQuantitySide } from '@/hooks/useQuantitySide';
import { QuantitySideToggle } from '@/components/QuantitySideToggle';
import {
  detectAvailableSides,
  filterWaveformChannelsBySide,
  sideLabel,
  classifyChannelSide,
} from '@/utils/quantitySide';
import {
  filterRxPointsForFault,
  isRxLocusApplicable,
  rxLocusEmptyHint,
} from '@/utils/rxLocus';
import {
  resolveBaySchemeHint,
  resolveDistanceApplicable,
  resolveFaultType,
} from '@/utils/schemeContext';
import { CombinedPageHeader } from '@/components/CombinedPageHeader';
import {
  alignRemoteMarkers,
  alignRemoteToLocal,
  buildCascadeDigitalStrip,
  buildOverlayChannels,
} from '@/utils/dualEndWaveforms';
import styles from './DrWorkspacePage.module.css';

type DualViewMode = 'side' | 'stacked' | 'overlay';

function endOverlayTag(label: string | undefined, fallback: string): string {
  if (!label?.trim()) return fallback;
  const u = label.trim().toUpperCase();
  return u.length <= 6 ? u : u.slice(0, 4);
}

export function DrWorkspacePage() {
  const { id } = useParams<{ id: string }>();
  const { event, analysisRevision } = useEventOrWorkspace(id);
  const { mode: quantitySide, setMode: setQuantitySide } = useQuantitySide(id);
  const [channelsLocal, setChannelsLocal] = useState<WaveformChannelData[]>([]);
  const [channelsRemote, setChannelsRemote] = useState<WaveformChannelData[]>([]);
  const [markers, setMarkers] = useState<WaveformMarker[]>([]);
  const [markersRemote, setMarkersRemote] = useState<WaveformMarker[]>([]);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const session = id ? loadDrSession(id) : null;
  const [cursorA, setCursorA] = useState<number | null>(session?.cursorA ?? null);
  const [cursorB, setCursorB] = useState<number | null>(session?.cursorB ?? null);
  const [ends, setEnds] = useState<
    Array<{ comtrade_file_id: string; end_label?: string; station_name?: string }>
  >([]);
  const [localId, setLocalId] = useState(session?.localId || '');
  const [remoteId, setRemoteId] = useState(session?.remoteId || '');
  const [syncUs, setSyncUs] = useState<number | null>(null);
  const [viewMode, setViewMode] = useState<DualViewMode>('side');
  const [profiles, setProfiles] = useState<DrDisplayProfile[]>(() => loadProfiles());
  const [sessionRestored] = useState(Boolean(session));
  const [protection, setProtection] = useState<ProtectionOperation[]>([]);
  const [fault, setFault] = useState<FaultClassification | null>(null);

  useEffect(() => {
    if (!id) return;
    markDrVisited(id);
  }, [id]);

  useEffect(() => {
    if (!id) return;
    void api
      .getProtection(id)
      .then(setProtection)
      .catch(() => setProtection([]));
    void api
      .getFaultClassification(id)
      .then((f) => setFault(Array.isArray(f) ? f[0] ?? null : f))
      .catch(() => setFault(null));
  }, [id, analysisRevision]);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    void Promise.all([
      api.getComtradeEnds(id).catch(() => ({ ends: [], computed_sync_offset_us: null })),
      api.getTimeline(id).catch(() => [] as TimelineEntry[]),
    ]).then(async ([endsRes, tl]) => {
      setTimeline(tl);
      const list = (endsRes.ends || []) as Array<{
        comtrade_file_id: string;
        end_label?: string;
        station_name?: string;
      }>;
      setEnds(list);
      setSyncUs(
        typeof endsRes.computed_sync_offset_us === 'number'
          ? endsRes.computed_sync_offset_us
          : null,
      );
      const saved = loadDrSession(id);
      const lab = (e: { end_label?: string }) => String(e.end_label || '').toUpperCase();
      const local =
        list.find((e) => e.comtrade_file_id === saved?.localId) ||
        list.find((e) => lab(e) === 'INITIATOR') ||
        list.find((e) => lab(e) === 'LOCAL') ||
        list[0];
      const remote =
        list.find((e) => e.comtrade_file_id === saved?.remoteId) ||
        list.find((e) => lab(e) === 'BACKUP') ||
        list.find((e) => lab(e).startsWith('REMOTE')) ||
        list[1];
      const lid = local?.comtrade_file_id ? String(local.comtrade_file_id) : '';
      const rid = remote?.comtrade_file_id ? String(remote.comtrade_file_id) : '';
      setLocalId(lid);
      setRemoteId(rid);
      const wf = await api.getWaveforms(id, lid ? { comtradeFileId: lid } : undefined);
      setChannelsLocal(wf.channels);
      setMarkers(wf.markers);
      if (saved?.cursorA == null && wf.markers?.length) {
        const inception = wf.markers.find((m) => /inception|fault/i.test(m.label || ''));
        if (inception) setCursorA(inception.t_us);
      }
      if (rid && rid !== lid) {
        const wfR = await api.getWaveforms(id, { comtradeFileId: rid });
        setChannelsRemote(wfR.channels);
        setMarkersRemote(wfR.markers || []);
      } else {
        setChannelsRemote([]);
        setMarkersRemote([]);
      }
    }).finally(() => setLoading(false));
  }, [id, analysisRevision]);

  useEffect(() => {
    if (!id || loading) return;
    saveDrSession({
      eventId: id,
      cursorA,
      cursorB,
      localId,
      remoteId,
      updatedAt: new Date().toISOString(),
    });
  }, [id, cursorA, cursorB, localId, remoteId, loading]);

  const sides = useMemo(
    () =>
      detectAvailableSides(
        channelsLocal.map((c) => ({
          name: c.channel.name,
          units: c.channel.units,
          ps: c.channel.ps,
          channel_type: c.channel.channel_type,
        })),
      ),
    [channelsLocal],
  );
  const dualSide = sides.hasPrimary && sides.hasSecondary;
  const plotChannels = useMemo(
    () => filterWaveformChannelsBySide(channelsLocal, dualSide ? quantitySide : 'both'),
    [channelsLocal, quantitySide, dualSide],
  );
  const remotePlotRaw = useMemo(
    () => filterWaveformChannelsBySide(channelsRemote, dualSide ? quantitySide : 'both'),
    [channelsRemote, quantitySide, dualSide],
  );
  /** SIGRA: remote shifted onto local trigger timebase. */
  const remotePlot = useMemo(
    () => alignRemoteToLocal(remotePlotRaw, syncUs),
    [remotePlotRaw, syncUs],
  );
  const remoteMarkersAligned = useMemo(
    () => alignRemoteMarkers(markersRemote, syncUs),
    [markersRemote, syncUs],
  );
  const localEndMeta = useMemo(
    () => ends.find((e) => e.comtrade_file_id === localId),
    [ends, localId],
  );
  const remoteEndMeta = useMemo(
    () => ends.find((e) => e.comtrade_file_id === remoteId),
    [ends, remoteId],
  );
  const leftOverlayTag = endOverlayTag(localEndMeta?.end_label, 'END1');
  const rightOverlayTag = endOverlayTag(remoteEndMeta?.end_label, 'END2');
  const overlayChannels = useMemo(() => {
    if (!remotePlot.length) return [];
    return buildOverlayChannels(plotChannels, remotePlot, leftOverlayTag, rightOverlayTag);
  }, [plotChannels, remotePlot, leftOverlayTag, rightOverlayTag]);
  const cascadeDigitals = useMemo(() => {
    if (!remotePlot.length) return [];
    return buildCascadeDigitalStrip(
      plotChannels,
      remotePlot,
      leftOverlayTag,
      rightOverlayTag,
    );
  }, [plotChannels, remotePlot, leftOverlayTag, rightOverlayTag]);

  const tMin = useMemo(() => {
    let m = Infinity;
    plotChannels.forEach((c) => {
      if (c.time_us.length) m = Math.min(m, Number(c.time_us[0]));
    });
    return Number.isFinite(m) ? m : 0;
  }, [plotChannels]);

  const phasors = useMemo(() => {
    const extra = (event?.extra || {}) as Record<string, unknown>;
    const ra = (extra.report_analysis || {}) as Record<string, unknown>;
    const ea = (ra.electrical_analysis || {}) as Record<string, unknown>;
    const ph = (ea.phasors || {}) as Record<
      string,
      { value?: { magnitude?: number; angle_deg?: number }; status?: string; unit?: string }
    >;
    const colors = ['#e07020', '#2aaa55', '#2a8fd4'];
    const vectors: PhasorVector[] = [];
    let i = 0;
    const sideMode = dualSide ? quantitySide : 'both';
    for (const [name, row] of Object.entries(ph)) {
      if (row?.status !== 'OK' || row.value?.angle_deg == null) continue;
      if (sideMode !== 'both') {
        const side = classifyChannelSide(name, row.unit);
        if (side !== 'unknown' && side !== sideMode) continue;
        if (side === 'unknown' && sideMode === 'primary') continue;
      }
      vectors.push({
        id: name,
        label: name,
        mag: Number(row.value.magnitude ?? 0),
        angleDeg: Number(row.value.angle_deg),
        unit: row.unit || undefined,
        color: colors[i++ % colors.length],
      });
    }
    return vectors.slice(0, 6);
  }, [event, dualSide, quantitySide]);

  const rxPoints = useMemo(() => {
    const extra = (event?.extra || {}) as Record<string, unknown>;
    const ra = (extra.report_analysis || {}) as Record<string, unknown>;
    const ea = (ra.electrical_analysis || {}) as Record<string, unknown>;
    const z = (ea.impedance || {}) as Record<
      string,
      { value?: { R?: number; X?: number }; status?: string }
    >;
    const colors = ['#e07020', '#2aaa55', '#2a8fd4', '#c47a00'];
    return Object.entries(z)
      .filter(([, v]) => v?.status === 'OK' && v.value?.R != null)
      .map(([k, v], idx) => {
        let label = k;
        if (k.startsWith('loop_')) label = `Z${k.slice(5)}`;
        else if (k.startsWith('phase_')) label = `Z${k.slice(6)}`;
        return {
          id: k,
          label,
          r: Number(v.value!.R),
          x: Number(v.value!.X ?? 0),
          color: colors[idx % colors.length],
        };
      });
  }, [event]);

  const faultTypeForRx = useMemo(
    () =>
      resolveFaultType({
        fault,
        eventFaultType: event?.fault_type,
        eventExtra: (event?.extra || {}) as Record<string, unknown>,
      }),
    [fault, event],
  );

  const distanceApplicableForRx = useMemo(
    () =>
      resolveDistanceApplicable({
        fault,
        protection,
        eventExtra: (event?.extra || {}) as Record<string, unknown>,
      }),
    [fault, protection, event],
  );

  const rxLocusOk = isRxLocusApplicable(distanceApplicableForRx, faultTypeForRx);
  const rxLocusPoints = useMemo(
    () => (rxLocusOk ? filterRxPointsForFault(rxPoints, faultTypeForRx) : []),
    [rxLocusOk, rxPoints, faultTypeForRx],
  );

  const zones = useMemo(() => {
    if (!rxLocusOk) return [];
    return loadEventDistanceZones((event?.extra || {}) as Record<string, unknown>);
  }, [rxLocusOk, event]);

  const harmonicSeries = useMemo(() => {
    const extra = (event?.extra || {}) as Record<string, unknown>;
    const ra = (extra.report_analysis || {}) as Record<string, unknown>;
    const ea = (ra.electrical_analysis || {}) as Record<string, unknown>;
    const harms = (ea.harmonics || {}) as Record<
      string,
      {
        value?: { harmonics_rms?: Record<string, number>; thd_percent?: number };
        status?: string;
        unit?: string;
      }
    >;
    const colors = ['#e07020', '#2aaa55', '#2a8fd4', '#c47a00'];
    return Object.entries(harms)
      .filter(([, v]) => v?.status === 'OK' && v.value?.harmonics_rms)
      .slice(0, 3)
      .map(([ch, v], i) => ({
        channel: ch,
        harmonics: v.value!.harmonics_rms!,
        thdPercent: v.value?.thd_percent ?? null,
        color: colors[i % colors.length],
        unit: unitLabel(v.unit, ch) !== '—' ? unitLabel(v.unit, ch) : undefined,
      }));
  }, [event]);

  const harmonicHeatmap = useMemo(() => {
    const extra = (event?.extra || {}) as Record<string, unknown>;
    const ra = (extra.report_analysis || {}) as Record<string, unknown>;
    const ea = (ra.electrical_analysis || {}) as Record<string, unknown>;
    const hm = (ea.harmonics_heatmap || {}) as Record<
      string,
      {
        status?: string;
        times_s?: number[];
        harmonics_rms?: Record<string, number[]>;
        unit?: string;
      }
    >;
    return Object.entries(hm)
      .filter(([, v]) => v?.status === 'OK' && (v.times_s?.length || 0) > 0)
      .slice(0, 3)
      .map(([ch, v]) => ({
        channel: ch,
        times_s: v.times_s || [],
        harmonics_rms: v.harmonics_rms || {},
        unit: unitLabel(v.unit, ch) !== '—' ? unitLabel(v.unit, ch) : undefined,
      }));
  }, [event]);

  const observed = useMemo(() => {
    const find = (types: string[]) => {
      const hit = timeline.find((t) => types.includes(String(t.event_type || '').toLowerCase()));
      if (!hit) return null;
      if (hit.t_us != null) return Number(hit.t_us) / 1e6;
      return null;
    };
    return {
      pickup_s: find(['protection_pickup']),
      trip_s: find(['protection_trip', 'breaker_trip_command']),
      breaker_s: find(['52a_change', '52b_change']),
      interrupt_s: find(['current_interruption']),
    };
  }, [timeline]);

  const expected = useMemo(() => {
    const extra = (event?.extra || {}) as Record<string, unknown>;
    const rs = (extra.relay_settings || {}) as Record<string, Record<string, unknown>>;
    const el51 = rs['51'] || rs['21'] || {};
    const bf = rs['50BF'] || {};
    return {
      pickup_s: typeof el51.pickup_time_s === 'number' ? el51.pickup_time_s : null,
      trip_s: typeof el51.trip_time_s === 'number' ? el51.trip_time_s : null,
      bf_timer_s: typeof bf.bf_timer_s === 'number' ? Number(bf.bf_timer_s) : null,
      source: (extra.setting_source as string) || null,
    };
  }, [event]);

  const eventExtra = (event?.extra || {}) as Record<string, unknown>;
  const labels = (eventExtra.plant_labels || {}) as Record<string, string>;
  const distanceMeta = (() => {
    const ra = (eventExtra.report_analysis || {}) as Record<string, unknown>;
    const fc = (ra.fault_classification || {}) as Record<string, unknown>;
    const d = (fc.distance || {}) as Record<string, unknown>;
    const applicable = distanceApplicableForRx;
    const km =
      applicable && typeof fault?.distance_km === 'number'
        ? fault.distance_km
        : applicable && typeof d.value_km === 'number'
          ? d.value_km
          : null;
    return { applicable, km };
  })();
  const lineLen = (() => {
    const lp = (eventExtra.line_params || {}) as Record<string, unknown>;
    return typeof lp.length_km === 'number' ? lp.length_km : null;
  })();
  const schemeHint = resolveBaySchemeHint({
    protection,
    eventExtra,
  });

  const saveProfile = () => {
    const p: DrDisplayProfile = {
      id: `p-${Date.now()}`,
      name: `DR ${new Date().toLocaleString()}`,
      showAnalog: true,
      showDigital: true,
      showRms: false,
      selectedChannelNames: plotChannels.map((c) => c.channel.name),
      layout: channelsRemote.length ? 'split' : 'stacked',
      updatedAt: new Date().toISOString(),
    };
    upsertProfile(p);
    setProfiles(loadProfiles());
  };

  if (loading) return <Skeleton rows={8} label="Loading DR workspace" />;

  if (!channelsLocal.length) {
    return (
      <EmptyState
        title="No waveforms for DR workspace"
        description="Upload COMTRADE and run analysis, then open this unified viewer."
        actions={[
          { label: 'Go to Files', to: id ? `/events/${id}/files` : '/events', primary: true },
        ]}
      />
    );
  }

  const leftPane = localEndMeta?.end_label || 'Local end';
  const rightPane = remoteEndMeta?.end_label || 'Remote end';
  const leftSelect = 'Primary end';
  const rightSelect = 'Peer end';

  const showEndsBar = ends.length > 1;
  const missingPeerEnd = ends.length >= 2 && channelsRemote.length === 0;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div style={{ flex: 1 }}>
          <CombinedPageHeader
            title="DR workspace"
            subtitle={`Waveforms, cursors, phasors, R–X, and harmonics${sessionRestored ? ' · last view restored' : ''}`}
          />
        </div>
        <div className={styles.tools}>
          <QuantitySideToggle
            mode={quantitySide}
            onChange={setQuantitySide}
            show={dualSide}
          />
          <button
            type="button"
            className="btn btn-sm"
            onClick={saveProfile}
            title="Remember channel layout preferences for next time"
          >
            Remember this view
          </button>
          {profiles.length > 0 && (
            <span className={styles.profileHint}>
              {profiles.length} saved view{profiles.length === 1 ? '' : 's'}
            </span>
          )}
        </div>
      </div>

      <OneLineBay
        substation={event?.substation_name || labels.substation_name}
        bay={event?.bay_name || labels.bay_name}
        relay={event?.relay_tag || labels.relay_tag}
        feeder={event?.feeder}
        faultType={faultTypeForRx || event?.fault_type}
        distanceKm={distanceMeta.applicable ? distanceMeta.km : null}
        lineLengthKm={lineLen}
        distanceApplicable={distanceMeta.applicable}
        schemeHint={schemeHint}
        onOpenDr={() => {
          const inception = markers.find((m) =>
            /inception|fault/i.test(m.label || ''),
          );
          if (inception) setCursorA(inception.t_us);
          window.scrollTo({ top: 0, behavior: 'smooth' });
        }}
      />

      <SettingsObservedStrip expected={expected} observed={observed} />

      {missingPeerEnd && (
        <div className="alert alert-warn" role="status">
          Multiple COMTRADE ends are registered but peer waveforms are not loaded. Select a peer
          end above or use <strong>Re-run analysis</strong>, then reopen DR.
        </div>
      )}

      {showEndsBar && (
        <div className={styles.endsBar}>
          <label>
            {leftSelect}
            <select
              className="input"
              value={localId}
              onChange={(e) => {
                setLocalId(e.target.value);
                void api.getWaveforms(id!, { comtradeFileId: e.target.value }).then((r) => {
                  setChannelsLocal(r.channels);
                  setMarkers(r.markers);
                });
              }}
            >
              {ends.length === 0 && <option value="">No ends yet</option>}
              {ends.map((en) => (
                <option key={en.comtrade_file_id} value={en.comtrade_file_id}>
                  {en.end_label || 'END'} {en.station_name || ''}
                </option>
              ))}
            </select>
          </label>
          <label>
            {rightSelect}
            <select
              className="input"
              value={remoteId}
              onChange={(e) => {
                setRemoteId(e.target.value);
                void api.getWaveforms(id!, { comtradeFileId: e.target.value }).then((r) => {
                  setChannelsRemote(r.channels);
                  setMarkersRemote(r.markers || []);
                });
              }}
            >
              <option value="">—</option>
              {ends.map((en) => (
                <option key={en.comtrade_file_id} value={en.comtrade_file_id}>
                  {en.end_label || 'END'} {en.station_name || ''}
                </option>
              ))}
            </select>
          </label>
          {syncUs != null && (
            <span className={`mono ${styles.syncBadge}`} title="Remote trigger − local trigger (SIGRA-style common timebase)">
              sync Δ {syncUs.toFixed(0)} µs ({(syncUs / 1000).toFixed(2)} ms) · remote aligned
            </span>
          )}
          {channelsRemote.length > 0 && (
            <label className={styles.viewMode}>
              View
              <select
                className="input"
                value={viewMode}
                onChange={(e) => setViewMode(e.target.value as DualViewMode)}
                title="SIGRA-style: side-by-side, stacked, or overlay same analogs from both ends"
              >
                <option value="side">Side-by-side (both ends)</option>
                <option value="stacked">Stacked (both ends)</option>
                <option value="overlay">Overlay compare (N1+N2)</option>
              </select>
            </label>
          )}
        </div>
      )}

      {dualSide && (
        <div className="alert alert-info" role="status" style={{ marginBottom: 0 }}>
          Viewing <strong>{sideLabel(quantitySide)}</strong> — this COMTRADE has both secondary (A/V)
          and primary (kA/kV) channels. Analysis / RCA use secondary by default.
        </div>
      )}

      {channelsRemote.length > 0 && viewMode === 'overlay' ? (
        <div>
          <div className={styles.paneTitle}>
            Overlay · {leftPane} + {rightPane} (common timebase
            {syncUs != null ? ` · Δ ${(syncUs / 1000).toFixed(2)} ms` : ''})
          </div>
          <WaveformViewer
            channels={overlayChannels}
            markers={[...markers, ...remoteMarkersAligned]}
            height={440}
            cursorAUs={cursorA}
            cursorBUs={cursorB}
            onCursorsChange={(a, b) => {
              setCursorA(a);
              setCursorB(b);
            }}
            hideReadout
          />
          {cascadeDigitals.length > 0 && (
            <>
              <div className={styles.paneTitle} style={{ marginTop: 8 }}>
                Protection digitals (both ends, synced)
              </div>
              <WaveformViewer
                channels={cascadeDigitals}
                markers={[...markers, ...remoteMarkersAligned]}
                height={220}
                cursorAUs={cursorA}
                cursorBUs={cursorB}
                onCursorsChange={(a, b) => {
                  setCursorA(a);
                  setCursorB(b);
                }}
                hideReadout
              />
            </>
          )}
        </div>
      ) : (
        <div
          className={
            channelsRemote.length
              ? viewMode === 'stacked'
                ? styles.stacked
                : styles.split
              : undefined
          }
        >
          <div>
            <div className={styles.paneTitle}>{leftPane}</div>
            <WaveformViewer
              channels={plotChannels}
              markers={markers}
              height={channelsRemote.length ? (viewMode === 'stacked' ? 360 : 320) : 420}
              cursorAUs={cursorA}
              cursorBUs={cursorB}
              onCursorsChange={(a, b) => {
                setCursorA(a);
                setCursorB(b);
              }}
              hideReadout
            />
          </div>
          {channelsRemote.length > 0 && (
            <div>
              <div className={styles.paneTitle}>
                {rightPane}
                {syncUs != null ? ' · time-aligned' : ''}
              </div>
              <WaveformViewer
                channels={remotePlot}
                markers={remoteMarkersAligned}
                height={viewMode === 'stacked' ? 360 : 320}
                cursorAUs={cursorA}
                cursorBUs={cursorB}
                onCursorsChange={(a, b) => {
                  setCursorA(a);
                  setCursorB(b);
                }}
                hideReadout
              />
            </div>
          )}
        </div>
      )}

      <CursorReadout
        channels={
          viewMode === 'overlay' && overlayChannels.length ? overlayChannels : plotChannels
        }
        cursorA={cursorA}
        cursorB={cursorB}
        tMin={tMin}
        quantitySide={dualSide ? quantitySide : 'secondary'}
      />
      {channelsRemote.length > 0 && viewMode !== 'overlay' && (
        <CursorReadout
          channels={remotePlot}
          cursorA={cursorA}
          cursorB={cursorB}
          tMin={tMin}
          quantitySide={dualSide ? quantitySide : 'secondary'}
        />
      )}

      <div className={styles.panels}>
        <PhasorDiagram title="Phasors (fault window)" vectors={phasors} />
        <RXPlot
          title={rxLocusOk ? `R–X locus (${faultTypeForRx || 'Ω'})` : 'R–X locus'}
          points={rxLocusPoints}
          zones={zones}
          emptyHint={rxLocusEmptyHint(distanceApplicableForRx, faultTypeForRx)}
        />
        <HarmonicsBars series={harmonicSeries} />
        <HarmonicsHeatmap channels={harmonicHeatmap} />
      </div>
    </div>
  );
}
