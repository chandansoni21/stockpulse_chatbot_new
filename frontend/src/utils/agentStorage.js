const AGENT_KEY = 'fabric-selected-agent';

export function getStoredAgentId() {
  return sessionStorage.getItem(AGENT_KEY);
}

export function setStoredAgentId(agentId) {
  sessionStorage.setItem(AGENT_KEY, agentId);
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
