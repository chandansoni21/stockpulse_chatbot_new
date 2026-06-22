const PKCE_VERIFIER_KEY = 'fabric-pkce-verifier';
const PKCE_STATE_KEY = 'fabric-pkce-state';

const tenantId = import.meta.env.VITE_AZURE_AUTHORITY || import.meta.env.VITE_AZURE_TENANT_ID || 'common';
const clientId = import.meta.env.VITE_AZURE_CLIENT_ID || '04b07795-8ddb-461a-bbee-02f9e1bf7b46';
const fabricScope = 'https://api.fabric.microsoft.com/.default';

export function getRedirectUri() {
  return window.location.origin;
}

function base64UrlEncode(bytes) {
  let binary = '';
  bytes.forEach((value) => {
    binary += String.fromCharCode(value);
  });
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

async function createPkcePair() {
  const random = crypto.getRandomValues(new Uint8Array(32));
  const verifier = base64UrlEncode(random);
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
  const challenge = base64UrlEncode(new Uint8Array(digest));
  return { verifier, challenge };
}

export async function startLoginRedirect() {
  const redirectUri = getRedirectUri();
  const { verifier, challenge } = await createPkcePair();
  const state = crypto.randomUUID();

  sessionStorage.setItem(PKCE_VERIFIER_KEY, verifier);
  sessionStorage.setItem(PKCE_STATE_KEY, state);

  const params = new URLSearchParams({
    client_id: clientId,
    response_type: 'code',
    redirect_uri: redirectUri,
    response_mode: 'query',
    scope: `${fabricScope} openid profile offline_access`,
    code_challenge: challenge,
    code_challenge_method: 'S256',
    state,
    prompt: 'select_account',
  });

  window.location.assign(
    `https://login.microsoftonline.com/${tenantId}/oauth2/v2.0/authorize?${params.toString()}`,
  );
}

export function readLoginCallback() {
  const params = new URLSearchParams(window.location.search);
  const error = params.get('error_description') || params.get('error');
  if (error) {
    throw new Error(decodeURIComponent(error.replace(/\+/g, ' ')));
  }

  const code = params.get('code');
  if (!code) return null;

  const state = params.get('state');
  const expectedState = sessionStorage.getItem(PKCE_STATE_KEY);
  if (!expectedState || state !== expectedState) {
    throw new Error('Sign-in state mismatch. Please try again.');
  }

  const verifier = sessionStorage.getItem(PKCE_VERIFIER_KEY);
  if (!verifier) {
    throw new Error('Sign-in verification expired. Please try again.');
  }

  sessionStorage.removeItem(PKCE_VERIFIER_KEY);
  sessionStorage.removeItem(PKCE_STATE_KEY);
  window.history.replaceState({}, document.title, window.location.pathname);

  return {
    code,
    redirectUri: getRedirectUri(),
    codeVerifier: verifier,
  };
}

export function startLogoutRedirect() {
  const redirectUri = encodeURIComponent(getRedirectUri());
  window.location.assign(
    `https://login.microsoftonline.com/${tenantId}/oauth2/v2.0/logout?post_logout_redirect_uri=${redirectUri}`,
  );
  return true;
}
