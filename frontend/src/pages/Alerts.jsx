import React, { useState, useEffect, useCallback, useContext } from 'react';
import { AppContext } from '../App.jsx';
import { apiFetch } from '../utils/api.js';

const DEFAULT_CHANNEL_FORM = {
  slack_webhook_url: '',
  teams_webhook_url: '',
  alert_email_from: '',
  alert_email_to: '',
  smtp_host: '',
  smtp_port: 587,
  smtp_username: '',
};

export default function Alerts() {
  const { apiKey } = useContext(AppContext);
  const [title, setTitle] = useState('Test Alert from Dashboard');
  const [message, setMessage] = useState('Manually triggered test alert to verify channel delivery.');
  const [severity, setSeverity] = useState('MEDIUM');
  const [emailTo, setEmailTo] = useState('');
  const [alert, setAlert] = useState({ show: false, msg: '', type: '' });
  const [delivery, setDelivery] = useState(null);

  const [effective, setEffective] = useState(null);
  const [channelForm, setChannelForm] = useState(DEFAULT_CHANNEL_FORM);
  const [smtpPasswordInput, setSmtpPasswordInput] = useState('');
  const [clearSmtpPassword, setClearSmtpPassword] = useState(false);
  const [channelAlert, setChannelAlert] = useState({ show: false, msg: '', type: '' });
  const [channelBusy, setChannelBusy] = useState(false);

  const showAlert = (msg, type = 'info') => setAlert({ show: true, msg, type });
  const hideAlert = () => setAlert({ show: false, msg: '', type: '' });
  const showChannelAlert = (msg, type = 'info') => setChannelAlert({ show: true, msg, type });
  const hideChannelAlert = () => setChannelAlert({ show: false, msg: '', type: '' });

  const loadChannelSettings = useCallback(async () => {
    if (!apiKey) return;
    const r = await apiFetch('/api/v1/alert-settings', {}, apiKey);
    if (r.ok) {
      setEffective(r.body);
      setChannelForm({
        slack_webhook_url: '',
        teams_webhook_url: '',
        alert_email_from: r.body.alert_email_from || '',
        alert_email_to: r.body.alert_email_to || '',
        smtp_host: r.body.smtp_host || '',
        smtp_port: r.body.smtp_port || 587,
        smtp_username: r.body.smtp_username || '',
      });
    }
  }, [apiKey]);

  useEffect(() => {
    loadChannelSettings();
  }, [loadChannelSettings]);

  const sendAlert = async () => {
    if (!title.trim() || !message.trim()) { showAlert('Title and message are required.', 'error'); return; }
    if (!apiKey) { showAlert('Enter your API key in the sidebar.', 'error'); return; }
    hideAlert();
    const r = await apiFetch('/api/v1/alerts/test', {
      method: 'POST',
      body: JSON.stringify({
        title: title.trim(),
        message: message.trim(),
        severity,
        recipient_email: emailTo.trim() || null,
      }),
    }, apiKey);
    if (!r.ok) { showAlert(r.body.detail || 'Request failed.', 'error'); return; }
    setDelivery({ slack: r.body.slack, teams: r.body.teams, email: r.body.email });
    const anyDelivered = r.body.slack || r.body.teams || r.body.email;
    if (anyDelivered) {
      showAlert('Alert sent. See delivery results.', 'success');
    } else {
      showAlert('No channel is configured for this project, so nothing was delivered. See details below.', 'error');
    }
  };

  const saveChannelSettings = async () => {
    if (!apiKey) { showChannelAlert('Enter your API key in the sidebar.', 'error'); return; }
    hideChannelAlert();
    setChannelBusy(true);
    const body = {
      slack_webhook_url: channelForm.slack_webhook_url.trim() || null,
      teams_webhook_url: channelForm.teams_webhook_url.trim() || null,
      alert_email_from: channelForm.alert_email_from.trim() || null,
      alert_email_to: channelForm.alert_email_to.trim() || null,
      smtp_host: channelForm.smtp_host.trim() || null,
      smtp_port: channelForm.smtp_port === '' ? null : Number(channelForm.smtp_port),
      smtp_username: channelForm.smtp_username.trim() || null,
    };
    if (clearSmtpPassword) {
      body.smtp_password = '';
    } else if (smtpPasswordInput.trim()) {
      body.smtp_password = smtpPasswordInput.trim();
    }
    const r = await apiFetch('/api/v1/alert-settings', { method: 'PUT', body: JSON.stringify(body) }, apiKey);
    setChannelBusy(false);
    if (!r.ok) { showChannelAlert(r.body.detail || 'Failed to save alert channels.', 'error'); return; }
    setEffective(r.body);
    setSmtpPasswordInput('');
    setClearSmtpPassword(false);
    showChannelAlert('Saved. This project will use these channels for alerts.', 'success');
  };

  const resetChannelSettings = async () => {
    if (!apiKey) return;
    if (!window.confirm('Remove this project\'s custom alert channels and revert to the system default?')) return;
    hideChannelAlert();
    const r = await apiFetch('/api/v1/alert-settings', { method: 'DELETE' }, apiKey);
    if (r.ok || r.status === 204) {
      showChannelAlert('Reverted to the system default alert channels.', 'success');
      loadChannelSettings();
    }
  };

  const DeliveryBadge = ({ delivered }) =>
    delivered
      ? <span className="badge badge-active">Delivered</span>
      : <span className="badge badge-inactive">Not configured</span>;

  return (
    <div>
      <div className="page-header"><h2>Alerts</h2></div>
      <p style={{ fontSize: '13px', color: 'var(--text-sub)', marginTop: '-8px', marginBottom: '16px' }}>
        This page manually tests notification delivery and lets you email a specific AI Insight. There is no
        automated/triggered alerting yet (e.g. auto-notify when a service goes critical).
      </p>
      <div className="grid2 mb-16">
        <div className="card">
          <div className="card-title">Send a Test Alert</div>
          <p style={{ fontSize: '13px', color: 'var(--text-sub)', marginBottom: '16px' }}>
            Verify your Slack / Teams / email settings for this project.
          </p>
          {alert.show && <div className={`alert-box ${alert.type}`}>{alert.msg}</div>}
          <div className="form-row">
            <label>Title *</label>
            <input type="text" placeholder="e.g. Payment service timeout spike" value={title} onChange={e => setTitle(e.target.value)} />
          </div>
          <div className="form-row">
            <label>Message *</label>
            <textarea rows={3} value={message} onChange={e => setMessage(e.target.value)}></textarea>
          </div>
          <div className="form-row">
            <label>Recipient Email (optional)</label>
            <input type="email" placeholder="e.g. owner@company.com" value={emailTo} onChange={e => setEmailTo(e.target.value)} />
          </div>
          <div className="form-row">
            <label>Severity</label>
            <select value={severity} onChange={e => setSeverity(e.target.value)}>
              <option value="LOW">LOW</option>
              <option value="MEDIUM">MEDIUM</option>
              <option value="HIGH">HIGH</option>
              <option value="CRITICAL">CRITICAL</option>
            </select>
          </div>
          <button className="btn btn-primary" onClick={sendAlert}>Send Test Alert</button>

          {delivery && (
            <div className="table-wrap" style={{ marginTop: '16px' }}>
              <table>
                <thead><tr><th>Channel</th><th>Status</th></tr></thead>
                <tbody>
                  <tr><td>Slack</td><td><DeliveryBadge delivered={delivery.slack} /></td></tr>
                  <tr><td>Microsoft Teams</td><td><DeliveryBadge delivered={delivery.teams} /></td></tr>
                  <tr><td>Email (SMTP)</td><td><DeliveryBadge delivered={delivery.email} /></td></tr>
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="card">
          <div className="card-title">Alert Channels for This Project</div>
          {channelAlert.show && <div className={`alert-box ${channelAlert.type}`}>{channelAlert.msg}</div>}
          <p className="form-hint" style={{ marginTop: 0 }}>
            Leave a field blank to fall back to the system-wide default configured on the server. Webhook
            URLs and the SMTP password are never shown again after saving — only whether one is set.
          </p>

          <div className="form-row">
            <label>Slack Webhook URL {effective?.slack_configured && <span className="tag" style={{ marginLeft: '6px' }}>configured</span>}</label>
            <input
              type="password"
              autoComplete="off"
              placeholder={effective?.slack_configured ? 'Leave blank to keep the stored URL' : 'https://hooks.slack.com/services/...'}
              value={channelForm.slack_webhook_url}
              onChange={e => setChannelForm({ ...channelForm, slack_webhook_url: e.target.value })}
            />
          </div>

          <div className="form-row">
            <label>Teams Webhook URL {effective?.teams_configured && <span className="tag" style={{ marginLeft: '6px' }}>configured</span>}</label>
            <input
              type="password"
              autoComplete="off"
              placeholder={effective?.teams_configured ? 'Leave blank to keep the stored URL' : 'https://outlook.office.com/webhook/...'}
              value={channelForm.teams_webhook_url}
              onChange={e => setChannelForm({ ...channelForm, teams_webhook_url: e.target.value })}
            />
          </div>

          <div className="gap-12">
            <div className="form-row" style={{ flex: 1 }}>
              <label>Alert Email From</label>
              <input type="email" value={channelForm.alert_email_from} onChange={e => setChannelForm({ ...channelForm, alert_email_from: e.target.value })} />
            </div>
            <div className="form-row" style={{ flex: 1 }}>
              <label>Alert Email To</label>
              <input type="email" value={channelForm.alert_email_to} onChange={e => setChannelForm({ ...channelForm, alert_email_to: e.target.value })} />
            </div>
          </div>

          <div className="gap-12">
            <div className="form-row" style={{ flex: 1 }}>
              <label>SMTP Host</label>
              <input type="text" value={channelForm.smtp_host} onChange={e => setChannelForm({ ...channelForm, smtp_host: e.target.value })} />
            </div>
            <div className="form-row" style={{ width: '110px' }}>
              <label>SMTP Port</label>
              <input type="number" value={channelForm.smtp_port} onChange={e => setChannelForm({ ...channelForm, smtp_port: e.target.value })} />
            </div>
          </div>

          <div className="form-row">
            <label>SMTP Username</label>
            <input type="text" value={channelForm.smtp_username} onChange={e => setChannelForm({ ...channelForm, smtp_username: e.target.value })} />
          </div>

          <div className="form-row">
            <label>SMTP Password {effective?.smtp_password_configured && !clearSmtpPassword && (
              <span className="tag" style={{ marginLeft: '6px' }}>currently set</span>
            )}</label>
            <input
              type="password"
              autoComplete="off"
              disabled={clearSmtpPassword}
              placeholder={effective?.smtp_password_configured ? 'Leave blank to keep the stored password' : ''}
              value={smtpPasswordInput}
              onChange={e => setSmtpPasswordInput(e.target.value)}
            />
            {effective?.smtp_password_configured && (
              <label style={{ display: 'block', marginTop: '6px', fontSize: '12px' }}>
                <input type="checkbox" checked={clearSmtpPassword} onChange={e => setClearSmtpPassword(e.target.checked)} style={{ marginRight: '6px' }} />
                Clear the stored SMTP password
              </label>
            )}
          </div>

          <div className="gap-8">
            <button className="btn btn-primary" disabled={channelBusy} onClick={saveChannelSettings}>Save</button>
            {effective?.has_override && (
              <button className="btn btn-danger" disabled={channelBusy} onClick={resetChannelSettings}>Reset to Default</button>
            )}
          </div>

          <p className="form-hint" style={{ marginTop: '14px' }}>
            Source: {effective ? (effective.has_override ? 'Project override' : 'System default (.env)') : '—'}
          </p>
        </div>
      </div>
    </div>
  );
}
