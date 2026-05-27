export function tsShort(ts) {
  if (!ts) return '\u2014';
  return new Date(ts).toLocaleString();
}

export function formatGroupLabel(group) {
  if (!group) return '\u2014';
  return `${group.service_name || 'unknown-service'} / ${group.error_type || 'UnhandledError'} / ${group.operation || 'unknown-operation'}`;
}

export function badgeLevelClass(level = '') {
  const map = { ERROR: 'badge-error', WARN: 'badge-warn', INFO: 'badge-info', DEBUG: 'badge-debug' };
  return map[level.toUpperCase()] || 'badge-info';
}
