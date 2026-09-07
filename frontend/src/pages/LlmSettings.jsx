import React, { useState, useEffect, useCallback, useContext } from 'react';
import { AppContext } from '../App.jsx';
import { apiFetch } from '../utils/api.js';

const PROVIDER_INFO = {
  ollama: {
    label: 'Ollama (self-hosted)',
    baseUrlPlaceholder: 'http://localhost:11434',
    modelLabel: 'Model',
    modelPlaceholder: 'qwen3:4b-q4_K_M',
    apiKeyHint: 'Not needed for a local Ollama server.',
    showApiVersion: false,
  },
  openai_compatible: {
    label: 'OpenAI-compatible (OpenAI, self-hosted, etc.)',
    baseUrlPlaceholder: 'https://api.openai.com/v1',
    modelLabel: 'Model',
    modelPlaceholder: 'gpt-4o-mini',
    apiKeyHint: 'Your OpenAI (or compatible provider) API key.',
    showApiVersion: false,
  },
  azure_openai: {
    label: 'Azure OpenAI',
    baseUrlPlaceholder: 'https://<resource-name>.openai.azure.com',
    modelLabel: 'Deployment Name',
    modelPlaceholder: 'my-gpt4o-deployment',
    apiKeyHint: 'The API key from your Azure OpenAI resource (Keys and Endpoint page).',
    showApiVersion: true,
  },
  anthropic: {
    label: 'Anthropic (Claude)',
    baseUrlPlaceholder: 'https://api.anthropic.com',
    modelLabel: 'Model',
    modelPlaceholder: 'claude-3-5-sonnet-20241022',
    apiKeyHint: 'Your Anthropic API key (console.anthropic.com).',
    showApiVersion: false,
  },
  bedrock: {
    label: 'AWS Bedrock (Claude via Bedrock)',
    baseUrlPlaceholder: 'https://bedrock-runtime.us-east-1.amazonaws.com/anthropic',
    modelLabel: 'Model ID',
    modelPlaceholder: 'us.anthropic.claude-sonnet-5',
    apiKeyHint: 'An Amazon Bedrock API key (AWS console -> Bedrock -> API keys) - not your AWS secret access key.',
    showApiVersion: false,
  },
};

const PROVIDER_ALIASES = {
  openai: 'openai_compatible',
  'openai-compatible': 'openai_compatible',
  akash: 'openai_compatible',
  azure: 'azure_openai',
  'azure-openai': 'azure_openai',
  aws_bedrock: 'bedrock',
  'aws-bedrock': 'bedrock',
};

function normalizeProvider(provider) {
  return PROVIDER_ALIASES[provider] || provider || 'ollama';
}

const DEFAULT_FORM = {
  enabled: false,
  provider: 'ollama',
  base_url: '',
  model: '',
  temperature: 0.1,
  api_version: '',
};

export default function LlmSettings() {
  const { apiKey } = useContext(AppContext);
  const [effective, setEffective] = useState(null);
  const [form, setForm] = useState(DEFAULT_FORM);
  const [savedForm, setSavedForm] = useState(DEFAULT_FORM);
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [clearApiKey, setClearApiKey] = useState(false);
  const [alert, setAlert] = useState({ show: false, msg: '', type: '' });
  const [testResult, setTestResult] = useState(null);
  const [busy, setBusy] = useState(false);

  const info = PROVIDER_INFO[form.provider] || PROVIDER_INFO.ollama;
  const isDirty = JSON.stringify(form) !== JSON.stringify(savedForm) || apiKeyInput.trim() !== '' || clearApiKey;

  const showAlert = (msg, type = 'info') => setAlert({ show: true, msg, type });
  const hideAlert = () => setAlert({ show: false, msg: '', type: '' });

  const load = useCallback(async () => {
    if (!apiKey) return;
    const r = await apiFetch('/api/v1/llm-settings', {}, apiKey);
    if (r.ok) {
      setEffective(r.body);
      const next = {
        enabled: r.body.enabled,
        provider: normalizeProvider(r.body.provider),
        base_url: r.body.base_url || '',
        model: r.body.model || '',
        temperature: r.body.temperature ?? 0.1,
        api_version: r.body.api_version || '',
      };
      setForm(next);
      setSavedForm(next);
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
      api_version: form.api_version.trim() || null,
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
    const next = {
      enabled: r.body.enabled,
      provider: normalizeProvider(r.body.provider),
      base_url: r.body.base_url || '',
      model: r.body.model || '',
      temperature: r.body.temperature ?? 0.1,
      api_version: r.body.api_version || '',
    };
    setForm(next);
    setSavedForm(next);
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
    if (isDirty) { showAlert('You have unsaved changes — click Save first, then Test Connection.', 'error'); return; }
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
              {Object.entries(PROVIDER_INFO).map(([value, meta]) => (
                <option key={value} value={value}>{meta.label}</option>
              ))}
            </select>
          </div>

          <div className="form-row">
            <label>Base URL</label>
            <input
              type="text"
              placeholder={info.baseUrlPlaceholder}
              value={form.base_url}
              onChange={e => setForm({ ...form, base_url: e.target.value })}
            />
            <p className="form-hint">Leave blank to use the system default endpoint (only meaningful if the system default is also this same provider).</p>
          </div>

          {info.showApiVersion && (
            <div className="form-row">
              <label>API Version</label>
              <input
                type="text"
                placeholder="2024-06-01"
                value={form.api_version}
                onChange={e => setForm({ ...form, api_version: e.target.value })}
                style={{ width: '160px' }}
              />
              <p className="form-hint">The Azure OpenAI REST API version for your deployment.</p>
            </div>
          )}

          <div className="form-row">
            <label>{info.modelLabel}</label>
            <input
              type="text"
              placeholder={info.modelPlaceholder}
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
              placeholder={effective?.api_key_configured ? 'Leave blank to keep the stored key' : info.apiKeyHint}
              value={apiKeyInput}
              disabled={clearApiKey}
              autoComplete="off"
              onChange={e => setApiKeyInput(e.target.value)}
            />
            <p className="form-hint">{info.apiKeyHint}</p>
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
            <p className="form-hint">Anthropic/Bedrock models expect 0-1; OpenAI-family models allow up to 2.</p>
          </div>

          <div className="gap-8">
            <button className="btn btn-primary" disabled={busy} onClick={save}>Save</button>
            <button
              className="btn btn-ghost"
              disabled={busy}
              title={isDirty ? 'Save your changes first, then test the connection.' : undefined}
              onClick={testConnection}
            >
              Test Connection
            </button>
            {effective?.has_override && (
              <button className="btn btn-danger" disabled={busy} onClick={resetToDefault}>Reset to Default</button>
            )}
          </div>

          {isDirty && (
            <p className="form-hint" style={{ marginTop: '8px' }}>
              You have unsaved changes. Save before testing the connection.
            </p>
          )}

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
                <tr><td>Provider</td><td>{(PROVIDER_INFO[normalizeProvider(effective.provider)] || {}).label || effective.provider}</td></tr>
                <tr><td>Base URL</td><td className="mono" style={{ fontSize: '12px' }}>{effective.base_url || '(none)'}</td></tr>
                <tr><td>{(PROVIDER_INFO[normalizeProvider(effective.provider)] || {}).modelLabel || 'Model'}</td><td>{effective.model || '(none)'}</td></tr>
                {effective.api_version && <tr><td>API Version</td><td>{effective.api_version}</td></tr>}
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
