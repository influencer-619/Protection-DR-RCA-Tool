import { Link } from 'react-router-dom';
import { DQ_GLOSSARY, STATUS_GLOSSARY } from '@/utils/statusGlossary';
import styles from './HelpPage.module.css';

const HIGHLIGHT_STATUSES = [
  'CONSISTENT',
  'INCONSISTENT',
  'UNVERIFIABLE',
  'INCONCLUSIVE',
  'NOT_VERIFIED',
  'NOT_CALCULABLE',
  'DATA_INSUFFICIENT',
  'CLASSIFIED',
  'UNKNOWN',
  'FAILED',
];

export function HelpPage() {
  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>User guide</h1>
          <p className="subtitle">
            How to launch, analyse disturbance records, and complete engineer review
          </p>
        </div>
        <Link className="btn btn-primary" to="/events/new">
          Create event
        </Link>
      </div>

      <div className="alert alert-info" style={{ marginBottom: 16 }}>
        Professional workflow (same idea as SIGRA / Synchrowave Event): upload COMTRADE → validate →
        waveforms & timeline → electrical / protection → consistency vs settings → RCA → report →
        engineer review. Hover any status badge in the app for a short explanation.
      </div>

      <div className={styles.grid}>
        <section className="panel">
          <div className="panel-header">Start / stop</div>
          <div className="panel-body">
            <ol>
              <li>
                Double-click <span className="mono">ProtectionRCA.exe</span> in the project or
                portable-share folder.
              </li>
              <li>
                Browser opens at <span className="mono">http://127.0.0.1:8001</span> (portable) or{' '}
                <span className="mono">http://127.0.0.1:5173</span> (dev). The control window shows
                LAN URLs for other PCs on your network.
              </li>
              <li>Keep the “Protection RCA is running” window open while you work.</li>
              <li>Close that window (or Stop &amp; Close) to shut down API + UI.</li>
            </ol>
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">Typical workflow</div>
          <div className="panel-body">
            <ol>
              <li>
                <Link to="/events/new">Events → New event</Link> (leave unknown fields blank).
              </li>
              <li>Files → upload CFG + DAT (or CFF), relay settings, SOE / event report.</li>
              <li>COMTRADE → confirm detection / validation status.</li>
              <li>Run analysis and follow the “Recommended next step” banner.</li>
              <li>Inspect Waveforms (I / V / Digitals) → Sequence of operation.</li>
              <li>
                Fault characteristics (type, timing, magnitudes). Use{' '}
                <em>Location (optional)</em> only when line parameters / distance elements apply.
              </li>
              <li>Protection (any scheme: 50/51, 21, 87, BF, …) → Consistency → RCA → Evidence.</li>
              <li>Report → Review (ACCEPT / MODIFY / REJECT / …).</li>
            </ol>
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">Safety reminders</div>
          <div className="panel-body">
            <ul>
              <li>Read-only — no relay or breaker control.</li>
              <li>No generative AI in analysis or reports.</li>
              <li>Never invent measurements, settings, or fault location.</li>
              <li>Disabled element + pickup/trip ⇒ INCONSISTENT, not auto “malfunction”.</li>
              <li>Labels like NOT VERIFIED / NOT CALCULABLE / INCONCLUSIVE are intentional.</li>
              <li>
                The tool is scheme-agnostic: overcurrent, earth fault, differential, distance, BF,
                etc. Location/km is optional, not the centre of every analysis.
              </li>
            </ul>
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">Sample COMTRADE for practice</div>
          <div className="panel-body">
            <p className="mono" style={{ fontSize: '0.85rem' }}>
              test_data/comtrade/ieee_1999/ag_fault.cfg
              <br />
              test_data/comtrade/ieee_1999/ag_fault.dat
            </p>
            <p style={{ color: 'var(--text-muted)', marginTop: 8 }}>
              <Link to="/events/new">Create a new event</Link>, upload both files, run analysis, then
              explore each tab.
            </p>
          </div>
        </section>
      </div>

      <section className="panel" style={{ marginTop: 16 }}>
        <div className="panel-header">Status glossary (hover badges anywhere for the same text)</div>
        <div className="panel-body">
          <dl className={styles.glossary}>
            {HIGHLIGHT_STATUSES.map((key) => (
              <div key={key} className={styles.glossaryRow}>
                <dt className="mono">{key.replace(/_/g, ' ')}</dt>
                <dd>{STATUS_GLOSSARY[key]}</dd>
              </div>
            ))}
          </dl>
          <h3 className={styles.subhead}>Data quality</h3>
          <dl className={styles.glossary}>
            {Object.entries(DQ_GLOSSARY).map(([key, text]) => (
              <div key={key} className={styles.glossaryRow}>
                <dt className="mono">{key}</dt>
                <dd>{text}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      <p style={{ marginTop: 20, color: 'var(--text-muted)' }}>
        Full document: <span className="mono">docs/USER_GUIDE.md</span>. Word copy:{' '}
        <span className="mono">Protection_RCA_User_Guide.doc</span> in the project root /{' '}
        <span className="mono">docs/</span> folder.
      </p>
    </div>
  );
}
