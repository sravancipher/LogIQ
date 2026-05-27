import React, { useState, useEffect, useCallback, useContext } from 'react';
import { AppContext } from '../App.jsx';
import { apiFetch } from '../utils/api.js';
import { tsShort } from '../utils/helpers.js';

const INTEGRATION_SERVICES = {
  aws: [
    { value: 'cloudwatch',   label: 'CloudWatch (Alarms / Logs)' },
    { value: 'cloudtrail',   label: 'CloudTrail' },
    { value: 'guardduty',    label: 'GuardDuty' },
    { value: 'rds',          label: 'RDS Events' },
    { value: 'lambda',       label: 'Lambda Events' },
    { value: 'security_hub', label: 'Security Hub' },
    { value: 'eventbridge',  label: 'EventBridge Events' },
  ],
  azure: [
    { value: 'azure_monitor',  label: 'Monitor Alerts (Action Group)' },
    { value: 'activity_log',   label: 'Activity Log' },
    { value: 'app_insights',   label: 'Application Insights' },
    { value: 'service_health', label: 'Service Health' },
    { value: 'defender',       label: 'Defender for Cloud' },
    { value: 'aks',            label: 'AKS Events' },
    { value: 'event_grid',     label: 'Event Grid' },
  ],
  gcp: [
    { value: 'gcp_logging',             label: 'Cloud Logging' },
    { value: 'gcp_monitoring',          label: 'Cloud Monitoring' },
    { value: 'security_command_center', label: 'Security Command Center' },
  ],
};

function IntegrationsTable({ items, onDelete }) {
  if (!items || !items.length) {
    return <div className="empty-state">No integrations yet. Connect a cloud above.</div>;
  }
  return (
    <table>
      <thead>
        <tr><th>Name</th><th>Provider</th><th>Status</th><th>Created</th><th></th></tr>
      </thead>
      <tbody>
        {items.map(item => (
          <tr key={item.id}>
            <td style={{ fontWeight: 500 }}>{item.name}</td>
            <td><span className={`tag tag-${item.provider}`}>{item.provider.toUpperCase()}</span></td>
            <td>
              {item.status === 'active'
                ? <span className="badge badge-active">active</span>
                : <span className="badge badge-inactive">inactive</span>}
            </td>
            <td style={{ fontSize: '12px', color: 'var(--muted)' }}>{tsShort(item.created_at)}</td>
            <td>
              <button className="btn btn-danger btn-sm" onClick={() => onDelete(item.id)}>Delete</button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function Integrations() {
  const { apiKey } = useContext(AppContext);
  const [intName, setIntName] = useState('');
  const [intProvider, setIntProvider] = useState('aws');
  const [intService, setIntService] = useState(INTEGRATION_SERVICES.aws[0].value);
  const [alert, setAlert] = useState({ show: false, msg: '', type: '' });
  const [createdWebhook, setCreatedWebhook] = useState(null);
  const [integrations, setIntegrations] = useState([]);

  const showAlert = (msg, type = 'info') => setAlert({ show: true, msg, type });
  const hideAlert = () => setAlert({ show: false, msg: '', type: '' });

  const handleProviderChange = (provider) => {
    setIntProvider(provider);
    const svcs = INTEGRATION_SERVICES[provider] || [];
    setIntService(svcs[0]?.value || '');
  };

  const loadIntegrations = useCallback(async () => {
    if (!apiKey) return;
    const r = await apiFetch('/api/v1/integrations', {}, apiKey);
    if (r.ok && r.body.items) setIntegrations(r.body.items);
    else setIntegrations([]);
  }, [apiKey]);

  useEffect(() => {
    loadIntegrations();
  }, [loadIntegrations]);

  const createIntegration = async () => {
    if (!intName.trim()) { showAlert('Name is required.', 'error'); return; }
    if (!apiKey) { showAlert('Enter your API key in the sidebar.', 'error'); return; }
    hideAlert();
    const r = await apiFetch('/api/v1/integrations', {
      method: 'POST',
      body: JSON.stringify({ name: intName.trim(), provider: intProvider }),
    }, apiKey);
    if (!r.ok) { showAlert(r.body.detail || 'Failed to create integration.', 'error'); return; }
    let webhookWithToken = `${r.body.webhook_url}?token=${r.body.webhook_token}`;
    if (intService) webhookWithToken += `&source=${encodeURIComponent(intService)}`;
    setCreatedWebhook({ url: webhookWithToken, token: r.body.webhook_token });
    showAlert(`Integration created for ${intProvider.toUpperCase()} / ${intService}. Configure your cloud with the webhook URL below.`, 'success');
    loadIntegrations();
  };

  const deleteIntegration = async (id) => {
    if (!window.confirm('Delete this integration? The cloud will stop sending logs.')) return;
    const r = await apiFetch(`/api/v1/integrations/${id}`, { method: 'DELETE' }, apiKey);
    if (r.ok) loadIntegrations();
  };

  const copyField = (value) => {
    navigator.clipboard.writeText(value).then(() => window.alert('Copied!'));
  };

  const services = INTEGRATION_SERVICES[intProvider] || [];

  return (
    <div>
      <div className="page-header"><h2>Cloud Integrations</h2></div>

      <div className="grid2 mb-16">
        <div className="card">
          <div className="card-title">Connect a Cloud Provider</div>
          {alert.show && <div className={`alert-box ${alert.type}`}>{alert.msg}</div>}
          <div className="form-row">
            <label>Integration Name *</label>
            <input type="text" placeholder="e.g. prod-aws-us-east-1" value={intName} onChange={e => setIntName(e.target.value)} />
          </div>
          <div className="form-row">
            <label>Cloud Provider *</label>
            <select value={intProvider} onChange={e => handleProviderChange(e.target.value)}>
              <option value="aws">AWS</option>
              <option value="azure">Azure</option>
              <option value="gcp">GCP</option>
            </select>
          </div>
          <div className="form-row">
            <label>Service *</label>
            <select value={intService} onChange={e => setIntService(e.target.value)}>
              {services.map(s => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
            <p className="form-hint">Appends a source hint to the webhook URL for accurate parser routing.</p>
          </div>
          <button className="btn btn-primary" onClick={createIntegration}>Connect</button>
        </div>

        <div className="card">
          <div className="card-title">Setup Guide</div>
          {intProvider === 'aws' && (
            <ol className="step-list">
              <li>Go to <strong style={{ color: 'var(--text)' }}>AWS SNS</strong> &rarr; Create Topic (Standard)</li>
              <li>Add an <strong style={{ color: 'var(--text)' }}>HTTP/S Subscription</strong> using the Webhook URL</li>
              <li>The platform auto-confirms the SNS subscription</li>
              <li>Route CloudWatch, CloudTrail, GuardDuty, RDS, Lambda, Security Hub, or EventBridge events through SNS to this webhook</li>
            </ol>
          )}
          {intProvider === 'azure' && (
            <ol className="step-list">
              <li>Go to <strong style={{ color: 'var(--text)' }}>Azure Monitor</strong> &rarr; Action Groups</li>
              <li>Add a <strong style={{ color: 'var(--text)' }}>Webhook</strong> action with the generated URL</li>
              <li>Attach the Action Group to Monitor Alerts, Activity Log, App Insights, Service Health, Defender, AKS, or Event Grid</li>
            </ol>
          )}
          {intProvider === 'gcp' && (
            <ol className="step-list">
              <li>Create a GCP notification channel or Pub/Sub push-to-webhook pipeline</li>
              <li>Paste the generated URL (includes token + source hint) as the push endpoint</li>
              <li>Connect Cloud Logging exports, Cloud Monitoring incidents, or Security Command Center findings</li>
            </ol>
          )}
        </div>
      </div>

      {createdWebhook && (
        <div className="card mb-16">
          <div className="card-title">Integration Created &mdash; configure your cloud with the details below</div>
          <div className="grid2 mt-16">
            <div className="form-row">
              <label>Webhook URL (paste into your cloud service)</label>
              <div className="gap-8">
                <input type="text" readOnly style={{ flex: 1, fontSize: '12px' }} className="mono" value={createdWebhook.url} onChange={() => {}} />
                <button className="btn btn-ghost btn-sm" onClick={() => copyField(createdWebhook.url)}>Copy</button>
              </div>
            </div>
            <div className="form-row">
              <label>Token (already embedded in URL above)</label>
              <input type="text" readOnly className="mono" style={{ fontSize: '12px' }} value={createdWebhook.token} onChange={() => {}} />
            </div>
          </div>
        </div>
      )}

      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
          <div className="card-title" style={{ marginBottom: 0 }}>Active Integrations</div>
          <button className="btn btn-ghost btn-sm" onClick={loadIntegrations}>&#8635; Refresh</button>
        </div>
        <div className="table-wrap">
          <IntegrationsTable items={integrations} onDelete={deleteIntegration} />
        </div>
      </div>
    </div>
  );
}
