import React, { useContext, useEffect, useRef, useState } from 'react';
import { AppContext } from '../App.jsx';
import { apiFetch } from '../utils/api.js';

const CONFIDENCE_LABEL = { high: 'High confidence', medium: 'Medium confidence', low: 'Low confidence' };

function ToolTrace({ toolCalls }) {
  if (!Array.isArray(toolCalls) || toolCalls.length === 0) return null;
  return (
    <details className="chat-trace">
      <summary>Investigation steps ({toolCalls.length})</summary>
      {toolCalls.map((call, i) => (
        <div key={i} className="chat-trace-step">
          <span className="tag">{call.tool}</span>{' '}
          {Object.keys(call.arguments || {}).length > 0 && (
            <span className="mono" style={{ color: 'var(--muted)' }}>
              {JSON.stringify(call.arguments)}
            </span>
          )}
        </div>
      ))}
    </details>
  );
}

function AssistantBubble({ msg }) {
  const unavailable = msg.analysisMode === 'unavailable';
  return (
    <div className={`chat-bubble assistant${unavailable ? ' unavailable' : ''}`}>
      <div>{msg.text}</div>

      {Array.isArray(msg.evidence) && msg.evidence.length > 0 && (
        <ul className="chat-evidence">
          {msg.evidence.map((e, i) => (
            <li key={i}>
              {e.description}
              {e.log_id != null && <span className="tag" style={{ marginLeft: '6px' }}>log #{e.log_id}</span>}
            </li>
          ))}
        </ul>
      )}

      <ToolTrace toolCalls={msg.toolCalls} />

      {!unavailable && (
        <div className="chat-meta">
          <span className="badge badge-info">{CONFIDENCE_LABEL[msg.confidence] || 'Confidence unknown'}</span>
          {msg.modelName && <span className="tag">{msg.modelName}</span>}
        </div>
      )}
    </div>
  );
}

export default function Chat() {
  const { apiKey } = useContext(AppContext);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [lookback, setLookback] = useState('1440');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const threadRef = useRef(null);

  useEffect(() => {
    if (threadRef.current) threadRef.current.scrollTop = threadRef.current.scrollHeight;
  }, [messages, loading]);

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || loading) return;
    if (!apiKey) {
      setError('Enter your API key in the sidebar to use the assistant.');
      return;
    }

    setError('');
    setMessages(prev => [...prev, { role: 'user', text }]);
    setInput('');
    setLoading(true);

    const r = await apiFetch('/api/v1/chat', {
      method: 'POST',
      body: JSON.stringify({ message: text, lookback_minutes: Number(lookback) }),
    }, apiKey);

    setLoading(false);

    if (!r.ok) {
      setMessages(prev => [
        ...prev,
        { role: 'assistant', text: r.body.detail || 'Something went wrong reaching the assistant.', analysisMode: 'unavailable' },
      ]);
      return;
    }

    setMessages(prev => [
      ...prev,
      {
        role: 'assistant',
        text: r.body.answer,
        evidence: r.body.evidence || [],
        toolCalls: r.body.tool_calls || [],
        confidence: r.body.confidence,
        analysisMode: r.body.analysis_mode,
        modelName: r.body.model_name,
      },
    ]);
  };

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div>
      <div className="page-header"><h2>AI Assistant</h2></div>

      <div className="card mb-16">
        <div className="form-row" style={{ marginBottom: 0, maxWidth: '260px' }}>
          <label>Default lookback (used when your question doesn't name a time range)</label>
          <select value={lookback} onChange={e => setLookback(e.target.value)}>
            <option value="60">Last 1 hour</option>
            <option value="360">Last 6 hours</option>
            <option value="1440">Last 24 hours</option>
            <option value="10080">Last 7 days</option>
            <option value="43200">Last 30 days</option>
          </select>
        </div>
      </div>

      <div className="card chat-card">
        <div className="chat-thread" ref={threadRef}>
          {messages.length === 0 && !loading && (
            <div className="empty-state">
              Ask about your logs, e.g. "Why did payment-service fail in the last hour?" or "What's the top error today?"
            </div>
          )}
          {messages.map((msg, i) => (
            msg.role === 'user'
              ? <div key={i} className="chat-bubble user">{msg.text}</div>
              : <AssistantBubble key={i} msg={msg} />
          ))}
          {loading && (
            <div className="chat-bubble assistant">
              <span className="spinner"></span>{' '}Investigating...
            </div>
          )}
        </div>

        {error && <div className="alert-box error">{error}</div>}

        <div className="chat-input-bar">
          <textarea
            rows={2}
            placeholder="Ask about your logs..."
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={onKeyDown}
          />
          <button className="btn btn-primary" onClick={sendMessage} disabled={loading}>Send</button>
        </div>
      </div>
    </div>
  );
}
