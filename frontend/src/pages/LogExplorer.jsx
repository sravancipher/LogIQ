import React, { useState, useCallback, useContext } from 'react';
import { AppContext } from '../App.jsx';
import { apiFetch } from '../utils/api.js';
import { tsShort, badgeLevelClass } from '../utils/helpers.js';

function BadgeLevel({ level = '' }) {
  return <span className={`badge ${badgeLevelClass(level)}`}>{level}</span>;
}

function LogTable({ items }) {
  if (!items || !items.length) return <div className="empty-state">No logs found.</div>;
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

export default function LogExplorer() {
  const { apiKey } = useContext(AppContext);
  const [level, setLevel] = useState('');
  const [service, setService] = useState('');
  const [startTime, setStartTime] = useState('');
  const [endTime, setEndTime] = useState('');
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [hasPrev, setHasPrev] = useState(false);
  const [hasNext, setHasNext] = useState(false);
  const [pageNum, setPageNum] = useState(1);
  const [cursorStack, setCursorStack] = useState([null]);
  const [currentPage, setCurrentPage] = useState(0);
  const [initialized, setInitialized] = useState(false);

  const doFetch = useCallback(async (page, stack, overrides = {}) => {
    const f = {
      level:     'level'     in overrides ? overrides.level     : level,
      service:   'service'   in overrides ? overrides.service   : service,
      startTime: 'startTime' in overrides ? overrides.startTime : startTime,
      endTime:   'endTime'   in overrides ? overrides.endTime   : endTime,
    };
    if (!apiKey) { setItems([]); setInitialized(true); return; }
    setLoading(true);
    let url = '/api/v1/logs?limit=20';
    if (f.level)          url += `&level=${encodeURIComponent(f.level)}`;
    if (f.service.trim()) url += `&service_name=${encodeURIComponent(f.service.trim())}`;
    if (f.startTime)      url += `&start_time=${encodeURIComponent(new Date(f.startTime).toISOString())}`;
    if (f.endTime)        url += `&end_time=${encodeURIComponent(new Date(f.endTime).toISOString())}`;
    const cursor = stack[page];
    if (cursor) url += `&cursor=${encodeURIComponent(cursor)}`;
    const r = await apiFetch(url, {}, apiKey);
    setLoading(false);
    setInitialized(true);
    if (!r.ok) { setItems([]); return; }
    setItems(r.body.items || []);
    const newStack = [...stack];
    if (r.body.next_cursor && newStack.length === page + 1) newStack.push(r.body.next_cursor);
    setCursorStack(newStack);
    setHasPrev(page > 0);
    setHasNext(!!r.body.next_cursor);
    setPageNum(page + 1);
    setCurrentPage(page);
  }, [apiKey, level, service, startTime, endTime]);

  const search = () => doFetch(0, [null]);

  const clear = () => {
    setLevel(''); setService(''); setStartTime(''); setEndTime('');
    doFetch(0, [null], { level: '', service: '', startTime: '', endTime: '' });
  };

  const nextPage = () => doFetch(currentPage + 1, cursorStack);
  const prevPage = () => { if (currentPage > 0) doFetch(currentPage - 1, cursorStack); };

  return (
    <div>
      <div className="page-header"><h2>Log Explorer</h2></div>
      <div className="card mb-16">
        <div className="filter-bar">
          <div className="form-row">
            <label>Level</label>
            <select value={level} onChange={e => setLevel(e.target.value)} style={{ minWidth: '110px' }}>
              <option value="">All Levels</option>
              <option value="ERROR">ERROR</option>
              <option value="WARN">WARN</option>
              <option value="INFO">INFO</option>
              <option value="DEBUG">DEBUG</option>
            </select>
          </div>
          <div className="form-row" style={{ flex: 2 }}>
            <label>Service</label>
            <input type="text" placeholder="Filter by service name" value={service} onChange={e => setService(e.target.value)} />
          </div>
          <div className="form-row">
            <label>From</label>
            <input type="datetime-local" value={startTime} onChange={e => setStartTime(e.target.value)} />
          </div>
          <div className="form-row">
            <label>To</label>
            <input type="datetime-local" value={endTime} onChange={e => setEndTime(e.target.value)} />
          </div>
          <div className="btn-group" style={{ display: 'flex', gap: '8px', alignSelf: 'flex-end' }}>
            <button className="btn btn-primary btn-sm" onClick={search}>Search</button>
            <button className="btn btn-ghost btn-sm" onClick={clear}>Clear</button>
          </div>
        </div>
      </div>
      <div className="card">
        <div className="table-wrap">
          {!initialized
            ? <div className="empty-state">Enter your API key and click Search.</div>
            : <LogTable items={items} />
          }
        </div>
        <div className="pagination">
          <button className="btn btn-ghost btn-sm" onClick={prevPage} disabled={!hasPrev}>&#9664; Prev</button>
          <span style={{ color: 'var(--muted)' }}>Page {pageNum}</span>
          <button className="btn btn-ghost btn-sm" onClick={nextPage} disabled={!hasNext}>Next &#9654;</button>
          {loading && <span><span className="spinner"></span></span>}
        </div>
      </div>
    </div>
  );
}
