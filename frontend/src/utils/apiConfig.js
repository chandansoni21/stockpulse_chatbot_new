/**
 * Resolve backend API base URL.
 * - VITE_API_URL in .env / Vercel env overrides everything (required for production chat)
 * - Dev: /api (Vite proxy -> localhost:8000)
 * - Prod fallback: /api (Vercel serverless proxy -> BACKEND_URL)
 */
export function getApiUrl() {
  const envUrl = import.meta.env.VITE_API_URL?.replace(/\/$/, '');
  if (envUrl) return envUrl;

  if (import.meta.env.DEV) {
    return '/api';
  }

  return '/api';
}

export const API_URL = getApiUrl();
