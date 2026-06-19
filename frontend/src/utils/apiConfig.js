/**
 * Resolve backend API base URL.
 * - VITE_API_URL in .env overrides everything
 * - Dev: /api (Vite proxy → localhost:8000) so mobile on same LAN works
 * - Prod: same host, port 8000
 */
export function getApiUrl() {
  const envUrl = import.meta.env.VITE_API_URL?.replace(/\/$/, '');
  if (envUrl) return envUrl;

  if (import.meta.env.DEV) {
    return '/api';
  }

  if (typeof window !== 'undefined') {
    const { protocol, hostname } = window.location;
    return `${protocol}//${hostname}:8000`;
  }

  return 'http://127.0.0.1:8000';
}

export const API_URL = getApiUrl();
