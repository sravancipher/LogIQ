import React, { useState, useEffect, useCallback, useContext } from 'react';
import { AppContext } from '../App.jsx';
import { apiFetch } from '../utils/api.js';

const DEFAULT_FORM = {
  enabled: false,
  provider: 'ollama',
  base_url: '',
  model: '',
  temperature: 0.1,
};

export default function LlmSettings() {
  const { apiKey } = useContext(AppContext);
  const [effective, setEffective] = useState(null);
  const [form, setForm] = useState(DEFAULT_FORM);
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [clearApiKey, setClearApiKey] = useState(false);
  const [alert, setAlert] = useState({ show: false, msg: '', type: '' });
  const [testResult, setTestResult] = useState(null);
  const [busy, setBusy] = useState(false);

  const showAlert = (msg, type = 'info') => setAlert({ show: true, msg, type });
  const hideAlert = () => setAlert({ show: false, msg: '', type: '' });

  const load = useCallback(async () => {
    if (!apiKey) return;
    const r = await apiFetch('/api/v1/llm-settings', {}, apiKey);
    if (r.ok) {
      setEffective(r.body);
      setForm({
        enabled: r.body.enabled,
        provider: r.body.provider === 'openai' || r.body.provider === 'openai-compatible' || r.body.provider === 'akash'
          ? 'openai_compatible'
          : (r.body.provider || 'ollama'),
        base_url: r.body.base_url || '',
        model: r.body.model || '',
        temperature: r.body.temperature ?? 0.1,
      });
    }
  }, [apiKey]);

  useEffect(() => {
    load();
  }, [load]);

  const save = async () => {
    if (!apiKey) { showAlert('Enter your API key in the sidebar.', 'error'); return; }
    hideAlert();
    setTestResult(null);
    setBusy(true);
    const body = {
      enabled: form.enabled,
      provider: form.provider,
      base_url: form.base_url.trim() || null,
      model: form.model.trim() || null,
      temperature: form.temperature === '' ? null : Number(form.temperature),
    };
    if (clearApiKey) {
      body.api_key = '';
    } else if (apiKeyInput.trim()) {
      body.api_key = apiKeyInput.trim();
    }
    const r = await apiFetch('/api/v1/llm-settings', { method: 'PUT', body: JSON.stringify(body) }, apiKey);
    setBusy(false);
    if (!r.ok) { showAlert(r.body.detail || 'Failed to save LLM settings.', 'error'); return; }
    setEffective(r.body);
    setApiKeyInput('');
    setClearApiKey(false);
    showAlert('Saved. This project will use this configuration for AI Insights.', 'success');
  };

  const resetToDefault = async () => {
    if (!apiKey) return;
    if (!window.confirm('Remove this project\'s custom LLM configuration and revert to the system default?')) return;
    hideAlert();
    setTestResult(null);
    const r = await apiFetch('/api/v1/llm-settings', { method: 'DELETE' }, apiKey);
    if (r.ok || r.status === 204) {
      showAlert('Reverted to the system default LLM configuration.', 'success');
      load();
    }
  };

  const testConnection = async () => {
    if (!apiKey) { showAlert('Enter your API key in the sidebar.', 'error'); return; }
    setTestResult(null);
    setBusy(true);
    const r = await apiFetch('/api/v1/llm-settings/test', { method: 'POST' }, apiKey);
    setBusy(false);
    if (!r.ok) { setTestResult({ success: false, message: r.body.detail || 'Test request failed.' }); return; }
    setTestResult(r.body);
  };

  return (
    <div>
      <div className="page-header"><h2>AI Configuration</h2></div>

      <div className="grid2 mb-16">
        <div className="card">
          <div className="card-title">LLM Provider for This Project</div>
          {alert.show && <div className={`alert-box ${alert.type}`}>{alert.msg}</div>}
          <p className="form-hint" style={{ marginTop: 0 }}>
            Choose which LLM AI Insights uses to analyze this project's logs. Leave everything below
            untouched to keep using the system default. Log content is sent to whichever endpoint you configure here.
          </p>

          <div className="form-row">
            <label>
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={e => setForm({ ...form, enabled: e.target.checked })}
                style={{ marginRight: '8px' }}
              />
              Enable AI-powered analysis for this project
            </label>
          </div>

          <div className="form-row">
            <label>Provider</label>
            <select value={form.provider} onChange={e => setForm({ ...form, provider: e.target.value })}>
              <option value="ollama">Ollama (self-hosted)</option>
              <option value="openai_compatible">OpenAI-compatible (hosted / cloud)</option>
            </select>
          </div>

          <div className="form-row">
            <label>Base URL</label>
            <input
              type="text"
              placeholder="e.g. http://localhost:11434 or https://api.your-provider.com/v1"
              value={form.base_url}
              onChange={e => setForm({ ...form, base_url: e.target.value })}
            />
            <p className="form-hint">Leave blank to use the system default endpoint.</p>
          </div>

          <div className="form-row">
            <label>Model</label>
            <input
              type="text"
              placeholder="e.g. qwen3:4b-q4_K_M or gpt-4o-mini"
              value={form.model}
              onChange={e => setForm({ ...form, model: e.target.value })}
            />
          </div>

          <div className="form-row">
            <label>API Key {effective?.api_key_configured && !clearApiKey && (
              <span className="tag" style={{ marginLeft: '6px' }}>currently set</span>
            )}</label>
            <input
              type="password"
              placeholder={effective?.api_key_configured ? 'Leave blank to keep the stored key' : 'Only needed for hosted/cloud providers'}
              value={apiKeyInput}
              disabled={clearApiKey}
              autoComplete="off"
              onChange={e => setApiKeyInput(e.target.value)}
            />
            {effective?.api_key_configured && (
              <label style={{ display: 'block', marginTop: '6px', fontSize: '12px' }}>
                <input
                  type="checkbox"
                  checked={clearApiKey}
                  onChange={e => setClearApiKey(e.target.checked)}
                  style={{ marginRight: '6px' }}
                />
                Clear the stored API key
              </label>
            )}
          </div>

          <div className="form-row">
            <label>Temperature</label>
            <input
              type="number"
              min="0"
              max="2"
              step="0.1"
              value={form.temperature}
              onChange={e => setForm({ ...form, temperature: e.target.value })}
              style={{ width: '100px' }}
            />
          </div>

          <div className="gap-8">
            <button className="btn btn-primary" disabled={busy} onClick={save}>Save</button>
            <button className="btn btn-ghost" disabled={busy} onClick={testConnection}>Test Connection</button>
            {effective?.has_override && (
              <button className="btn btn-danger" disabled={busy} onClick={resetToDefault}>Reset to Default</button>
            )}
          </div>

          {testResult && (
            <div className={`alert-box ${testResult.success ? 'success' : 'error'}`} style={{ marginTop: '12px' }}>
              {testResult.message}
            </div>
          )}
        </div>

        <div className="card">
          <div className="card-title">Currently Active Configuration</div>
          {effective ? (
            <table>
              <tbody>
                <tr><td>Source</td><td>{effective.has_override ? 'Project override' : 'System default'}</td></tr>
                <tr><td>Enabled</td><td>{effective.enabled ? 'Yes' : 'No'}</td></tr>
                <tr><td>Provider</td><td>{effective.provider}</td></tr>
                <tr><td>Base URL</td><td className="mono" style={{ fontSize: '12px' }}>{effective.base_url}</td></tr>
                <tr><td>Model</td><td>{effective.model}</td></tr>
                <tr><td>API Key</td><td>{effective.api_key_configured ? 'Configured' : 'Not set'}</td></tr>
                <tr><td>Temperature</td><td>{effective.temperature}</td></tr>
              </tbody>
            </table>
          ) : (
            <div className="empty-state">Enter your API key in the sidebar to view the current configuration.</div>
          )}
          <p className="form-hint">
            Raw log content (messages, service names, error types) is sent to this endpoint when AI
            Insights runs. Only point this at an LLM provider you trust with that data.
          </p>
        </div>
      </div>
    </div>
  );
}
