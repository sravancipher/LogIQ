import React, { useState, useEffect, useCallback, useContext } from 'react';
import { AppContext } from '../App.jsx';
import { apiFetch } from '../utils/api.js';
import { tsShort, badgeLevelClass } from '../utils/helpers.js';

/* ── helpers ─────────────────────────────────────────────── */

const LOOKBACK_OPTIONS = [
  { label: 'Last 1 hour',   value: 60 },
  { label: 'Last 6 hours',  value: 360 },
  { label: 'Last 24 hours', value: 1440 },
  { label: 'Last 7 days',   value: 10080 },
];

function statusStyle(status) {
  if (status === 'critical') return { color: 'var(--red)',    fontWeight: 700 };
  if (status === 'degraded') return { color: 'var(--yellow)', fontWeight: 700 };
  return { color: 'var(--green)', fontWeight: 700 };
}

function StatusDot({ status }) {
  const colors = { healthy: 'var(--green)', degraded: 'var(--yellow)', critical: 'var(--red)' };
  return (
    <span style={{
      display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
      background: colors[status] || 'var(--muted)', marginRight: 6,
      boxShadow: `0 0 6px ${colors[status] || 'var(--muted)'}`,
    }} />
  );
}

function BadgeLevel({ level = '' }) {
  return <span className={`badge ${badgeLevelClass(level)}`}>{level}</span>;
}

/* ── Server error drill-down ─────────────────────────────── */

function ServerErrors({ serviceName, apiKey }) {
  const [items, setItems]         = useState([]);
  const [loading, setLoading]     = useState(true);
  const [hasNext, setHasNext]     = useState(false);
  const [hasPrev, setHasPrev]     = useState(false);
  const [cursorStack, setCursors] = useState([null]);
  const [pageIdx, setPageIdx]     = useState(0);

  const load = useCallback(async (idx, stack) => {
    setLoading(true);
    let url = `/api/v1/logs?limit=20&level=ERROR&service_name=${encodeURIComponent(serviceName)}`;
    const cursor = stack[idx];
    if (cursor) url += `&cursor=${encodeURIComponent(cursor)}`;
    const r = await apiFetch(url, {}, apiKey);
    setLoading(false);
    if (!r.ok) { setItems([]); return; }
    setItems(r.body.items || []);
    const newStack = [...stack];
    if (r.body.next_cursor && newStack.length === idx + 1) newStack.push(r.body.next_cursor);
    setCursors(newStack);
    setHasPrev(idx > 0);
    setHasNext(!!r.body.next_cursor);
    setPageIdx(idx);
  }, [serviceName, apiKey]);

  useEffect(() => { load(0, [null]); }, [load]);

  if (loading) return <div className="empty-state" style={{ padding: '20px 0' }}>Loading errors…</div>;
  if (!items.length) return <div className="empty-state" style={{ padding: '20px 0', color: 'var(--green)' }}>No errors found for this service.</div>;

  return (
    <div>
      <table>
        <thead>
          <tr>
            <th>Time</th><th>Level</th><th>Operation</th>
            <th>Message</th><th>Error Type</th><th>Correlation ID</th>
          </tr>
        </thead>
        <tbody>
          {items.map((r, i) => (
            <tr key={i}>
              <td style={{ whiteSpace: 'nowrap', fontSize: '11.5px', color: 'var(--muted)' }}>{tsShort(r.created_at)}</td>
              <td><BadgeLevel level={r.level} /></td>
              <td style={{ fontSize: '12px', color: 'var(--text-sub)' }}>{r.operation || '—'}</td>
              <td className="msg-cell" title={r.message || ''}>{r.message || '—'}</td>
              <td style={{ fontSize: '12px', color: 'var(--red)' }}>{r.error_type || '—'}</td>
              <td style={{ fontSize: '11px', color: 'var(--muted)', fontFamily: 'monospace' }}>{r.correlation_id || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginTop: '12px' }}>
        <button className="btn btn-sm" disabled={!hasPrev} onClick={() => load(pageIdx - 1, cursorStack)}>← Prev</button>
        <span style={{ fontSize: '12px', color: 'var(--muted)' }}>Page {pageIdx + 1}</span>
        <button className="btn btn-sm" disabled={!hasNext} onClick={() => load(pageIdx + 1, cursorStack)}>Next →</button>
      </div>
    </div>
  );
}

/* ── Main page ───────────────────────────────────────────── */

export default function Servers() {
  const { apiKey } = useContext(AppContext);
  const [services, setServices]   = useState([]);
  const [loading, setLoading]     = useState(false);
  const [selected, setSelected]   = useState(null);   // service_name string
  const [lookback, setLookback]   = useState(1440);
  const [alert, setAlert]         = useState({ show: true, msg: 'Enter your API key in the sidebar to load servers.', type: 'info' });

  const loadServices = useCallback(async () => {
    if (!apiKey) {
      setAlert({ show: true, msg: 'Enter your API key in the sidebar.', type: 'info' });
      setServices([]);
      return;
    }
    setAlert({ show: false, msg: '', type: '' });
    setLoading(true);
    const r = await apiFetch(`/api/v1/services?lookback_minutes=${lookback}`, {}, apiKey);
    setLoading(false);
    if (!r.ok) {
      setAlert({ show: true, msg: r.body.detail || 'Failed to load services.', type: 'error' });
      return;
    }
    setServices(r.body.services || []);
    if (r.body.services?.length && !selected) setSelected(r.body.services[0].service_name);
  }, [apiKey, lookback]);

  useEffect(() => { loadServices(); }, [loadServices]);

  // Auto-refresh every 30 s so newly started services appear without a manual reload
  useEffect(() => {
    if (!apiKey) return;
    const id = setInterval(loadServices, 30_000);
    return () => clearInterval(id);
  }, [apiKey, loadServices]);

  const totalErrors = services.reduce((s, x) => s + x.error_logs, 0);
  const criticalCount = services.filter(x => x.status === 'critical').length;

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
        <h2>Servers</h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <select
            value={lookback}
            onChange={e => { setLookback(Number(e.target.value)); setSelected(null); }}
            style={{ minWidth: '140px' }}
          >
            {LOOKBACK_OPTIONS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <button className="btn btn-primary btn-sm" onClick={loadServices} disabled={loading}>
            {loading ? 'Loading…' : 'Refresh'}
          </button>
        </div>
      </div>

      {alert.show && (
        <div className={`alert-box ${alert.type}`} style={{ marginBottom: '16px' }}>{alert.msg}</div>
      )}

      {/* Summary stats */}
      <div className="grid4 mb-16">
        <div className="stat-card">
          <div className="stat-bar cyan"></div>
          <div className="stat-lbl">Total Servers</div>
          <div className="stat-val cyan">{services.length || '—'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-bar red"></div>
          <div className="stat-lbl">Total Errors</div>
          <div className="stat-val red">{totalErrors || '—'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-bar" style={{ background: 'var(--red)' }}></div>
          <div className="stat-lbl">Critical Servers</div>
          <div className="stat-val" style={{ color: 'var(--red)' }}>{criticalCount || '—'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-bar" style={{ background: 'var(--green)' }}></div>
          <div className="stat-lbl">Healthy Servers</div>
          <div className="stat-val" style={{ color: 'var(--green)' }}>
            {services.filter(x => x.status === 'healthy').length || '—'}
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-start' }}>
        {/* Left: server list */}
        <div className="card" style={{ minWidth: '240px', width: '240px', padding: 0, flexShrink: 0 }}>
          <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', fontSize: '12px', color: 'var(--muted)', fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase' }}>
            Instances
          </div>
          {loading && (
            <div className="empty-state" style={{ padding: '24px 16px' }}>Loading…</div>
          )}
          {!loading && services.length === 0 && (
            <div className="empty-state" style={{ padding: '24px 16px' }}>No services found in window.</div>
          )}
          {services.map(svc => (
            <div
              key={svc.service_name}
              onClick={() => setSelected(svc.service_name)}
              style={{
                padding: '12px 16px',
                cursor: 'pointer',
                borderBottom: '1px solid var(--border)',
                background: selected === svc.service_name ? 'var(--surface2)' : 'transparent',
                borderLeft: selected === svc.service_name ? '3px solid var(--cyan)' : '3px solid transparent',
                transition: 'background 0.15s',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: '13px', fontWeight: 600, wordBreak: 'break-all' }}>
                  <StatusDot status={svc.status} />{svc.service_name}
                </span>
              </div>
              <div style={{ marginTop: '4px', fontSize: '11px', color: 'var(--muted)', display: 'flex', gap: '8px' }}>
                <span style={statusStyle(svc.status)}>{svc.status}</span>
                <span>{svc.error_logs} err / {svc.total_logs} total</span>
              </div>
              <div style={{ fontSize: '10.5px', color: 'var(--muted)', marginTop: '2px' }}>
                Last seen {tsShort(svc.last_seen)}
              </div>
            </div>
          ))}
        </div>

        {/* Right: error detail for selected server */}
        <div className="card" style={{ flex: 1, minWidth: 0 }}>
          {!selected ? (
            <div className="empty-state">Select a server to view its errors.</div>
          ) : (
            <>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px', flexWrap: 'wrap', gap: '8px' }}>
                <div>
                  <h3 style={{ margin: 0 }}>
                    <StatusDot status={services.find(s => s.service_name === selected)?.status || 'healthy'} />
                    {selected}
                  </h3>
                  <div style={{ fontSize: '12px', color: 'var(--muted)', marginTop: '2px' }}>
                    Recent ERROR / CRITICAL logs
                  </div>
                </div>
                {(() => {
                  const svc = services.find(s => s.service_name === selected);
                  return svc ? (
                    <div style={{ display: 'flex', gap: '12px' }}>
                      <div className="stat-card" style={{ minWidth: 0, padding: '8px 16px' }}>
                        <div className="stat-lbl">Errors</div>
                        <div className="stat-val red" style={{ fontSize: '20px' }}>{svc.error_logs}</div>
                      </div>
                      <div className="stat-card" style={{ minWidth: 0, padding: '8px 16px' }}>
                        <div className="stat-lbl">Total Logs</div>
                        <div className="stat-val cyan" style={{ fontSize: '20px' }}>{svc.total_logs}</div>
                      </div>
                    </div>
                  ) : null;
                })()}
              </div>
              <ServerErrors key={selected} serviceName={selected} apiKey={apiKey} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
