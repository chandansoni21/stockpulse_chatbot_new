const AGENT_KEY = 'fabric-selected-agent';
const CHAT_PREFIX = 'fabric-chat';

export function getStoredAgentId() {
  return sessionStorage.getItem(AGENT_KEY);
}

export function setStoredAgentId(agentId) {
  sessionStorage.setItem(AGENT_KEY, agentId);
}

export function getChatStorageKey(sessionId, agentId) {
  return `${CHAT_PREFIX}-${sessionId}-${agentId}`;
}

export function loadAgentMessages(sessionId, agentId) {
  try {
    const raw = sessionStorage.getItem(getChatStorageKey(sessionId, agentId));
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function saveAgentMessages(sessionId, agentId, messages) {
  sessionStorage.setItem(getChatStorageKey(sessionId, agentId), JSON.stringify(messages));
}

export function createWelcomeMessage(agentName) {
  return {
    id: crypto.randomUUID(),
    role: 'assistant',
    text: `Hi! You're chatting with ${agentName}. Ask me anything about your data.`,
    animate: false,
    typewriter: false,
    suggestions: [],
  };
}
