import { useCallback, useEffect, useState } from 'react';
import App from './App';
import { clearAuthExpires, isAuthExpiredLocally, setAuthExpires } from './utils/authStorage';
import { API_URL } from './utils/apiConfig';

function Root() {
  const [authChecked, setAuthChecked] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginError, setLoginError] = useState(null);
  const [sessionDays, setSessionDays] = useState(7);

  const applyAuthStatus = useCallback((data) => {
    if (data?.session_days) setSessionDays(data.session_days);
    if (data?.authenticated) {
      setAuthExpires(data.expires_at);
      setAuthenticated(true);
      setLoginError(null);
    } else {
      clearAuthExpires();
      setAuthenticated(false);
    }
  }, []);

  const checkAuth = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/auth/status`);
      if (!response.ok) throw new Error('Could not verify login status.');
      const data = await response.json();
      applyAuthStatus(data);
    } catch {
      if (!isAuthExpiredLocally()) {
        setAuthenticated(true);
      } else {
        setAuthenticated(false);
      }
    } finally {
      setAuthChecked(true);
    }
  }, [applyAuthStatus]);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  const handleLogin = async () => {
    setLoginLoading(true);
    setLoginError(null);
    try {
      const controller = new AbortController();
      const timeoutId = window.setTimeout(() => controller.abort(), 5 * 60 * 1000);

      const response = await fetch(`${API_URL}/auth/login`, {
        method: 'POST',
        signal: controller.signal,
      });
      window.clearTimeout(timeoutId);

      const data = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(data?.detail || 'Microsoft login failed.');
      }
      applyAuthStatus(data);
    } catch (exception) {
      const message =
        exception.name === 'AbortError'
          ? 'Login took too long. Complete sign-in on the server PC and try again.'
          : exception.message || 'Microsoft login failed.';
      setLoginError(
        message === 'Failed to fetch'
          ? 'Cannot reach the server. Use the same Wi‑Fi and open the app via your PC IP (not localhost).'
          : message,
      );
    } finally {
      setLoginLoading(false);
    }
  };

  const handleLogout = useCallback(async () => {
    try {
      await fetch(`${API_URL}/auth/logout`, { method: 'POST' });
    } catch {
      // Ignore network errors during logout.
    }
    clearAuthExpires();
    setAuthenticated(false);
    setLoginError(null);
  }, []);

  const handleSessionExpired = useCallback(() => {
    clearAuthExpires();
    setAuthenticated(false);
    setLoginError(null);
  }, []);

  if (!authChecked) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-slate-50 text-slate-400">
        <div className="h-2 w-2 animate-pulse rounded-full bg-brand-500" />
      </div>
    );
  }

  return (
    <App
      authenticated={authenticated}
      onLogin={handleLogin}
      loginLoading={loginLoading}
      loginError={loginError}
      sessionDays={sessionDays}
      onLogout={handleLogout}
      onSessionExpired={handleSessionExpired}
    />
  );
}

export default Root;
