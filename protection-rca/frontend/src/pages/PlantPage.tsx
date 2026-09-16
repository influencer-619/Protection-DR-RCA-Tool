import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '@/services/api';
import type { PlantTree } from '@/types';
import styles from './PlantPage.module.css';

type AddKind = 'substation' | 'voltage' | 'bay' | 'feeder' | 'ied' | null;

const STEPS = [
  { key: 'ss', label: 'Substation' },
  { key: 'kv', label: 'Voltage' },
  { key: 'bay', label: 'Bay' },
  { key: 'fdr', label: 'Feeder' },
  { key: 'ied', label: 'IED' },
] as const;

export function PlantPage() {
  const [tree, setTree] = useState<PlantTree | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [adding, setAdding] = useState<{ kind: AddKind; parentId?: string }>({ kind: null });
  const [name, setName] = useState('');
  const [kv, setKv] = useState('');
  const [busy, setBusy] = useState(false);

  const counts = useMemo(() => {
    let ss = 0;
    let vl = 0;
    let bay = 0;
    let fdr = 0;
    let ied = 0;
    for (const s of tree?.substations ?? []) {
      ss += 1;
      for (const v of s.voltage_levels) {
        vl += 1;
        for (const b of v.bays) {
          bay += 1;
          for (const f of b.feeders) {
            fdr += 1;
            ied += f.ieds.length;
          }
        }
      }
    }
    return { ss, vl, bay, fdr, ied };
  }, [tree]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getPlantTree();
      setTree(data);
      setExpanded((prev) => {
        if (Object.keys(prev).length) return prev;
        const next: Record<string, boolean> = {};
        for (const s of data.substations) {
          next[`s-${s.id}`] = true;
          for (const vl of s.voltage_levels) {
            next[`v-${vl.id}`] = true;
            for (const b of vl.bays) {
              next[`b-${b.id}`] = true;
              for (const f of b.feeders) next[`f-${f.id}`] = true;
            }
          }
        }
        return next;
      });
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

  const startAdd = (kind: AddKind, parentId?: string) => {
    setAdding({ kind, parentId });
    setName('');
    setKv('');
  };

  const submitAdd = async () => {
    if (!adding.kind || !name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      if (adding.kind === 'substation') {
        await api.createSubstation({ name: name.trim() });
      } else if (adding.kind === 'voltage' && adding.parentId) {
        await api.createVoltageLevel({
          substation_id: adding.parentId,
          name: name.trim(),
          nominal_voltage_kv: kv ? Number(kv) : undefined,
        });
      } else if (adding.kind === 'bay' && adding.parentId) {
        await api.createBay({ voltage_level_id: adding.parentId, name: name.trim() });
      } else if (adding.kind === 'feeder' && adding.parentId) {
        await api.createFeeder({ bay_id: adding.parentId, name: name.trim() });
      } else if (adding.kind === 'ied' && adding.parentId) {
        await api.createIed({ feeder_id: adding.parentId, name: name.trim() });
      }
      setAdding({ kind: null });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Create failed');
    } finally {
      setBusy(false);
    }
  };

  const remove = async (
    kind: 'substation' | 'voltage' | 'bay' | 'feeder' | 'ied',
    id: string,
    label: string,
  ) => {
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

  const addTitle =
    adding.kind === 'substation'
      ? 'New substation'
      : adding.kind === 'voltage'
        ? 'New voltage level'
        : adding.kind === 'bay'
          ? 'New bay'
          : adding.kind === 'feeder'
            ? 'New feeder'
            : adding.kind === 'ied'
              ? 'New IED'
              : '';

  return (
    <div className={`page ${styles.page}`}>
      <div className={styles.top}>
        <div>
          <h1>Plant hierarchy</h1>
          <p className={styles.sub}>
            Build the site tree, then open an IED to upload disturbance records.
          </p>
        </div>
        <button type="button" className="btn btn-primary" onClick={() => startAdd('substation')}>
          + Substation
        </button>
      </div>

      <ol className={styles.steps} aria-label="Plant hierarchy levels">
        {STEPS.map((s, i) => (
          <li key={s.key} className={styles.step}>
            <span className={styles.stepNum}>{i + 1}</span>
            <span className={styles.stepLabel}>{s.label}</span>
            {i < STEPS.length - 1 && <span className={styles.stepArrow} aria-hidden />}
          </li>
        ))}
      </ol>

      <div className={styles.stats}>
        <div className={styles.stat}>
          <span className={styles.statVal}>{counts.ss}</span>
          <span className={styles.statLbl}>Substations</span>
        </div>
        <div className={styles.stat}>
          <span className={styles.statVal}>{counts.vl}</span>
          <span className={styles.statLbl}>Voltage levels</span>
        </div>
        <div className={styles.stat}>
          <span className={styles.statVal}>{counts.bay}</span>
          <span className={styles.statLbl}>Bays</span>
        </div>
        <div className={styles.stat}>
          <span className={styles.statVal}>{counts.fdr}</span>
          <span className={styles.statLbl}>Feeders</span>
        </div>
        <div className={styles.stat}>
          <span className={styles.statVal}>{counts.ied}</span>
          <span className={styles.statLbl}>IEDs</span>
        </div>
      </div>

      {error && <div className={styles.error}>{error}</div>}

      {adding.kind && (
        <div className={styles.addBar}>
          <span className={styles.addTitle}>{addTitle}</span>
          <input
            className={styles.input}
            placeholder="Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void submitAdd();
            }}
            autoFocus
          />
          {adding.kind === 'voltage' && (
            <input
              className={styles.inputSm}
              placeholder="kV"
              value={kv}
              onChange={(e) => setKv(e.target.value)}
            />
          )}
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy || !name.trim()}
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
          <h2>Structure</h2>
          <span className={styles.hint}>Click an IED name to upload and analyse</span>
        </div>

        {loading && <p className={styles.muted}>Loading plant…</p>}

        {!loading && tree && tree.substations.length === 0 && (
          <div className={styles.empty}>
            <div className={styles.emptyTitle}>No plant yet</div>
            <p>
              Create a substation, then add voltage level → bay → feeder → IED. Analysis files are
              uploaded only under an IED.
            </p>
            <button type="button" className="btn btn-primary" onClick={() => startAdd('substation')}>
              Add first substation
            </button>
          </div>
        )}

        {!loading && tree && tree.substations.length > 0 && (
          <ul className={styles.tree}>
            {tree.substations.map((sub) => (
              <li key={sub.id} className={`${styles.node} ${styles.levelSs}`}>
                <div className={styles.row}>
                  <button type="button" className={styles.twisty} onClick={() => toggle(`s-${sub.id}`)}>
                    {expanded[`s-${sub.id}`] ? '▾' : '▸'}
                  </button>
                  <span className={`${styles.badge} ${styles.badgeSs}`}>SS</span>
                  <div className={styles.main}>
                    <span className={styles.label}>{sub.name}</span>
                    <span className={styles.code}>{sub.code}</span>
                  </div>
                  <div className={styles.actions}>
                    <button type="button" className="btn btn-sm" onClick={() => startAdd('voltage', sub.id)}>
                      + Voltage
                    </button>
                    <button
                      type="button"
                      className="btn btn-sm"
                      onClick={() => void remove('substation', sub.id, sub.name)}
                    >
                      Delete
                    </button>
                  </div>
                </div>
                {expanded[`s-${sub.id}`] && (
                  <ul className={styles.children}>
                    {sub.voltage_levels.map((vl) => (
                      <li key={vl.id} className={styles.node}>
                        <div className={styles.row}>
                          <button
                            type="button"
                            className={styles.twisty}
                            onClick={() => toggle(`v-${vl.id}`)}
                          >
                            {expanded[`v-${vl.id}`] ? '▾' : '▸'}
                          </button>
                          <span className={`${styles.badge} ${styles.badgeKv}`}>kV</span>
                          <div className={styles.main}>
                            <span className={styles.label}>{vl.name}</span>
                            {vl.nominal_voltage_kv != null && (
                              <span className={styles.meta}>{vl.nominal_voltage_kv} kV</span>
                            )}
                          </div>
                          <div className={styles.actions}>
                            <button
                              type="button"
                              className="btn btn-sm"
                              onClick={() => startAdd('bay', vl.id)}
                            >
                              + Bay
                            </button>
                            <button
                              type="button"
                              className="btn btn-sm"
                              onClick={() => void remove('voltage', vl.id, vl.name)}
                            >
                              Delete
                            </button>
                          </div>
                        </div>
                        {expanded[`v-${vl.id}`] && (
                          <ul className={styles.children}>
                            {vl.bays.map((bay) => (
                              <li key={bay.id} className={styles.node}>
                                <div className={styles.row}>
                                  <button
                                    type="button"
                                    className={styles.twisty}
                                    onClick={() => toggle(`b-${bay.id}`)}
                                  >
                                    {expanded[`b-${bay.id}`] ? '▾' : '▸'}
                                  </button>
                                  <span className={`${styles.badge} ${styles.badgeBay}`}>Bay</span>
                                  <div className={styles.main}>
                                    <span className={styles.label}>{bay.name}</span>
                                  </div>
                                  <div className={styles.actions}>
                                    <button
                                      type="button"
                                      className="btn btn-sm"
                                      onClick={() => startAdd('feeder', bay.id)}
                                    >
                                      + Feeder
                                    </button>
                                    <button
                                      type="button"
                                      className="btn btn-sm"
                                      onClick={() => void remove('bay', bay.id, bay.name)}
                                    >
                                      Delete
                                    </button>
                                  </div>
                                </div>
                                {expanded[`b-${bay.id}`] && (
                                  <ul className={styles.children}>
                                    {bay.feeders.map((feeder) => (
                                      <li key={feeder.id} className={styles.node}>
                                        <div className={styles.row}>
                                          <button
                                            type="button"
                                            className={styles.twisty}
                                            onClick={() => toggle(`f-${feeder.id}`)}
                                          >
                                            {expanded[`f-${feeder.id}`] ? '▾' : '▸'}
                                          </button>
                                          <span className={`${styles.badge} ${styles.badgeFdr}`}>Fdr</span>
                                          <div className={styles.main}>
                                            <span className={styles.label}>{feeder.name}</span>
                                          </div>
                                          <div className={styles.actions}>
                                            <button
                                              type="button"
                                              className="btn btn-sm"
                                              onClick={() => startAdd('ied', feeder.id)}
                                            >
                                              + IED
                                            </button>
                                            <button
                                              type="button"
                                              className="btn btn-sm"
                                              onClick={() =>
                                                void remove('feeder', feeder.id, feeder.name)
                                              }
                                            >
                                              Delete
                                            </button>
                                          </div>
                                        </div>
                                        {expanded[`f-${feeder.id}`] && (
                                          <ul className={styles.children}>
                                            {feeder.ieds.map((ied) => (
                                              <li key={ied.id} className={styles.node}>
                                                <div className={`${styles.row} ${styles.iedRow}`}>
                                                  <span className={styles.twistySpacer} />
                                                  <span className={`${styles.badge} ${styles.badgeIed}`}>
                                                    IED
                                                  </span>
                                                  <div className={styles.main}>
                                                    <Link
                                                      to={`/plant/ieds/${ied.id}`}
                                                      className={styles.iedLink}
                                                    >
                                                      {ied.name}
                                                    </Link>
                                                    <span className={styles.meta}>
                                                      {ied.event_count} event
                                                      {ied.event_count === 1 ? '' : 's'}
                                                    </span>
                                                  </div>
                                                  <div className={styles.actions}>
                                                    <Link
                                                      to={`/plant/ieds/${ied.id}`}
                                                      className="btn btn-sm btn-primary"
                                                    >
                                                      Open
                                                    </Link>
                                                    <button
                                                      type="button"
                                                      className="btn btn-sm"
                                                      onClick={() =>
                                                        void remove('ied', ied.id, ied.name)
                                                      }
                                                    >
                                                      Delete
                                                    </button>
                                                  </div>
                                                </div>
                                              </li>
                                            ))}
                                            {feeder.ieds.length === 0 && (
                                              <li className={styles.emptyChild}>
                                                No IEDs — add one to upload files
                                              </li>
                                            )}
                                          </ul>
                                        )}
                                      </li>
                                    ))}
                                    {bay.feeders.length === 0 && (
                                      <li className={styles.emptyChild}>No feeders</li>
                                    )}
                                  </ul>
                                )}
                              </li>
                            ))}
                            {vl.bays.length === 0 && (
                              <li className={styles.emptyChild}>No bays</li>
                            )}
                          </ul>
                        )}
                      </li>
                    ))}
                    {sub.voltage_levels.length === 0 && (
                      <li className={styles.emptyChild}>No voltage levels</li>
                    )}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
