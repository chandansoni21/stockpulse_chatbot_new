import { API_URL } from './apiConfig';

function normalizeMessages(messages) {
  if (!Array.isArray(messages)) return [];
  return messages.map((message) => ({
    ...message,
    animate: false,
    typewriter: false,
    suggestions: message.suggestions ?? [],
    suggestionsLoading: false,
  }));
}

export async function fetchChatHistory(agentId) {
  const response = await fetch(`${API_URL}/chat/history?agent_id=${encodeURIComponent(agentId)}`);
  if (!response.ok) {
    throw new Error('Could not load chat history.');
  }

  const data = await response.json();
  return {
    messages: normalizeMessages(data.messages),
    backendSessionId: data.backend_session_id,
  };
}

export async function saveChatHistory(agentId, messages, backendSessionId) {
  if (!backendSessionId) return;

  const response = await fetch(`${API_URL}/chat/history`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      agent_id: agentId,
      messages: normalizeMessages(messages),
      backend_session_id: backendSessionId,
    }),
  });

  if (!response.ok) {
    throw new Error('Could not save chat history.');
  }
}
