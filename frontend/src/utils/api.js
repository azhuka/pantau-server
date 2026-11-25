export function getAuthHeaders(extra = {}) {
  const token = localStorage.getItem('pantau_token')
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extra,
  }
}

export async function apiFetch(url, options = {}) {
  const headers = getAuthHeaders(options.headers || {})
  const res = await fetch(url, { ...options, headers })
  if (res.status === 401 && !url.includes('/api/auth/login')) {
    localStorage.removeItem('pantau_token')
  }
  return res
}
