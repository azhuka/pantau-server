/**
 * API Client untuk Pantau Server
 * Mengelola CSRF, credentials, dan error handling terstandarisasi.
 */

function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(';').shift();
  return '';
}

export async function request(url, options = {}) {
  const csrfToken = getCookie('pantau_csrf_token');
  const headers = {
    'Accept': 'application/json',
    ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
    ...(options.headers || {}),
  };

  if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(options.body);
  }

  const response = await fetch(url, {
    credentials: 'same-origin',
    ...options,
    headers,
  });

  if (response.status === 401) {
    if (window.location.pathname !== '/login') {
      window.location.href = '/login';
    }
    throw new Error('Sesi berakhir, silakan login kembali.');
  }

  if (!response.ok) {
    let errMsg = `HTTP Error ${response.status}`;
    try {
      const errData = await response.json();
      errMsg = errData.detail || errData.message || errMsg;
    } catch (e) {
      // fallback text
    }
    throw new Error(errMsg);
  }

  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    return await response.json();
  }
  return await response.text();
}

export const api = {
  get: (url) => request(url, { method: 'GET' }),
  post: (url, body) => request(url, { method: 'POST', body }),
  put: (url, body) => request(url, { method: 'PUT', body }),
  delete: (url) => request(url, { method: 'DELETE' }),
};
