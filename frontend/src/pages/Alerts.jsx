import React, { useState, useContext } from 'react';
import { AppContext } from '../App.jsx';
import { apiFetch } from '../utils/api.js';

export default function Alerts() {
  const { apiKey } = useContext(AppContext);
  const [title, setTitle] = useState('Test Alert from Dashboard');
  const [message, setMessage] = useState('Manually triggered test alert to verify channel delivery.');
  const [severity, setSeverity] = useState('MEDIUM');
  const [emailTo, setEmailTo] = useState('');
  const [alert, setAlert] = useState({ show: false, msg: '', type: '' });
  const [delivery, setDelivery] = useState(null);

  const showAlert = (msg, type = 'info') => setAlert({ show: true, msg, type });
  const hideAlert = () => setAlert({ show: false, msg: '', type: '' });

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
    showAlert('Alert sent. See delivery results.', 'success');
  };

  const DeliveryBadge = ({ delivered }) =>
    delivered
      ? <span className="badge badge-active">Delivered</span>
      : <span className="badge badge-inactive">Not configured</span>;

  return (
    <div>
      <div className="page-header"><h2>Alerts</h2></div>
      <div className="grid2">
        <div className="card">
          <div className="card-title">Send a Test Alert</div>
          <p style={{ fontSize: '13px', color: 'var(--text-sub)', marginBottom: '16px' }}>
            Verify your Slack / Teams / email settings. Configure webhook URLs and SMTP in your{' '}
            <code style={{ color: 'var(--cyan)' }}>.env</code> file.
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
        </div>

        <div>
          {delivery && (
            <div className="card mb-16">
              <div className="card-title">Delivery Results</div>
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
          <div className="card">
            <div className="card-title">Configure in .env</div>
            <pre className="code-box">{`SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
TEAMS_WEBHOOK_URL=https://outlook.office.com/webhook/...
ALERT_EMAIL_FROM=alerts@yourcompany.com
ALERT_EMAIL_TO=oncall@yourcompany.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=...
SMTP_PASSWORD=...`}</pre>
          </div>
        </div>
      </div>
    </div>
  );
}
