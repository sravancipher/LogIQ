const API_BASE = import.meta.env.VITE_API_BASE || '';

export async function apiFetch(path, opts = {}, apiKey = '') {
  const headers = { 'Content-Type': 'application/json', ...opts.headers };
  if (apiKey) headers['X-API-Key'] = apiKey;
  const res = await fetch(API_BASE + path, { ...opts, headers });
  const body = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, body };
}
