import { useCallback, useEffect, useState } from 'react';
import App from './App';
import {
  clearAuthExpires,
  isAuthExpiredLocally,
  setAuthExpires,
} from './utils/authStorage';
import { API_URL } from './utils/apiConfig';
import {
  readLoginCallback,
  startLoginRedirect,
  startLogoutRedirect,
} from './utils/microsoftAuth';

async function postCodeLogin(callback) {
  const response = await fetch(`${API_URL}/auth/login/code`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      code: callback.code,
      redirect_uri: callback.redirectUri,
      code_verifier: callback.codeVerifier,
    }),
  });

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(data?.detail || 'Microsoft login failed.');
  }
  return data;
}

function Root() {
  const [authChecked, setAuthChecked] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [userEmail, setUserEmail] = useState(null);
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginError, setLoginError] = useState(null);
  const [sessionDays, setSessionDays] = useState(7);

  const applyAuthStatus = useCallback((data) => {
    if (data?.session_days) setSessionDays(data.session_days);
    if (data?.authenticated) {
      setAuthExpires(data.expires_at);
      setAuthenticated(true);
      setUserEmail(data.user_email || null);
      setLoginError(null);
    } else {
      clearAuthExpires();
      setAuthenticated(false);
      setUserEmail(null);
    }
  }, []);

  const checkAuth = useCallback(async () => {
    const response = await fetch(`${API_URL}/auth/status`);
    if (!response.ok) throw new Error('Could not verify login status.');
    const data = await response.json();
    applyAuthStatus(data);
    return data;
  }, [applyAuthStatus]);

  useEffect(() => {
    let active = true;

    (async () => {
      try {
        const callback = readLoginCallback();
        const data = callback ? await postCodeLogin(callback) : await checkAuth();
        if (active && data) {
          applyAuthStatus(data);
        }
      } catch (exception) {
        if (!active) return;
        setLoginError(exception.message || 'Microsoft login failed.');
        if (!isAuthExpiredLocally()) {
          setAuthenticated(true);
        } else {
          setAuthenticated(false);
        }
      } finally {
        if (active) {
          setAuthChecked(true);
        }
      }
    })();

    return () => {
      active = false;
    };
  }, [applyAuthStatus, checkAuth]);

  const handleLogin = async () => {
    setLoginLoading(true);
    setLoginError(null);
    try {
      await startLoginRedirect();
    } catch (exception) {
      setLoginError(exception.message || 'Microsoft login failed.');
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
    setUserEmail(null);
    setLoginError(null);
    startLogoutRedirect();
  }, []);

  const handleSessionExpired = useCallback(() => {
    clearAuthExpires();
    setAuthenticated(false);
    setUserEmail(null);
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
      userEmail={userEmail}
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
