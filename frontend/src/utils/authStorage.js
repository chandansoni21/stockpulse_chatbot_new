const AUTH_EXPIRES_KEY = 'fabric-auth-expires';

export function setAuthExpires(expiresAt) {
  if (expiresAt) {
    localStorage.setItem(AUTH_EXPIRES_KEY, String(expiresAt));
  }
}

export function clearAuthExpires() {
  localStorage.removeItem(AUTH_EXPIRES_KEY);
}

export function getAuthExpires() {
  const raw = localStorage.getItem(AUTH_EXPIRES_KEY);
  return raw ? Number(raw) : null;
}

export function isAuthExpiredLocally() {
  const expiresAt = getAuthExpires();
  if (!expiresAt) return true;
  return Date.now() / 1000 > expiresAt;
}
