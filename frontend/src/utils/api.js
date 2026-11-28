export function getAuthHeaders(extra = {}) {
  const token = localStorage.getItem('pantau_token')
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extra,
  }
}

export function extractErrorMessage(data, fallback = 'Request failed') {
  if (!data) return fallback
  const d = data.detail ?? data.error ?? data.message
  if (!d) return fallback
  if (typeof d === 'string') return d
  if (Array.isArray(d)) {
    return d.map(item => (typeof item === 'string' ? item : (item?.msg || JSON.stringify(item)))).join('; ') || fallback
  }
  if (typeof d === 'object') return d.msg || d.message || JSON.stringify(d)
  return String(d)
}

export async function apiFetch(url, options = {}) {
  const headers = getAuthHeaders(options.headers || {})
  if (typeof options.body === 'string' && !headers['Content-Type'] && !headers['content-type']) {
    headers['Content-Type'] = 'application/json'
  }
  const res = await fetch(url, { ...options, headers })
  if (res.status === 401 && !url.includes('/api/auth/login')) {
    localStorage.removeItem('pantau_token')
  }
  return res
}
