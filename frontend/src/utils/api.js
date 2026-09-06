const API_BASE = import.meta.env.VITE_API_BASE || '';

export async function apiFetch(path, opts = {}, apiKey = '') {
  const headers = { 'Content-Type': 'application/json', ...opts.headers };
  // API keys never legitimately contain whitespace - trim defensively so a stray
  // leading/trailing space or newline picked up from copy-paste doesn't silently
  // turn into a confusing "Invalid API key" (the hash comparison is exact-match).
  const trimmedKey = (apiKey || '').trim();
  if (trimmedKey) headers['X-API-Key'] = trimmedKey;
  const res = await fetch(API_BASE + path, { ...opts, headers });
  const body = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, body };
}
