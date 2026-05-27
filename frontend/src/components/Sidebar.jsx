import React, { useContext } from 'react';
import { AppContext } from '../App.jsx';

const NAV_ITEMS = [
  { id: 'page-home',         icon: '\u25C9', label: 'Overview' },
  { id: 'page-onboard',      icon: '\u2726', label: 'New Project' },
  { id: 'page-servers',      icon: '\u25A3', label: 'Servers' },
  { id: 'page-logs',         icon: '\u2261', label: 'Log Explorer' },
  { id: 'page-insights',     icon: '\u2908', label: 'AI Insights' },
  { id: 'page-integrations', icon: '\u2B21', label: 'Integrations' },
  { id: 'page-alerts',       icon: '\u25CE', label: 'Alerts' },
];

export default function Sidebar({ activePage, navigateTo }) {
  const { apiKey, setApiKey } = useContext(AppContext);

  return (
    <aside id="sidebar">
      <div className="sidebar-logo">
        <img src="/dashboard/assets/project_logo_bg.png" alt="LogIQ" style={{ height: 40, width: 'auto' }} />
      </div>
      <div className="nav-section">Navigation</div>
      <nav>
        {NAV_ITEMS.map(item => (
          <a
            key={item.id}
            href="#"
            className={activePage === item.id ? 'active' : ''}
            onClick={(e) => { e.preventDefault(); navigateTo(item.id); }}
          >
            <i className="nav-icon">{item.icon}</i>{' '}{item.label}
          </a>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <div className="api-key-box">
          <label>
            <span className={`conn-dot${apiKey ? ' live' : ''}`}></span>{' '}API Key
          </label>
          <input
            type="password"
            placeholder="Paste pm_... key"
            autoComplete="off"
            spellCheck={false}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
          />
        </div>
      </div>
    </aside>
  );
}
