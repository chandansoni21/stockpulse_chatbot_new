const AUTH_EXPIRES_KEY = 'fabric-auth-expires';
const LAST_USER_EMAIL_KEY = 'fabric-last-user-email';

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

export function getLastUserEmail() {
  return localStorage.getItem(LAST_USER_EMAIL_KEY);
}

export function setLastUserEmail(email) {
  if (email) {
    localStorage.setItem(LAST_USER_EMAIL_KEY, email);
  }
}

export function clearLastUserEmail() {
  localStorage.removeItem(LAST_USER_EMAIL_KEY);
}

export function hasSwitchedMicrosoftAccount(nextEmail) {
  const previousEmail = getLastUserEmail();
  return Boolean(previousEmail && nextEmail && previousEmail !== nextEmail);
}
