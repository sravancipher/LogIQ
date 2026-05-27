import React, { useState, useContext } from 'react';
import { AppContext } from '../App.jsx';
import { apiFetch } from '../utils/api.js';
import { tsShort, formatGroupLabel } from '../utils/helpers.js';

function ErrorGroupsTable({ groups }) {
  if (!Array.isArray(groups) || !groups.length) {
    return <div className="empty-state">No grouped errors yet.</div>;
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

export default function AIInsights() {
  const { apiKey } = useContext(AppContext);
  const [lookback, setLookback] = useState('60');
  const [deepAnalysis, setDeepAnalysis] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [emptyMsg, setEmptyMsg] = useState('Select a window and click Analyse.');
  const [notifyEmail, setNotifyEmail] = useState('');
  const [notifyGroupIndex, setNotifyGroupIndex] = useState('');
  const [notifyNote, setNotifyNote] = useState('');
  const [notifyAlert, setNotifyAlert] = useState({ show: false, msg: '', type: '' });

  const loadInsights = async () => {
    if (!apiKey) return;
    setLoading(true);
    setResult(null);
    setEmptyMsg('');
    const r = await apiFetch(
      `/api/v1/insights?lookback_minutes=${lookback}&deep_analysis=${deepAnalysis}`,
      {}, apiKey
    );
    setLoading(false);
    if (!r.ok) {
      setEmptyMsg(r.body.detail || 'Failed.');
      return;
    }
    setResult(r.body);
  };

  const notifyFromInsight = async () => {
    if (!notifyEmail.trim()) {
      setNotifyAlert({ show: true, msg: 'Recipient email is required.', type: 'error' });
      return;
    }
    if (!apiKey) {
      setNotifyAlert({ show: true, msg: 'Enter your API key in the sidebar.', type: 'error' });
      return;
    }
    if (!result) {
      setNotifyAlert({ show: true, msg: 'Run Analyse first to generate insight context.', type: 'error' });
      return;
    }
    const payload = {
      recipient_email: notifyEmail.trim(),
      lookback_minutes: Number(lookback),
      deep_analysis: deepAnalysis,
      note: notifyNote.trim() || null,
      severity: 'HIGH',
    };
    if (notifyGroupIndex !== '' && Array.isArray(result.error_groups) && result.error_groups[Number(notifyGroupIndex)]) {
      const g = result.error_groups[Number(notifyGroupIndex)];
      payload.target_service_name = g.service_name;
      payload.target_error_type   = g.error_type;
      payload.target_operation    = g.operation;
    }
    setNotifyAlert({ show: false, msg: '', type: '' });
    const res = await apiFetch('/api/v1/alerts/insights/notify', {
      method: 'POST',
      body: JSON.stringify(payload),
    }, apiKey);
    if (!res.ok) {
      setNotifyAlert({ show: true, msg: res.body.detail || 'Failed to send insight notification.', type: 'error' });
      return;
    }
    if (res.body.email) {
      setNotifyAlert({ show: true, msg: `Insight notification sent to ${res.body.recipient_email}.`, type: 'success' });
    } else {
      setNotifyAlert({ show: true, msg: `${res.body.message || 'Notification was not delivered.'} Check SMTP settings.`, type: 'error' });
    }
  };

  const conf = result?.confidence;
  const confPct    = conf != null ? `${(conf * 100).toFixed(0)}%` : '\u2014';
  const confWidth  = conf != null ? `${Math.round(conf * 100)}%` : '0%';

  return (
    <div>
      <div className="page-header"><h2>AI Insights</h2></div>

      <div className="card mb-16">
        <div className="gap-12" style={{ alignItems: 'flex-end' }}>
          <div className="form-row" style={{ marginBottom: 0 }}>
            <label>Lookback Window</label>
            <select value={lookback} onChange={e => setLookback(e.target.value)} style={{ width: '168px' }}>
              <option value="15">Last 15 minutes</option>
              <option value="30">Last 30 minutes</option>
              <option value="60">Last 1 hour</option>
              <option value="360">Last 6 hours</option>
              <option value="1440">Last 24 hours</option>
            </select>
          </div>
          <div className="form-row" style={{ marginBottom: 0, minWidth: '220px' }}>
            <label>Analysis Mode</label>
            <label style={{ display: 'flex', gap: '8px', alignItems: 'center', color: 'var(--text-sub)', fontSize: '12px', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={deepAnalysis}
                onChange={e => setDeepAnalysis(e.target.checked)}
                style={{ width: '16px', height: '16px', accentColor: 'var(--cyan)' }}
              />
              Deep analysis (slower, higher quality)
            </label>
          </div>
          <button className="btn btn-primary" onClick={loadInsights}>Analyse</button>
          {loading && <span><span className="spinner"></span></span>}
        </div>
      </div>

      {result ? (
        <div>
          <div className="grid4 mb-16">
            <div className="stat-card">
              <div className="stat-bar cyan"></div>
              <div className="stat-lbl">Total Logs</div>
              <div className="stat-val cyan">{result.total_logs ?? '\u2014'}</div>
            </div>
            <div className="stat-card">
              <div className="stat-bar red"></div>
              <div className="stat-lbl">Error Logs</div>
              <div className="stat-val red">{result.error_logs ?? '\u2014'}</div>
            </div>
            <div className="stat-card">
              <div className="stat-bar green"></div>
              <div className="stat-lbl">Top Service</div>
              <div className="stat-val green" style={{ fontSize: '16px', wordBreak: 'break-all' }}>{result.top_service || '\u2014'}</div>
            </div>
            <div className="stat-card">
              <div className="stat-bar yellow"></div>
              <div className="stat-lbl">Top Error Type</div>
              <div className="stat-val yellow" style={{ fontSize: '16px', wordBreak: 'break-all' }}>{result.top_error_type || '\u2014'}</div>
            </div>
          </div>

          <div className="card mb-16">
            <div className="card-title">Top Error Groups</div>
            <div className="table-wrap">
              <ErrorGroupsTable groups={result.error_groups || []} />
            </div>
          </div>

          <div className="card mb-16">
            <div className="card-title">Incident Summary</div>
            <p style={{ fontSize: '14px', lineHeight: '1.8', color: 'var(--text-sub)' }}>{result.incident_summary || '\u2014'}</p>
            <p style={{ marginTop: '10px', fontSize: '12px', color: 'var(--cyan)' }}>
              {result.target_error_group
                ? `Fix target group: ${formatGroupLabel(result.target_error_group)}`
                : 'Fix target group: not identified'}
            </p>
            <div className="gap-8 mt-16">
              <ContribGroupTags groups={result.contributing_error_groups || []} />
            </div>
          </div>

          <div className="grid2 mb-16">
            <div className="card">
              <div className="card-title">Root Cause</div>
              <p style={{ fontSize: '14px', lineHeight: '1.75', color: 'var(--text-sub)' }}>{result.root_cause || '\u2014'}</p>
              <div className="conf-bar-wrap">
                <div className="conf-bar-header">
                  <span>AI Confidence</span>
                  <span style={{ color: 'var(--cyan)', fontWeight: 600 }}>{confPct}</span>
                </div>
                <div className="conf-bar-track">
                  <div className="conf-bar-fill" style={{ width: confWidth }}></div>
                </div>
              </div>
            </div>
            <div className="card">
              <div className="card-title">Suggestion</div>
              <p style={{ fontSize: '14px', lineHeight: '1.75', color: 'var(--text-sub)' }}>{result.suggestion || '\u2014'}</p>
            </div>
          </div>

          <div className="card mb-16">
            <div className="card-title">Action Plan</div>
            <ol className="step-list">
              {Array.isArray(result.action_plan) && result.action_plan.length > 0
                ? result.action_plan.map((step, i) => <li key={i}>{step}</li>)
                : <li>No action plan returned.</li>
              }
            </ol>
          </div>

          <div className="card mb-16">
            <div className="card-title">Notify From This Insight</div>
            {notifyAlert.show && (
              <div className={`alert-box ${notifyAlert.type}`}>{notifyAlert.msg}</div>
            )}
            <div className="form-row">
              <label>Recipient Email *</label>
              <input type="email" placeholder="e.g. owner@company.com" value={notifyEmail} onChange={e => setNotifyEmail(e.target.value)} />
            </div>
            <div className="form-row">
              <label>Error Group (optional)</label>
              <select value={notifyGroupIndex} onChange={e => setNotifyGroupIndex(e.target.value)}>
                <option value="">Auto (target error group)</option>
                {(result.error_groups || []).map((g, idx) => (
                  <option key={idx} value={String(idx)}>{formatGroupLabel(g)}</option>
                ))}
              </select>
            </div>
            <div className="form-row">
              <label>Optional Note</label>
              <textarea rows={3} placeholder="Any extra context to include in the email" value={notifyNote} onChange={e => setNotifyNote(e.target.value)}></textarea>
            </div>
            <button className="btn btn-primary" onClick={notifyFromInsight}>Send Insight Notification</button>
          </div>
        </div>
      ) : (
        !loading && <div className="empty-state">{emptyMsg}</div>
      )}
    </div>
  );
}
