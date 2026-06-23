const AGENT_KEY = 'fabric-selected-agent';

export function getStoredAgentId() {
  return sessionStorage.getItem(AGENT_KEY);
}

export function setStoredAgentId(agentId) {
  if (agentId) {
    sessionStorage.setItem(AGENT_KEY, agentId);
  } else {
    sessionStorage.removeItem(AGENT_KEY);
  }
}

export function createWelcomeMessage(agentName, { suggestionsLoading = false } = {}) {
  return {
    id: crypto.randomUUID(),
    role: 'assistant',
    isWelcome: true,
    text: `Hi! You're chatting with ${agentName}. Ask me anything about your data.`,
    animate: false,
    typewriter: false,
    suggestions: [],
    suggestionsLoading,
  };
}
