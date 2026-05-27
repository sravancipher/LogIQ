import React, { useState, useCallback, createContext } from 'react';
import Sidebar from './components/Sidebar.jsx';
import Topbar from './components/Topbar.jsx';
import Overview from './pages/Overview.jsx';
import NewProject from './pages/NewProject.jsx';
import LogExplorer from './pages/LogExplorer.jsx';
import AIInsights from './pages/AIInsights.jsx';
import Integrations from './pages/Integrations.jsx';
import Alerts from './pages/Alerts.jsx';
import Servers from './pages/Servers.jsx';

export const AppContext = createContext({
  apiKey: '',
  setApiKey: () => {},
  navigateTo: () => {},
});

const PAGE_TITLES = {
  'page-home':         'Overview',
  'page-onboard':      'New Project',
  'page-logs':         'Log Explorer',
  'page-insights':     'AI Insights',
  'page-integrations': 'Cloud Integrations',
  'page-alerts':       'Alerts',
  'page-servers':      'Servers',
};

export default function App() {
  const [activePage, setActivePage] = useState('page-home');
  const [apiKey, setApiKey] = useState('');

  const navigateTo = useCallback((pageId) => {
    setActivePage(pageId);
  }, []);

  return (
    <AppContext.Provider value={{ apiKey, setApiKey, navigateTo }}>
      <Sidebar activePage={activePage} navigateTo={navigateTo} />
      <div id="main">
        <Topbar title={PAGE_TITLES[activePage] || ''} />
        <div id="content">
          {activePage === 'page-home'         && <Overview />}
          {activePage === 'page-onboard'      && <NewProject />}
          {activePage === 'page-logs'         && <LogExplorer />}
          {activePage === 'page-insights'     && <AIInsights />}
          {activePage === 'page-integrations' && <Integrations />}
          {activePage === 'page-alerts'       && <Alerts />}
          {activePage === 'page-servers'      && <Servers />}
        </div>
      </div>
    </AppContext.Provider>
  );
}
