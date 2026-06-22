import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import AgentSelector from './components/AgentSelector';
import AppLogo from './components/AppLogo';
import ChatBubble from './components/ChatBubble';
import ChatInput from './components/ChatInput';
import UserProfileMenu from './components/UserProfileMenu';
import SignInModal from './components/SignInModal';
import { useSpeechToText } from './hooks/useSpeechToText';
import {
  createWelcomeMessage,
  getStoredAgentId,
  setStoredAgentId,
} from './utils/agentStorage';
import { fetchChatHistory, saveChatHistory } from './utils/chatHistoryApi';
import { fetchAgentSuggestions, fetchFollowupSuggestions } from './utils/agentSuggestionsApi';
import { getLastTwoExchanges } from './utils/suggestQuestions';
import { isFabricAccessMessage, normalizeAssistantText } from './utils/chatErrors';
import { API_URL } from './utils/apiConfig';

const REQUEST_TIMEOUT = 300;
const DEFAULT_AGENTS = [
  {
    id: 'stock-pulse',
    name: 'Stock Pulse Agent',
    description: 'SKU, stock, store inventory and barcode data',
  },
];

function App({
  authenticated = false,
  userEmail = null,
  onLogin,
  loginLoading = false,
  loginError = null,
  sessionDays = 7,
  onLogout,
  onSessionExpired,
}) {
  const initialAgentId = getStoredAgentId() || DEFAULT_AGENTS[0].id;
  const [agents, setAgents] = useState(DEFAULT_AGENTS);
  const [selectedAgentId, setSelectedAgentId] = useState(initialAgentId);
  const [messages, setMessages] = useState(() => [
    createWelcomeMessage(
      DEFAULT_AGENTS.find((agent) => agent.id === initialAgentId)?.name ?? DEFAULT_AGENTS[0].name,
    ),
  ]);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showSignInModal, setShowSignInModal] = useState(false);
  const bottomRef = useRef(null);
  const pendingSubmitRef = useRef(null);
  const chatHydratedRef = useRef(false);
  const backendSessionIdRef = useRef(null);
  const activeUserEmailRef = useRef(userEmail);

  const selectedAgent = useMemo(
    () => agents.find((agent) => agent.id === selectedAgentId),
    [agents, selectedAgentId],
  );

  const handleLogout = async () => {
    try {
      await fetch(`${API_URL}/auth/logout`, { method: 'POST' });
    } catch {
      // Still clear local session if the server is unreachable.
    }
    backendSessionIdRef.current = null;
    chatHydratedRef.current = false;
    onLogout?.();
  };

  const handleAuthFailure = useCallback(
    (response) => {
      if (response?.status === 401) {
        backendSessionIdRef.current = null;
        chatHydratedRef.current = false;
        onSessionExpired?.();
        setShowSignInModal(true);
        return true;
      }
      return false;
    },
    [onSessionExpired],
  );

  const loadHistoryForAgent = useCallback(async (agentId, agentName) => {
    try {
      const history = await fetchChatHistory(agentId);
      backendSessionIdRef.current = history.backendSessionId;
      return history.messages?.length
        ? history.messages
        : [createWelcomeMessage(agentName)];
    } catch {
      return [createWelcomeMessage(agentName)];
    }
  }, []);

  const isWelcomeOnlyChat = useCallback((messageList) => {
    return Array.isArray(messageList)
      && messageList.length === 1
      && messageList[0]?.role === 'assistant';
  }, []);

  const applyWelcomeSuggestions = useCallback(async (agentId, messageList) => {
    if (!isWelcomeOnlyChat(messageList)) return;

    setMessages((current) => {
      if (!isWelcomeOnlyChat(current)) return current;
      return [{ ...current[0], suggestions: [], suggestionsLoading: true }];
    });

    try {
      const suggestions = await fetchAgentSuggestions(agentId);
      setMessages((current) => {
        if (!isWelcomeOnlyChat(current)) return current;
        return [{
          ...current[0],
          suggestions: suggestions?.length ? suggestions : [],
          suggestionsLoading: false,
        }];
      });
    } catch {
      setMessages((current) => {
        if (!isWelcomeOnlyChat(current)) return current;
        return [{ ...current[0], suggestionsLoading: false }];
      });
    }
  }, [isWelcomeOnlyChat]);

  const loadAgents = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/agents`);
      if (handleAuthFailure(response)) return;
      if (!response.ok) throw new Error('Could not load agents.');
      const data = await response.json();
      const list = data.agents ?? [];
      setAgents(list.length ? list : DEFAULT_AGENTS);

      const storedId = getStoredAgentId();
      const initialId = list.find((agent) => agent.id === storedId)?.id ?? list[0]?.id ?? DEFAULT_AGENTS[0].id;
      if (!initialId) return;

      setSelectedAgentId(initialId);
      setStoredAgentId(initialId);

      if (!pendingSubmitRef.current) {
        const agentName = list.find((agent) => agent.id === initialId)?.name ?? DEFAULT_AGENTS[0].name;
        const restored = await loadHistoryForAgent(initialId, agentName);
        setMessages(restored);
        applyWelcomeSuggestions(initialId, restored);
      }

      chatHydratedRef.current = true;
    } catch (exception) {
      setError(exception.message || 'Failed to load agents.');
    }
  }, [applyWelcomeSuggestions, handleAuthFailure, loadHistoryForAgent]);

  useEffect(() => {
    if (!authenticated) {
      chatHydratedRef.current = false;
      backendSessionIdRef.current = null;
      activeUserEmailRef.current = null;
      const agentName = agents.find((agent) => agent.id === selectedAgentId)?.name ?? DEFAULT_AGENTS[0].name;
      setMessages([createWelcomeMessage(agentName)]);
      return;
    }

    if (activeUserEmailRef.current && userEmail && activeUserEmailRef.current !== userEmail) {
      chatHydratedRef.current = false;
      backendSessionIdRef.current = null;
      setQuestion('');
      setError(null);
      const agentName = agents.find((agent) => agent.id === selectedAgentId)?.name ?? DEFAULT_AGENTS[0].name;
      setMessages([createWelcomeMessage(agentName)]);
    }

    activeUserEmailRef.current = userEmail;
  }, [authenticated, agents, selectedAgentId, userEmail]);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading, scrollToBottom]);

  useEffect(() => {
    if (!authenticated || !chatHydratedRef.current || !selectedAgentId || !messages.length) {
      return undefined;
    }

    const timeoutId = window.setTimeout(() => {
      saveChatHistory(selectedAgentId, messages, backendSessionIdRef.current).catch(() => {
        // Ignore background save errors; the next change will retry.
      });
    }, 300);

    return () => window.clearTimeout(timeoutId);
  }, [authenticated, messages, selectedAgentId]);

  useEffect(() => {
    if (authenticated) {
      loadAgents();
    }
  }, [authenticated, loadAgents]);

  const switchAgent = useCallback(async (nextAgentId) => {
    if (!nextAgentId || nextAgentId === selectedAgentId) return;

    if (selectedAgentId && messages.length && backendSessionIdRef.current) {
      try {
        await saveChatHistory(selectedAgentId, messages, backendSessionIdRef.current);
      } catch {
        // Continue switching even if save fails.
      }
    }

    const nextAgent = agents.find((agent) => agent.id === nextAgentId);
    const agentName = nextAgent?.name ?? 'Data Agent';
    const restored = await loadHistoryForAgent(nextAgentId, agentName);

    setSelectedAgentId(nextAgentId);
    setStoredAgentId(nextAgentId);
    setQuestion('');
    setError(null);
    setMessages(restored);
    applyWelcomeSuggestions(nextAgentId, restored);
  }, [agents, applyWelcomeSuggestions, loadHistoryForAgent, messages, selectedAgentId]);

  const sendQuestion = useCallback(async (text) => {
    if (!selectedAgentId) return;

    const questionText = text?.trim();
    if (!questionText || loading) return;
    setError(null);

    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: 'user', text: questionText, animate: true },
    ]);
    setQuestion('');
    setLoading(true);

    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), (REQUEST_TIMEOUT + 30) * 1000);

    try {
      const response = await fetch(`${API_URL}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Session-Id': backendSessionIdRef.current,
        },
        body: JSON.stringify({
          question: questionText,
          agent_id: selectedAgentId,
          timeout: REQUEST_TIMEOUT,
          include_details: false,
        }),
        signal: controller.signal,
      });

      if (handleAuthFailure(response)) {
        setLoading(false);
        return;
      }
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail || 'Unable to reach the backend.');
      }

      const data = await response.json();
      const answerText = normalizeAssistantText(data.answer ?? 'No answer returned.');
      const isError = data.success === false;
      const assistantId = crypto.randomUUID();
      const assistantMessage = {
        id: assistantId,
        role: 'assistant',
        text: answerText,
        animate: true,
        typewriter: !isError,
        suggestions: [],
      };

      setMessages((current) => {
        const withAssistant = [...current, assistantMessage];

        if (!isError) {
          const exchanges = getLastTwoExchanges(withAssistant);
          fetchFollowupSuggestions(selectedAgentId, exchanges)
            .then((suggestions) => {
              if (!suggestions?.length) return;
              setMessages((latest) =>
                latest.map((message) =>
                  message.id === assistantId
                    ? { ...message, suggestions }
                    : message,
                ),
              );
            })
            .catch(() => {
              // Assistant answer still shows without follow-up chips.
            });
        }

        return withAssistant;
      });

      if (isError && !isFabricAccessMessage(answerText)) {
        setError(answerText);
      }
    } catch (exception) {
      const message =
        exception.name === 'AbortError'
          ? 'Request took too long. Try a simpler question.'
          : exception.message || 'Something went wrong.';
      setError(message);
    } finally {
      window.clearTimeout(timeoutId);
      setLoading(false);
    }
  }, [handleAuthFailure, loading, selectedAgentId]);

  useEffect(() => {
    if (!authenticated || !pendingSubmitRef.current) return;
    const pending = pendingSubmitRef.current;
    pendingSubmitRef.current = null;
    setShowSignInModal(false);
    sendQuestion(pending.text);
  }, [authenticated, sendQuestion]);

  const submitQuestion = useCallback((text = question) => {
    if (!selectedAgentId) return;

    const questionText = text?.trim();
    if (!questionText || loading) return;

    if (!authenticated) {
      pendingSubmitRef.current = { text };
      setShowSignInModal(true);
      return;
    }

    sendQuestion(text);
  }, [authenticated, loading, question, selectedAgentId, sendQuestion]);

  const handleCloseSignIn = () => {
    setShowSignInModal(false);
    pendingSubmitRef.current = null;
  };

  const startNewSession = async () => {
    if (!authenticated) {
      setShowSignInModal(true);
      return;
    }
    if (!selectedAgentId) return;
    setError(null);
    try {
      const response = await fetch(`${API_URL}/session/new`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Session-Id': backendSessionIdRef.current,
        },
        body: JSON.stringify({ agent_id: selectedAgentId }),
      });
      if (handleAuthFailure(response)) return;
      if (!response.ok) throw new Error('Could not start a new session.');
      const welcome = createWelcomeMessage(selectedAgent?.name ?? 'Data Agent');
      welcome.text = 'New conversation started.';
      welcome.animate = true;
      welcome.typewriter = true;
      setMessages([welcome]);
      applyWelcomeSuggestions(selectedAgentId, [welcome]);
      if (backendSessionIdRef.current) {
        await saveChatHistory(selectedAgentId, [welcome], backendSessionIdRef.current);
      }
    } catch (exception) {
      setError(exception.message || 'Failed to start a new session.');
    }
  };

  const handleSpeechResult = useCallback((text, speechError) => {
    if (speechError) {
      setError(speechError.message);
      return;
    }
    if (text) {
      setQuestion(text);
      submitQuestion(text);
    }
  }, [submitQuestion]);

  const { listening, supported, startListening } = useSpeechToText({
    onFinalText: handleSpeechResult,
    disabled: loading,
  });

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submitQuestion();
    }
  };

  const handleSuggestionSelect = (suggestion) => {
    submitQuestion(suggestion);
  };

  return (
    <div className="flex h-dvh flex-col bg-slate-50 text-slate-800">
      <header className="shrink-0 border-b border-slate-200 bg-white px-3 py-2 shadow-sm sm:px-4 sm:py-2.5">
        <div className="flex min-w-0 items-center gap-2 sm:gap-3">
          <div className="flex shrink-0 items-center" aria-label="Data Agent">
            <AppLogo className="h-8 w-8 sm:h-9 sm:w-9" />
          </div>

          <div className="flex min-w-0 flex-1 items-center justify-end gap-1.5 sm:gap-2">
            <AgentSelector
              agents={agents}
              value={selectedAgentId}
              onChange={switchAgent}
              disabled={loading || !agents.length}
            />
            <button
              type="button"
              onClick={startNewSession}
              disabled={!selectedAgentId || loading}
              className="shrink-0 rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-[11px] font-medium text-slate-600 shadow-sm transition hover:border-brand-500 hover:text-brand-600 disabled:opacity-50 sm:px-3 sm:py-2 sm:text-xs"
            >
              <span className="sm:hidden">New</span>
              <span className="hidden sm:inline">New chat</span>
            </button>
            {authenticated && (
              <UserProfileMenu email={userEmail} onSignOut={handleLogout} />
            )}
          </div>
        </div>
      </header>

      <main className="flex min-h-0 flex-1 flex-col">
        <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto overscroll-contain px-3 py-4 sm:gap-4 sm:px-6 sm:py-5">
          {messages.map((message) => (
            <ChatBubble
              key={message.id}
              role={message.role}
              animate={message.animate}
              typewriter={message.typewriter}
              suggestions={message.suggestions ?? []}
              suggestionsLoading={message.suggestionsLoading}
              onSuggestionSelect={handleSuggestionSelect}
              onTypingProgress={scrollToBottom}
            >
              {message.text}
            </ChatBubble>
          ))}
          {loading && (
            <div className="message-enter-assistant flex items-center gap-2 text-sm text-slate-500">
              <div className="h-2 w-2 animate-pulse rounded-full bg-brand-500" />
              Thinking...
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="shrink-0 border-t border-slate-200 bg-white px-3 py-3 pb-[max(0.75rem,var(--safe-bottom))] sm:px-6 sm:py-4">
          {error && <p className="mb-2 text-sm text-rose-600">{error}</p>}
          {listening && <p className="mb-2 text-sm text-brand-600">Listening...</p>}

          <ChatInput
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={handleKeyDown}
            onSend={() => submitQuestion()}
            onMicClick={startListening}
            listening={listening}
            loading={loading}
            micSupported={supported}
            placeholder={
              selectedAgent
                ? `Ask ${selectedAgent.name}...`
                : 'Ask a question...'
            }
          />
        </div>
      </main>

      <SignInModal
        open={showSignInModal}
        onLogin={onLogin}
        onClose={handleCloseSignIn}
        loading={loginLoading}
        error={loginError}
        sessionDays={sessionDays}
      />
    </div>
  );
}

export default App;
