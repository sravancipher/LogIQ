import React from 'react';

export default function Topbar({ title }) {
  return (
    <div id="topbar">
      <div id="topbar-title">{title}</div>
      <div id="topbar-sub">LogIQ &middot; AI-Powered Observability</div>
    </div>
  );
}
