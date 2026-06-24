const AUTH_SESSION_KEY = 'fabric-auth-session-id';

export function getAuthSessionId() {
  return localStorage.getItem(AUTH_SESSION_KEY);
}

export function setAuthSessionId(sessionId) {
  if (sessionId) {
    localStorage.setItem(AUTH_SESSION_KEY, sessionId);
  }
}

export function clearAuthSessionId() {
  localStorage.removeItem(AUTH_SESSION_KEY);
}

export function apiFetch(url, options = {}) {
  const sessionId = getAuthSessionId();
  const headers = new Headers(options.headers || {});
  if (sessionId) {
    headers.set('X-Auth-Session-Id', sessionId);
  }
  return fetch(url, { ...options, headers });
}
