const AUTH_EXPIRES_KEY = 'fabric-auth-expires';

export function setAuthExpires(expiresAt) {
  if (expiresAt) {
    localStorage.setItem(AUTH_EXPIRES_KEY, String(expiresAt));
  }
}

export function clearAuthExpires() {
  localStorage.removeItem(AUTH_EXPIRES_KEY);
}

export function isAuthExpiredLocally() {
  const raw = localStorage.getItem(AUTH_EXPIRES_KEY);
  if (!raw) return true;
  return Date.now() / 1000 > Number(raw);
}
