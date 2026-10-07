import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { api } from '@/services/api';
import type { PlantTree } from '@/types';
import styles from './PlantPage.module.css';

type Level = 'substation' | 'voltage' | 'bay' | 'feeder' | 'ied';
type AddKind = Level | null;

interface TreeNode {
  key: string;
  level: Level;
  id: string;
  name: string;
  code?: string;
  meta?: string;
  eventCount?: number;
  total: number;
  children: TreeNode[];
}

const LEVELS: Record<
  Level,
  { label: string; plural: string; child?: Level; empty?: string; className: string; icon: ReactNode }
> = {
  substation: {
    label: 'Substation',
    plural: 'Substations',
    child: 'voltage',
    empty: 'No voltage levels',
    className: styles.lvlSs,
    icon: (
      <>
        <path d="M3 21h18" />
        <path d="M5 21V10l7-5 7 5v11" />
        <path d="M12 9l-2 4h4l-2 4" />
      </>
    ),
  },
  voltage: {
    label: 'Voltage level',
    plural: 'Voltage levels',
    child: 'bay',
    empty: 'No bays',
    className: styles.lvlKv,
    icon: <path d="M13 2L4 14h6l-1 8 9-12h-6l1-8z" />,
  },
  bay: {
    label: 'Bay',
    plural: 'Bays',
    child: 'feeder',
    empty: 'No feeders',
    className: styles.lvlBay,
    icon: (
      <>
        <rect x="4" y="4" width="16" height="16" rx="2" />
        <path d="M4 10h16M10 10v10" />
      </>
    ),
  },
  feeder: {
    label: 'Feeder',
    plural: 'Feeders',
    child: 'ied',
    empty: 'No IEDs — add one to upload or fetch records',
    className: styles.lvlFdr,
    icon: (
      <>
        <path d="M12 3v18" />
        <path d="M6 8h12M8 14h8" />
        <circle cx="12" cy="3" r="1" />
      </>
    ),
  },
  ied: {
    label: 'IED',
    plural: 'IEDs',
    className: styles.lvlIed,
    icon: (
      <>
        <rect x="5" y="3" width="14" height="18" rx="2" />
        <path d="M9 7h6M9 11h6" />
        <circle cx="12" cy="16" r="1.5" />
      </>
    ),
  },
};

const ORDER: Level[] = ['substation', 'voltage', 'bay', 'feeder', 'ied'];

type VoltageUnit = 'kV' | 'V';

function tidyKv(n: number): number {
  return Number(Number(n).toPrecision(8));
}

/** Parse a kilovolt value from the field (kV or V) or from a name like "33", "33kV", "33000 V". */
function parseKv(rawKv: string, rawName: string, unit: VoltageUnit = 'kV'): number | undefined {
  const fromField = rawKv.trim().replace(/,/g, '');
  if (fromField) {
    const n = Number(fromField.replace(/[^\d.+-eE]/g, ''));
    if (Number.isFinite(n) && n > 0) return tidyKv(unit === 'V' ? n / 1000 : n);
  }
  const withUnit = rawName.trim().match(/(\d+(?:\.\d+)?)\s*(kV|V)\b/i);
  if (withUnit) {
    const n = Number(withUnit[1]);
    if (Number.isFinite(n) && n > 0) {
      return tidyKv(withUnit[2].toLowerCase() === 'kv' ? n : n / 1000);
    }
  }
  const m = rawName.trim().match(/^(\d+(?:\.\d+)?)\s*k?v?$/i);
  if (m) {
    const n = Number(m[1]);
    if (Number.isFinite(n) && n > 0) return tidyKv(unit === 'V' ? n / 1000 : n);
  }
  return undefined;
}

function voltageLevelName(rawName: string, kv: number | undefined): string {
  const name = rawName.trim();
  if (!name && kv != null) return `${kv} kV`;
  if (kv == null) return name;
  if (/\bkV\b/i.test(name)) return name;
  // Pure numeric name → attach unit
  if (/^\d+(?:\.\d+)?$/.test(name)) return `${kv} kV`;
  return name;
}

function countNoun(cfg: { label: string; plural: string }, n: number): string {
  const word = n === 1 ? cfg.label : cfg.plural;
  return cfg.label === cfg.label.toUpperCase() ? word : word.toLowerCase();
}

function LevelIcon({ level }: { level: Level }) {
  return (
    <span className={`${styles.lvlIcon} ${LEVELS[level].className}`} aria-hidden="true">
      <svg viewBox="0 0 24 24">{LEVELS[level].icon}</svg>
    </span>
  );
}

function buildTree(tree: PlantTree | null): TreeNode[] {
  return (tree?.substations ?? []).map((s) => ({
    key: `s-${s.id}`,
    level: 'substation',
    id: s.id,
    name: s.name,
    code: s.code,
    total: s.voltage_levels.length,
    children: s.voltage_levels.map((v) => ({
      key: `v-${v.id}`,
      level: 'voltage',
      id: v.id,
      name: v.name,
      meta: v.nominal_voltage_kv != null ? `${v.nominal_voltage_kv} kV` : undefined,
      total: v.bays.length,
      children: v.bays.map((b) => ({
        key: `b-${b.id}`,
        level: 'bay',
        id: b.id,
        name: b.name,
        total: b.feeders.length,
        children: b.feeders.map((f) => ({
          key: `f-${f.id}`,
          level: 'feeder',
          id: f.id,
          name: f.name,
          total: f.ieds.length,
          children: f.ieds.map((i) => ({
            key: `i-${i.id}`,
            level: 'ied',
            id: i.id,
            name: i.name,
            code: i.relay_tag,
            eventCount: i.event_count,
            total: 0,
            children: [],
          })),
        })),
      })),
    })),
  }));
}

function filterTree(nodes: TreeNode[], q: string): TreeNode[] {
  if (!q) return nodes;
  const out: TreeNode[] = [];
  for (const n of nodes) {
    const hit = n.name.toLowerCase().includes(q) || (n.code ?? '').toLowerCase().includes(q);
    const kids = hit ? n.children : filterTree(n.children, q);
    if (hit || kids.length) out.push({ ...n, children: kids });
  }
  return out;
}

function allKeys(nodes: TreeNode[], acc: Record<string, boolean> = {}): Record<string, boolean> {
  for (const n of nodes) {
    if (n.level !== 'ied') acc[n.key] = true;
    allKeys(n.children, acc);
  }
  return acc;
}

function countByLevel(nodes: TreeNode[], acc: Record<Level, number>): Record<Level, number> {
  for (const n of nodes) {
    acc[n.level] += 1;
    countByLevel(n.children, acc);
  }
  return acc;
}

export function PlantPage() {
  const [tree, setTree] = useState<PlantTree | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [adding, setAdding] = useState<{ kind: AddKind; parentId?: string; parentName?: string }>({
    kind: null,
  });
  const [editing, setEditing] = useState<{
    kind: Level;
    id: string;
    name: string;
    kv: string;
    unit: VoltageUnit;
  } | null>(null);
  const [name, setName] = useState('');
  const [kv, setKv] = useState('');
  const [kvUnit, setKvUnit] = useState<VoltageUnit>('kV');
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState('');
  const initialised = useRef(false);

  const nodes = useMemo(() => buildTree(tree), [tree]);
  const q = query.trim().toLowerCase();
  const visible = useMemo(() => filterTree(nodes, q), [nodes, q]);
  const counts = useMemo(
    () => countByLevel(nodes, { substation: 0, voltage: 0, bay: 0, feeder: 0, ied: 0 }),
    [nodes],
  );
  const totalEvents = useMemo(() => {
    let n = 0;
    const walk = (list: TreeNode[]) =>
      list.forEach((x) => {
        n += x.eventCount ?? 0;
        walk(x.children);
      });
    walk(nodes);
    return n;
  }, [nodes]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getPlantTree();
      setTree(data);
      if (!initialised.current) {
        initialised.current = true;
        setExpanded(allKeys(buildTree(data)));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load plant');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const toggle = (key: string) => setExpanded((p) => ({ ...p, [key]: !p[key] }));

  const startAdd = (kind: AddKind, parentId?: string, parentName?: string) => {
    setEditing(null);
    setAdding({ kind, parentId, parentName });
    setName('');
    setKv('');
    setKvUnit('kV');
  };

  const startEdit = (n: TreeNode) => {
    setAdding({ kind: null });
    const kvMatch = n.meta?.match(/^(\d+(?:\.\d+)?)\s*kV$/i);
    setEditing({
      kind: n.level,
      id: n.id,
      name: n.name,
      kv: kvMatch?.[1] ?? '',
      unit: 'kV',
    });
  };

  const submitEdit = async () => {
    if (!editing) return;
    const trimmed = editing.name.trim();
    const isVoltage = editing.kind === 'voltage';
    const parsedKv = isVoltage ? parseKv(editing.kv, trimmed, editing.unit) : undefined;
    const vlName = isVoltage ? voltageLevelName(trimmed, parsedKv) : trimmed;
    if (!vlName) return;
    setBusy(true);
    setError(null);
    try {
      if (editing.kind === 'substation') {
        await api.updateSubstation(editing.id, { name: vlName });
      } else if (editing.kind === 'voltage') {
        await api.updateVoltageLevel(editing.id, {
          name: vlName,
          nominal_voltage_kv: parsedKv,
        });
      } else if (editing.kind === 'bay') {
        await api.updateBay(editing.id, { name: vlName });
      } else if (editing.kind === 'feeder') {
        await api.updateFeeder(editing.id, { name: vlName });
      } else {
        await api.updateIed(editing.id, { name: vlName });
      }
      setEditing(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Rename failed');
    } finally {
      setBusy(false);
    }
  };

  const submitAdd = async () => {
    if (!adding.kind) return;
    const isVoltage = adding.kind === 'voltage';
    const parsedKv = isVoltage ? parseKv(kv, name, kvUnit) : undefined;
    const vlName = isVoltage ? voltageLevelName(name, parsedKv) : name.trim();
    if (!isVoltage && !name.trim()) return;
    if (isVoltage && !vlName) return;
    setBusy(true);
    setError(null);
    try {
      if (adding.kind === 'substation') {
        await api.createSubstation({ name: name.trim() });
      } else if (isVoltage && adding.parentId) {
        await api.createVoltageLevel({
          substation_id: adding.parentId,
          name: vlName,
          nominal_voltage_kv: parsedKv,
        });
      } else if (adding.kind === 'bay' && adding.parentId) {
        await api.createBay({ voltage_level_id: adding.parentId, name: name.trim() });
      } else if (adding.kind === 'feeder' && adding.parentId) {
        await api.createFeeder({ bay_id: adding.parentId, name: name.trim() });
      } else if (adding.kind === 'ied' && adding.parentId) {
        await api.createIed({ feeder_id: adding.parentId, name: name.trim() });
      }
      const parentPrefix = { voltage: 's', bay: 'v', feeder: 'b', ied: 'f' } as Partial<Record<Level, string>>;
      const prefix = parentPrefix[adding.kind];
      if (prefix && adding.parentId) setExpanded((p) => ({ ...p, [`${prefix}-${adding.parentId}`]: true }));
      setAdding({ kind: null });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Create failed');
    } finally {
      setBusy(false);
    }
  };

  const remove = async (kind: Level, id: string, label: string) => {
    if (!window.confirm(`Delete ${label}? Child items will also be removed.`)) return;
    setBusy(true);
    try {
      if (kind === 'substation') await api.deleteSubstation(id);
      else if (kind === 'voltage') await api.deleteVoltageLevel(id);
      else if (kind === 'bay') await api.deleteBay(id);
      else if (kind === 'feeder') await api.deleteFeeder(id);
      else await api.deleteIed(id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Delete failed');
    } finally {
      setBusy(false);
    }
  };

  const renderNode = (n: TreeNode): ReactNode => {
    const cfg = LEVELS[n.level];
    const isIed = n.level === 'ied';
    const open = q ? true : !!expanded[n.key];
    const childCfg = cfg.child ? LEVELS[cfg.child] : null;
    const isEditing = editing?.kind === n.level && editing.id === n.id;
    return (
      <li key={n.key} className={`${styles.node} ${n.level === 'substation' ? styles.rootNode : ''}`}>
        <div className={`${styles.row} ${isIed ? styles.iedRow : ''}`}>
          {isIed ? (
            <span className={styles.twistySpacer} />
          ) : (
            <button
              type="button"
              className={`${styles.twisty} ${open ? styles.twistyOpen : ''}`}
              onClick={() => toggle(n.key)}
              aria-label={open ? `Collapse ${n.name}` : `Expand ${n.name}`}
              aria-expanded={open}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M9 6l6 6-6 6" />
              </svg>
            </button>
          )}
          <LevelIcon level={n.level} />
          <div className={styles.main}>
            {isEditing && editing ? (
              <span className={styles.editRow}>
                <input
                  className={styles.editInput}
                  value={editing.name}
                  autoFocus
                  aria-label={`Rename ${cfg.label}`}
                  onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') void submitEdit();
                    if (e.key === 'Escape') setEditing(null);
                  }}
                />
                {n.level === 'voltage' && (
                  <span className={styles.kvField}>
                    <input
                      className={styles.inputSm}
                      placeholder={editing.unit === 'V' ? '33000' : '33'}
                      inputMode="decimal"
                      aria-label={`Nominal voltage in ${editing.unit}`}
                      value={editing.kv}
                      onChange={(e) => setEditing({ ...editing, kv: e.target.value })}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') void submitEdit();
                        if (e.key === 'Escape') setEditing(null);
                      }}
                    />
                    <select
                      className={styles.kvUnit}
                      aria-label="Voltage unit"
                      value={editing.unit}
                      onChange={(e) =>
                        setEditing({ ...editing, unit: e.target.value as VoltageUnit })
                      }
                    >
                      <option value="kV">kV</option>
                      <option value="V">V</option>
                    </select>
                  </span>
                )}
                <button
                  type="button"
                  className="btn btn-sm btn-primary"
                  disabled={
                    busy ||
                    (n.level === 'voltage'
                      ? !voltageLevelName(
                          editing.name,
                          parseKv(editing.kv, editing.name, editing.unit),
                        )
                      : !editing.name.trim())
                  }
                  onClick={() => void submitEdit()}
                >
                  Save
                </button>
                <button
                  type="button"
                  className="btn btn-sm"
                  disabled={busy}
                  onClick={() => setEditing(null)}
                >
                  Cancel
                </button>
              </span>
            ) : isIed ? (
              <Link to={`/plant/ieds/${n.id}`} className={styles.iedLink}>
                {n.name}
              </Link>
            ) : (
              <button
                type="button"
                className={styles.labelBtn}
                onDoubleClick={() => startEdit(n)}
                title="Double-click to rename"
              >
                {n.name}
              </button>
            )}
            {!isEditing && <span className={styles.levelTag}>{cfg.label}</span>}
            {!isEditing && n.code && <span className={styles.code}>{n.code}</span>}
            {!isEditing && n.meta && <span className={styles.metaChip}>{n.meta}</span>}
            {!isEditing && childCfg && (
              <span className={styles.count}>
                {n.total} {countNoun(childCfg, n.total)}
              </span>
            )}
            {!isEditing && isIed && (
              <span className={`${styles.count} ${n.eventCount ? styles.countHot : ''}`}>
                {n.eventCount ?? 0} event{n.eventCount === 1 ? '' : 's'}
              </span>
            )}
          </div>
          <div className={styles.actions}>
            {!isEditing && childCfg && cfg.child && (
              <button
                type="button"
                className={styles.ghostBtn}
                onClick={() => startAdd(cfg.child!, n.id, n.name)}
              >
                + {childCfg.label}
              </button>
            )}
            {!isEditing && isIed && (
              <Link to={`/plant/ieds/${n.id}`} className="btn btn-sm btn-primary">
                Open
              </Link>
            )}
            {!isEditing && (
              <button
                type="button"
                className={styles.editBtn}
                onClick={() => startEdit(n)}
                title={`Rename ${n.name}`}
                aria-label={`Rename ${n.name}`}
                disabled={busy}
              >
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M12 20h9" />
                  <path d="M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4L16.5 3.5z" />
                </svg>
              </button>
            )}
            {!isEditing && (
              <button
                type="button"
                className={styles.deleteBtn}
                onClick={() => void remove(n.level, n.id, n.name)}
                title={`Delete ${n.name}`}
                aria-label={`Delete ${n.name}`}
                disabled={busy}
              >
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 002 2h6a2 2 0 002-2l1-12M9 7V4h6v3" />
                </svg>
              </button>
            )}
          </div>
        </div>
        {open && !isIed && (
          <ul className={styles.children}>
            {n.children.map(renderNode)}
            {n.children.length === 0 && <li className={styles.emptyChild}>{cfg.empty}</li>}
          </ul>
        )}
      </li>
    );
  };

  const addCfg = adding.kind ? LEVELS[adding.kind] : null;

  return (
    <div className={`page ${styles.page}`}>
      <div className={styles.top}>
        <div>
          <h1>Plant hierarchy</h1>
          <p className={styles.sub}>
            Build the site tree, then open an IED to fetch or upload disturbance records.
          </p>
        </div>
        <button type="button" className="btn btn-primary" onClick={() => startAdd('substation')}>
          + Substation
        </button>
      </div>

      <div className={styles.stats} aria-label="Plant hierarchy levels">
        {ORDER.map((lvl, i) => (
          <div key={lvl} className={`${styles.stat} ${LEVELS[lvl].className}`}>
            <LevelIcon level={lvl} />
            <div className={styles.statBody}>
              <span className={styles.statVal}>{counts[lvl]}</span>
              <span className={styles.statLbl}>{LEVELS[lvl].plural}</span>
            </div>
            <span className={styles.statStep}>{i + 1}</span>
          </div>
        ))}
      </div>

      {error && <div className={styles.error}>{error}</div>}

      {adding.kind && addCfg && (
        <div className={`${styles.addBar} ${addCfg.className}`}>
          <LevelIcon level={adding.kind} />
          <div className={styles.addTitle}>
            New {countNoun(addCfg, 1)}
            {adding.parentName && <span className={styles.addParent}>under {adding.parentName}</span>}
          </div>
          <input
            className={styles.input}
            placeholder={
              adding.kind === 'voltage' ? 'Name (e.g. 33 kV) — or leave blank' : `${addCfg.label} name`
            }
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void submitAdd();
              if (e.key === 'Escape') setAdding({ kind: null });
            }}
            autoFocus
          />
          {adding.kind === 'voltage' && (
            <span className={styles.kvField}>
              <input
                className={styles.inputSm}
                placeholder={kvUnit === 'V' ? '33000' : '33'}
                inputMode="decimal"
                aria-label={`Nominal voltage in ${kvUnit}`}
                value={kv}
                onChange={(e) => setKv(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') void submitAdd();
                  if (e.key === 'Escape') setAdding({ kind: null });
                }}
              />
              <select
                className={styles.kvUnit}
                aria-label="Voltage unit"
                value={kvUnit}
                onChange={(e) => setKvUnit(e.target.value as VoltageUnit)}
              >
                <option value="kV">kV</option>
                <option value="V">V</option>
              </select>
            </span>
          )}
          <button
            type="button"
            className="btn btn-primary"
            disabled={
              busy ||
              (adding.kind === 'voltage'
                ? !voltageLevelName(name, parseKv(kv, name, kvUnit))
                : !name.trim())
            }
            onClick={() => void submitAdd()}
          >
            Save
          </button>
          <button type="button" className="btn btn-sm" onClick={() => setAdding({ kind: null })}>
            Cancel
          </button>
        </div>
      )}

      <section className={styles.workspace}>
        <div className={styles.workspaceHead}>
          <div>
            <h2>Structure</h2>
            <span className={styles.hint}>
              {counts.ied} IED{counts.ied === 1 ? '' : 's'} · {totalEvents} event
              {totalEvents === 1 ? '' : 's'} · open an IED to fetch or upload records
            </span>
          </div>
          {nodes.length > 0 && (
            <div className={styles.headTools}>
              <label className={styles.search}>
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <circle cx="11" cy="11" r="6.5" />
                  <path d="M20 20l-4.2-4.2" />
                </svg>
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Filter by name or tag"
                  aria-label="Filter plant tree"
                />
              </label>
              <button
                type="button"
                className={styles.ghostBtn}
                onClick={() => setExpanded(allKeys(nodes))}
                disabled={!!q}
              >
                Expand all
              </button>
              <button
                type="button"
                className={styles.ghostBtn}
                onClick={() => setExpanded({})}
                disabled={!!q}
              >
                Collapse all
              </button>
            </div>
          )}
        </div>

        {loading && <p className={styles.muted}>Loading plant…</p>}

        {!loading && tree && nodes.length === 0 && (
          <div className={styles.empty}>
            <div className={styles.emptyIcon}>
              <LevelIcon level="substation" />
            </div>
            <div className={styles.emptyTitle}>No plant yet</div>
            <p>
              Create a substation, then add voltage level → bay → feeder → IED. Disturbance records
              are fetched or uploaded under an IED.
            </p>
            <button type="button" className="btn btn-primary" onClick={() => startAdd('substation')}>
              Add first substation
            </button>
          </div>
        )}

        {!loading && nodes.length > 0 && visible.length === 0 && (
          <p className={styles.muted}>Nothing matches “{query.trim()}”.</p>
        )}

        {!loading && visible.length > 0 && <ul className={styles.tree}>{visible.map(renderNode)}</ul>}
      </section>
    </div>
  );
}
