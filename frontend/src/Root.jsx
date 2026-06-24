import { useCallback, useEffect, useState } from 'react';
import App from './App';
import {
  clearAuthExpires,
  hasSwitchedMicrosoftAccount,
  setAuthExpires,
  setLastUserEmail,
} from './utils/authStorage';
import { setStoredAgentId } from './utils/agentStorage';
import { API_URL } from './utils/apiConfig';
import {
  apiFetch,
  clearAuthSessionId,
  setAuthSessionId,
} from './utils/apiFetch';
import {
  readLoginCallback,
  startLoginRedirect,
  startLogoutRedirect,
} from './utils/microsoftAuth';

async function postCodeLogin(callback) {
  const response = await apiFetch(`${API_URL}/auth/login/code`, {
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
    if (data?.session_id) setAuthSessionId(data.session_id);
    if (data?.authenticated) {
      if (hasSwitchedMicrosoftAccount(data.user_email)) {
        setStoredAgentId(null);
      }
      setAuthExpires(data.expires_at);
      setLastUserEmail(data.user_email);
      setAuthenticated(true);
      setUserEmail(data.user_email || null);
      setLoginError(null);
    } else {
      clearAuthExpires();
      clearAuthSessionId();
      setAuthenticated(false);
      setUserEmail(null);
    }
  }, []);

  const checkAuth = useCallback(async () => {
    const response = await apiFetch(`${API_URL}/auth/status`);
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
        clearAuthExpires();
        clearAuthSessionId();
        setAuthenticated(false);
        setUserEmail(null);
        setLoginError(exception.message || 'Microsoft login failed.');
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

  useEffect(() => {
    if (!authenticated) return undefined;

    const refreshAuth = () => {
      checkAuth().catch(() => {});
    };

    const interval = window.setInterval(refreshAuth, 45 * 60 * 1000);
    const onVisible = () => {
      if (document.visibilityState === 'visible') {
        refreshAuth();
      }
    };
    document.addEventListener('visibilitychange', onVisible);

    return () => {
      window.clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [authenticated, checkAuth]);

  const handleLogin = async () => {
    setLoginLoading(true);
    setLoginError(null);
    clearAuthSessionId();
    try {
      await startLoginRedirect();
    } catch (exception) {
      setLoginError(exception.message || 'Microsoft login failed.');
      setLoginLoading(false);
    }
  };

  const handleLogout = useCallback(async () => {
    try {
      await apiFetch(`${API_URL}/auth/logout`, { method: 'POST' });
    } catch {
      // Ignore network errors during logout.
    }
    clearAuthExpires();
    clearAuthSessionId();
    setAuthenticated(false);
    setUserEmail(null);
    setLoginError(null);
    startLogoutRedirect();
  }, []);

  const handleSessionExpired = useCallback(() => {
    clearAuthExpires();
    clearAuthSessionId();
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
