import React, { useState, useContext } from 'react';
import { AppContext } from '../App.jsx';
import { apiFetch } from '../utils/api.js';

export default function NewProject() {
  const { setApiKey } = useContext(AppContext);
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');
  const [alertState, setAlertState] = useState({ show: false, msg: '', type: '' });
  const [result, setResult] = useState(null);
  const [testResult, setTestResult] = useState('');

  const showAlert = (msg, type = 'info') => setAlertState({ show: true, msg, type });
  const hideAlert = () => setAlertState({ show: false, msg: '', type: '' });

  const createProject = async () => {
    if (!name.trim()) { showAlert('Project name is required.', 'error'); return; }
    hideAlert();
    const r = await apiFetch('/api/v1/projects', {
      method: 'POST',
      body: JSON.stringify({ name: name.trim(), description: desc.trim() || null }),
    });
    if (!r.ok) { showAlert(r.body.detail || 'Failed to create project.', 'error'); return; }
    setResult({ project_id: r.body.project_id, api_key: r.body.api_key });
    showAlert('Project created successfully!', 'success');
  };

  const copyApiKey = () => {
    if (!result) return;
    navigator.clipboard.writeText(result.api_key).then(() => window.alert('API key copied!'));
  };

  const useThisKey = () => {
    if (!result) return;
    setApiKey(result.api_key);
    window.alert('Key applied to sidebar. All requests will now use it.');
  };

  const sendTestLog = async () => {
    if (!result?.api_key) { setTestResult('Create a project first.'); return; }
    const res = await fetch('/api/v1/logs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': result.api_key },
      body: JSON.stringify({
        logs: [{
          service_name: 'dashboard-test', operation: 'send_test', level: 'ERROR',
          status: 'error', message: 'Test error from dashboard onboarding',
          error_type: 'TestError', source: 'dashboard',
        }],
      }),
    });
    const b = await res.json().catch(() => ({}));
    setTestResult(res.ok ? `Accepted: ${b.accepted} log.` : `Failed: ${b.detail || 'error'}`);
  };

  return (
    <div>
      <div className="page-header"><h2>New Project</h2></div>
      <div className="grid2">
        <div>
          <div className="card">
            <div className="card-title">Project Details</div>
            {alertState.show && (
              <div className={`alert-box ${alertState.type}`}>{alertState.msg}</div>
            )}
            <div className="form-row">
              <label>Project Name *</label>
              <input type="text" placeholder="e.g. my-saas-backend" value={name} onChange={e => setName(e.target.value)} />
            </div>
            <div className="form-row">
              <label>Description</label>
              <input type="text" placeholder="Optional description" value={desc} onChange={e => setDesc(e.target.value)} />
            </div>
            <button className="btn btn-primary" onClick={createProject}>Create Project</button>
          </div>

          {result && (
            <div className="card mt-16">
              <div className="card-title">Project Created</div>
              <p style={{ fontSize: '13px', color: 'var(--text-sub)', marginBottom: '14px' }}>
                Save your API key &mdash; it is shown only once.
              </p>
              <div className="form-row">
                <label>Project ID</label>
                <input type="text" readOnly className="mono" value={result.project_id} onChange={() => {}} />
              </div>
              <div className="form-row">
                <label>API Key</label>
                <input type="text" readOnly className="mono" value={result.api_key} onChange={() => {}} />
              </div>
              <div className="gap-8 mt-16">
                <button className="btn btn-primary btn-sm" onClick={copyApiKey}>Copy API Key</button>
                <button className="btn btn-ghost btn-sm" onClick={useThisKey}>Use in sidebar</button>
              </div>
              <hr className="divider" />
              <div className="card-title">Quick Test</div>
              <p style={{ fontSize: '13px', color: 'var(--text-sub)', marginBottom: '10px' }}>
                Send a sample error log to verify ingestion.
              </p>
              <button className="btn btn-ghost btn-sm" onClick={sendTestLog}>Send Test Log</button>
              {testResult && (
                <div style={{ marginTop: '10px', fontSize: '13px', color: 'var(--green)' }}>{testResult}</div>
              )}
            </div>
          )}
        </div>

        <div className="card">
          <div className="card-title">Getting Started</div>
          <ol className="step-list">
            <li>Copy your API Key (shown once after creation)</li>
            <li>Paste it into the sidebar &mdash; all pages use it automatically</li>
            <li>Send logs via <code style={{ color: 'var(--cyan)', fontSize: '12px' }}>POST /api/v1/logs</code></li>
            <li>Connect AWS / Azure / GCP on the <strong style={{ color: 'var(--text)' }}>Integrations</strong> page</li>
            <li>View AI insights and configure Slack / Teams / email alerts</li>
          </ol>
        </div>
      </div>
    </div>
  );
}
