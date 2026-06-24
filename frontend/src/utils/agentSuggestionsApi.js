import { API_URL } from './apiConfig';
import { apiFetch } from './apiFetch';

export async function fetchAgentSuggestions(agentId, { forceRefresh = false, timeout = 120 } = {}) {
  const params = new URLSearchParams();
  if (forceRefresh) params.set('force_refresh', 'true');
  if (timeout) params.set('timeout', String(timeout));

  const query = params.toString();
  const url = `${API_URL}/agents/${encodeURIComponent(agentId)}/suggestions${query ? `?${query}` : ''}`;

  const response = await apiFetch(url);
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail || 'Could not load suggested questions.');
  }

  const data = await response.json();
  return data.suggestions ?? [];
}

export async function fetchFollowupSuggestions(agentId, exchanges, { timeout = 90 } = {}) {
  const response = await apiFetch(
    `${API_URL}/agents/${encodeURIComponent(agentId)}/suggestions/followup`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ exchanges, timeout }),
    },
  );

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail || 'Could not load follow-up questions.');
  }

  const data = await response.json();
  return data.suggestions ?? [];
}
