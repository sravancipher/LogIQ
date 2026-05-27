import React, { useState, useEffect, useCallback, useContext } from 'react';
import { AppContext } from '../App.jsx';
import { apiFetch } from '../utils/api.js';
import { tsShort, formatGroupLabel, badgeLevelClass } from '../utils/helpers.js';

function BadgeLevel({ level = '' }) {
  return <span className={`badge ${badgeLevelClass(level)}`}>{level}</span>;
}

function LogTable({ items }) {
  if (!items || !items.length) return <div className="empty-state">No recent errors.</div>;
  return (
    <table>
      <thead>
        <tr>
          <th>Time</th><th>Level</th><th>Service</th><th>Operation</th>
          <th>Message</th><th>Error Type</th><th>Correlation ID</th>
        </tr>
      </thead>
      <tbody>
        {items.map((r, i) => (
          <tr key={i}>
            <td style={{ whiteSpace: 'nowrap', fontSize: '11.5px', color: 'var(--muted)' }}>{tsShort(r.created_at)}</td>
            <td><BadgeLevel level={r.level} /></td>
            <td><span className="tag">{r.service_name || '\u2014'}</span></td>
            <td style={{ fontSize: '12px', color: 'var(--text-sub)' }}>{r.operation || '\u2014'}</td>
            <td className="msg-cell" title={r.message || ''}>{r.message || '\u2014'}</td>
            <td style={{ fontSize: '12px', color: 'var(--red)' }}>{r.error_type || '\u2014'}</td>
            <td style={{ fontSize: '11px', color: 'var(--muted)', fontFamily: 'monospace' }}>{r.correlation_id || '\u2014'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ErrorGroupsTable({ groups }) {
  if (!Array.isArray(groups) || !groups.length) {
    return <div className="empty-state">No grouped errors in this window.</div>;
  }
  return (
    <table>
      <thead>
        <tr><th>Service</th><th>Error Type</th><th>Operation</th><th>Count</th><th>Last Seen</th></tr>
      </thead>
      <tbody>
        {groups.map((g, i) => (
          <tr key={i}>
            <td><span className="tag">{g.service_name || '\u2014'}</span></td>
            <td style={{ color: 'var(--red)', fontSize: '12px' }}>{g.error_type || '\u2014'}</td>
            <td style={{ fontSize: '12px', color: 'var(--text-sub)' }}>{g.operation || '\u2014'}</td>
            <td><span className="badge badge-error">{g.count || 0}</span></td>
            <td style={{ whiteSpace: 'nowrap', fontSize: '11.5px', color: 'var(--muted)' }}>{tsShort(g.last_seen)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ContribGroupTags({ groups }) {
  if (!Array.isArray(groups) || !groups.length) {
    return <span className="tag">No dependent groups detected</span>;
  }
  return (
    <>
      {groups.map((g, i) => (
        <span key={i} className="tag">
          {formatGroupLabel(g)} (shared corr: {g.shared_correlation_count || 0})
        </span>
      ))}
    </>
  );
}

export default function Overview() {
  const { apiKey, navigateTo } = useContext(AppContext);
  const [data, setData] = useState(null);
  const [recentErrors, setRecentErrors] = useState([]);
  const [alert, setAlert] = useState({ show: true, msg: 'Enter your API key in the sidebar to load live data.', type: 'info' });

  const loadOverview = useCallback(async () => {
    if (!apiKey) {
      setAlert({ show: true, msg: 'Enter your API key in the sidebar.', type: 'info' });
      return;
    }
    setAlert({ show: false, msg: '', type: '' });
    const r = await apiFetch('/api/v1/insights?lookback_minutes=60', {}, apiKey);
    if (!r.ok) {
      setAlert({ show: true, msg: r.body.detail || 'Failed to load insights.', type: 'error' });
      return;
    }
    setData(r.body);
    const lr = await apiFetch('/api/v1/logs?level=ERROR&limit=5', {}, apiKey);
    if (lr.ok && lr.body.items) setRecentErrors(lr.body.items);
    else setRecentErrors([]);
  }, [apiKey]);

  useEffect(() => {
    loadOverview();
  }, [loadOverview]);

  const confPct = data?.confidence != null ? `Confidence: ${(data.confidence * 100).toFixed(0)}%` : '';

  return (
    <div>
      <div className="page-header"><h2>Overview</h2></div>
      {alert.show && (
        <div className={`alert-box ${alert.type}`} style={{ marginBottom: '16px' }}>{alert.msg}</div>
      )}
      <div className="grid4 mb-16">
        <div className="stat-card">
          <div className="stat-bar cyan"></div>
          <div className="stat-lbl">Total Logs (1 h)</div>
          <div className="stat-val cyan">{data?.total_logs ?? '\u2014'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-bar red"></div>
          <div className="stat-lbl">Errors (1 h)</div>
          <div className="stat-val red">{data?.error_logs ?? '\u2014'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-bar green"></div>
          <div className="stat-lbl">Top Service</div>
          <div className="stat-val green" style={{ fontSize: '17px', wordBreak: 'break-all' }}>{data?.top_service || '\u2014'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-bar yellow"></div>
          <div className="stat-lbl">Top Error Type</div>
          <div className="stat-val yellow" style={{ fontSize: '17px', wordBreak: 'break-all' }}>{data?.top_error_type || '\u2014'}</div>
        </div>
      </div>

      <div className="grid2 mb-16">
        <div className="card">
          <div className="card-title">Root Cause Summary</div>
          <p style={{ fontSize: '14px', lineHeight: '1.75', color: 'var(--text-sub)' }}>
            {data?.root_cause || 'Load insights to see AI root-cause analysis.'}
          </p>
          {data?.suggestion && (
            <p style={{ marginTop: '10px', fontSize: '13px', color: 'var(--muted)' }}>{data.suggestion}</p>
          )}
          <p style={{ marginTop: '10px', fontSize: '12px', color: 'var(--cyan)' }}>
            {data?.target_error_group
              ? `Fix target group: ${formatGroupLabel(data.target_error_group)}`
              : data ? 'Fix target group: not identified' : ''}
          </p>
          <div className="gap-8 mt-16">
            <ContribGroupTags groups={data?.contributing_error_groups || []} />
          </div>
          {confPct && (
            <span className="tag" style={{ display: 'inline-block', marginTop: '12px' }}>{confPct}</span>
          )}
        </div>
        <div className="card">
          <div className="card-title">Quick Actions</div>
          <div className="quick-actions">
            <button className="btn btn-primary" onClick={loadOverview}>&#8634; Refresh Overview</button>
            <button className="btn btn-ghost" onClick={() => navigateTo('page-insights')}>Run AI Analysis</button>
            <button className="btn btn-ghost" onClick={() => navigateTo('page-logs')}>Browse Logs</button>
            <button className="btn btn-ghost" onClick={() => navigateTo('page-integrations')}>Manage Integrations</button>
          </div>
        </div>
      </div>

      <div className="card mb-16">
        <div className="card-title">Top Error Groups (Last 1 h)</div>
        <div className="table-wrap">
          <ErrorGroupsTable groups={data?.error_groups || []} />
        </div>
      </div>

      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
          <div className="card-title" style={{ marginBottom: 0 }}>Recent Errors</div>
          <button className="btn btn-ghost btn-sm" onClick={loadOverview}>&#8635; Refresh</button>
        </div>
        <div className="table-wrap">
          <LogTable items={recentErrors} />
        </div>
      </div>
    </div>
  );
}
