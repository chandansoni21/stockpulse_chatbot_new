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
import { finalizePausedMessages, isWelcomeOnlyChat } from './utils/chatMessages';
import { getLastTwoExchanges } from './utils/suggestQuestions';
import { isFabricAccessMessage, normalizeAssistantText } from './utils/chatErrors';
import { API_URL } from './utils/apiConfig';
import WelcomeScreen from './components/WelcomeScreen';

const REQUEST_TIMEOUT = 300;
const DEFAULT_AGENTS = [
  {
    id: 'stock-pulse',
    name: 'Stock Pulse Agent',
    description: 'SKU, stock, store inventory and barcode data',
  },
  {
    id: 'br',
    name: 'Billing Agent',
    description: 'Billing and business reporting data',
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
  const [agentSwitching, setAgentSwitching] = useState(false);
  const [error, setError] = useState(null);
  const [showSignInModal, setShowSignInModal] = useState(false);
  const bottomRef = useRef(null);
  const chatScrollRef = useRef(null);
  const pendingSubmitRef = useRef(null);
  const chatHydratedRef = useRef(false);
  const backendSessionIdRef = useRef(null);
  const activeUserEmailRef = useRef(userEmail);
  const historyCacheRef = useRef({});
  const switchGenerationRef = useRef(0);
  const messagesRef = useRef(messages);
  const activeChatRef = useRef({
    generation: 0,
    controller: null,
    timeoutId: null,
    userCancelled: false,
    pendingQuestion: null,
    agentId: null,
  });

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  const abortActiveChatRequest = useCallback(() => {
    const active = activeChatRef.current;
    active.generation += 1;
    active.userCancelled = true;

    if (active.timeoutId) {
      window.clearTimeout(active.timeoutId);
      active.timeoutId = null;
    }
    if (active.controller) {
      active.controller.abort();
      active.controller = null;
    }

    active.pendingQuestion = null;
    active.agentId = null;
    setLoading(false);
  }, []);

  const pauseActiveChatRequest = useCallback(({ agentId = selectedAgentId, persist = true } = {}) => {
    const active = activeChatRef.current;
    const questionText = active.pendingQuestion;
    const targetAgentId = agentId || active.agentId || selectedAgentId;

    active.generation += 1;
    active.userCancelled = true;

    if (active.timeoutId) {
      window.clearTimeout(active.timeoutId);
      active.timeoutId = null;
    }
    if (active.controller) {
      active.controller.abort();
      active.controller = null;
    }

    active.pendingQuestion = null;
    active.agentId = null;
    setLoading(false);

    if (!persist || !questionText || !targetAgentId) return null;

    const source = historyCacheRef.current[targetAgentId] ?? messagesRef.current;
    const updated = finalizePausedMessages(source, questionText);
    if (updated === source) return updated;

    historyCacheRef.current[targetAgentId] = updated;
    if (targetAgentId === selectedAgentId) {
      setMessages(updated);
    }

    const sessionId = backendSessionIdRef.current;
    if (sessionId) {
      saveChatHistory(targetAgentId, updated, sessionId).catch(() => {});
    }

    return updated;
  }, [selectedAgentId]);

  const selectedAgent = useMemo(
    () => agents.find((agent) => agent.id === selectedAgentId),
    [agents, selectedAgentId],
  );

  const handleLogout = async () => {
    pauseActiveChatRequest();
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

  const loadHistoryForAgent = useCallback(async (agentId, agentName, { useCache = true } = {}) => {
    if (useCache && historyCacheRef.current[agentId]?.length) {
      return historyCacheRef.current[agentId];
    }

    try {
      const history = await fetchChatHistory(agentId);
      backendSessionIdRef.current = history.backendSessionId;
      const restored = history.messages?.length
        ? history.messages
        : [createWelcomeMessage(agentName)];
      historyCacheRef.current[agentId] = restored;
      return restored;
    } catch {
      const fallback = [createWelcomeMessage(agentName)];
      return fallback;
    }
  }, []);

  const isWelcomeChat = useCallback((messageList) => isWelcomeOnlyChat(messageList), []);

  const applyWelcomeSuggestions = useCallback(async (agentId, messageList) => {
    if (!isWelcomeChat(messageList)) return;

    setMessages((current) => {
      if (!isWelcomeChat(current)) return current;
      return [{ ...current[0], suggestions: [], suggestionsLoading: true }];
    });

    try {
      const suggestions = await fetchAgentSuggestions(agentId);
      setMessages((current) => {
        if (!isWelcomeChat(current)) return current;
        return [{
          ...current[0],
          suggestions: suggestions?.length ? suggestions : [],
          suggestionsLoading: false,
        }];
      });
    } catch {
      setMessages((current) => {
        if (!isWelcomeChat(current)) return current;
        return [{ ...current[0], suggestionsLoading: false }];
      });
    }
  }, [isWelcomeChat]);

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
      pauseActiveChatRequest({ persist: false });
      chatHydratedRef.current = false;
      backendSessionIdRef.current = null;
      activeUserEmailRef.current = null;
      const agentName = agents.find((agent) => agent.id === selectedAgentId)?.name ?? DEFAULT_AGENTS[0].name;
      setMessages([createWelcomeMessage(agentName)]);
      return;
    }

    if (activeUserEmailRef.current && userEmail && activeUserEmailRef.current !== userEmail) {
      pauseActiveChatRequest();
      chatHydratedRef.current = false;
      backendSessionIdRef.current = null;
      setQuestion('');
      setError(null);
      const agentName = agents.find((agent) => agent.id === selectedAgentId)?.name ?? DEFAULT_AGENTS[0].name;
      setMessages([createWelcomeMessage(agentName)]);
    }

    activeUserEmailRef.current = userEmail;
  }, [authenticated, agents, pauseActiveChatRequest, selectedAgentId, userEmail]);

  const isNearChatBottom = useCallback((threshold = 96) => {
    const container = chatScrollRef.current;
    if (!container) return true;
    return container.scrollHeight - container.scrollTop - container.clientHeight < threshold;
  }, []);

  const scrollToBottom = useCallback(({ behavior = 'auto', force = false } = {}) => {
    const container = chatScrollRef.current;
    if (!container) {
      bottomRef.current?.scrollIntoView({ behavior });
      return;
    }

    if (!force && !isNearChatBottom()) return;

    if (behavior === 'smooth') {
      container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
    } else {
      container.scrollTop = container.scrollHeight;
    }
  }, [isNearChatBottom]);

  const scrollDuringTyping = useCallback(() => {
    scrollToBottom({ behavior: 'auto' });
  }, [scrollToBottom]);

  useEffect(() => {
    scrollToBottom({ behavior: 'smooth', force: true });
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
    if (!authenticated || !selectedAgentId || !messages.length) return;
    historyCacheRef.current[selectedAgentId] = messages;
  }, [authenticated, messages, selectedAgentId]);

  useEffect(() => {
    if (authenticated) {
      loadAgents();
    }
  }, [authenticated, loadAgents]);

  const switchAgent = useCallback(async (nextAgentId) => {
    if (!nextAgentId || nextAgentId === selectedAgentId || agentSwitching) return;

    pauseActiveChatRequest({ agentId: selectedAgentId });

    const generation = ++switchGenerationRef.current;
    const previousAgentId = selectedAgentId;
    const previousMessages = historyCacheRef.current[previousAgentId] ?? messages;
    const sessionId = backendSessionIdRef.current;

    const nextAgent = agents.find((agent) => agent.id === nextAgentId);
    const agentName = nextAgent?.name ?? 'Data Agent';
    const cachedMessages = historyCacheRef.current[nextAgentId];

    setAgentSwitching(true);
    setSelectedAgentId(nextAgentId);
    setStoredAgentId(nextAgentId);
    setQuestion('');
    setError(null);
    setMessages(
      cachedMessages?.length
        ? cachedMessages
        : [createWelcomeMessage(agentName, { suggestionsLoading: true })],
    );

    if (previousAgentId && previousMessages.length) {
      historyCacheRef.current[previousAgentId] = previousMessages;
      if (sessionId) {
        saveChatHistory(previousAgentId, previousMessages, sessionId).catch(() => {});
      }
    }

    try {
      const restored = await loadHistoryForAgent(nextAgentId, agentName, { useCache: false });
      if (generation !== switchGenerationRef.current) return;

      setMessages(restored);
      applyWelcomeSuggestions(nextAgentId, restored);
    } catch {
      if (generation !== switchGenerationRef.current) return;
      setMessages([createWelcomeMessage(agentName)]);
    } finally {
      if (generation === switchGenerationRef.current) {
        setAgentSwitching(false);
      }
    }
  }, [agentSwitching, agents, applyWelcomeSuggestions, loadHistoryForAgent, messages, pauseActiveChatRequest, selectedAgentId]);

  const sendQuestion = useCallback(async (text, { skipUserBubble = false, replaceMessageId = null } = {}) => {
    if (!selectedAgentId) return;

    const questionText = text?.trim();
    if (!questionText || agentSwitching) return;

    const active = activeChatRef.current;
    if (active.timeoutId) {
      window.clearTimeout(active.timeoutId);
      active.timeoutId = null;
    }
    if (active.controller) {
      active.userCancelled = true;
      active.controller.abort();
    }

    const requestGeneration = ++active.generation;
    active.userCancelled = false;
    active.pendingQuestion = questionText;
    active.agentId = selectedAgentId;

    setError(null);

    if (replaceMessageId) {
      setMessages((current) =>
        current.map((message) =>
          message.id === replaceMessageId
            ? {
                ...message,
                paused: false,
                resuming: true,
                text: 'Getting your answer...',
              }
            : message,
        ),
      );
    } else if (!skipUserBubble) {
      setMessages((current) => [
        ...current,
        { id: crypto.randomUUID(), role: 'user', text: questionText, animate: true },
      ]);
    }

    setQuestion('');
    setLoading(true);

    const controller = new AbortController();
    active.controller = controller;
    active.timeoutId = window.setTimeout(() => {
      active.userCancelled = false;
      controller.abort();
    }, (REQUEST_TIMEOUT + 30) * 1000);

    const agentIdForRequest = selectedAgentId;

    try {
      const response = await fetch(`${API_URL}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Session-Id': backendSessionIdRef.current,
        },
        body: JSON.stringify({
          question: questionText,
          agent_id: agentIdForRequest,
          timeout: REQUEST_TIMEOUT,
          include_details: false,
        }),
        signal: controller.signal,
      });

      if (requestGeneration !== active.generation) return;

      if (handleAuthFailure(response)) {
        return;
      }
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail || 'Unable to reach the backend.');
      }

      const data = await response.json();
      if (requestGeneration !== active.generation) return;

      active.pendingQuestion = null;
      active.agentId = null;

      const answerText = normalizeAssistantText(data.answer ?? 'No answer returned.');
      const isError = data.success === false;
      const charts = Array.isArray(data.charts) ? data.charts : [];
      const hasCharts = charts.length > 0;
      const assistantId = crypto.randomUUID();
      const assistantMessage = {
        id: assistantId,
        role: 'assistant',
        text: answerText,
        charts,
        animate: true,
        typewriter: !isError && !hasCharts,
        suggestions: [],
      };

      setMessages((current) => {
        let base = current;
        if (replaceMessageId) {
          const replaceIndex = current.findIndex((message) => message.id === replaceMessageId);
          base = replaceIndex >= 0 ? current.slice(0, replaceIndex) : current;
        }

        const withAssistant = [...base, assistantMessage];

        if (!isError) {
          const exchanges = getLastTwoExchanges(withAssistant);
          fetchFollowupSuggestions(agentIdForRequest, exchanges)
            .then((suggestions) => {
              if (requestGeneration !== active.generation) return;
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
      if (requestGeneration !== active.generation) return;

      if (exception.name === 'AbortError' && active.userCancelled) {
        return;
      }

      if (replaceMessageId) {
        setMessages((current) =>
          current.map((message) =>
            message.id === replaceMessageId
              ? {
                  ...message,
                  paused: true,
                  resuming: false,
                  pendingQuestion: questionText,
                  text: 'Your answer was paused. Tap below when you are ready to continue.',
                }
              : message,
          ),
        );
      }

      const message =
        exception.name === 'AbortError'
          ? 'Request took too long. Try a simpler question.'
          : exception.message || 'Something went wrong.';
      setError(message);
    } finally {
      if (requestGeneration !== active.generation) return;

      if (active.timeoutId) {
        window.clearTimeout(active.timeoutId);
        active.timeoutId = null;
      }
      active.controller = null;

      if (requestGeneration === active.generation) {
        if (!active.pendingQuestion) {
          active.agentId = null;
        }
      }

      setLoading(false);
    }
  }, [agentSwitching, handleAuthFailure, selectedAgentId]);

  const resumePausedAnswer = useCallback((pausedMessageId, questionText) => {
    if (!questionText || loading || agentSwitching) return;
    sendQuestion(questionText, { skipUserBubble: true, replaceMessageId: pausedMessageId });
  }, [agentSwitching, loading, sendQuestion]);

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
    if (!questionText || agentSwitching) return;

    if (!authenticated) {
      pendingSubmitRef.current = { text };
      setShowSignInModal(true);
      return;
    }

    sendQuestion(text);
  }, [authenticated, agentSwitching, question, selectedAgentId, sendQuestion]);

  const handleCloseSignIn = () => {
    abortActiveChatRequest();
    setShowSignInModal(false);
    pendingSubmitRef.current = null;
  };

  const startNewSession = async () => {
    if (!authenticated) {
      setShowSignInModal(true);
      return;
    }
    if (!selectedAgentId) return;

    abortActiveChatRequest();
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
      welcome.isWelcome = true;
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
    disabled: loading || agentSwitching,
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

  const showWelcomeScreen = isWelcomeChat(messages);

  return (
    <div className="flex h-dvh flex-col bg-slate-50 text-slate-800">
      <header className="relative z-20 shrink-0 border-b border-slate-200 bg-white px-3 pb-2 pt-[max(0.5rem,var(--safe-top))] shadow-sm sm:px-4 sm:pb-2.5 sm:pt-[max(0.625rem,var(--safe-top))]">
        <div className="flex min-h-11 min-w-0 items-center gap-2 sm:min-h-12 sm:gap-3">
          <div className="flex shrink-0 items-center justify-center" aria-label="Data Agent">
            <AppLogo className="block h-8 w-8 sm:h-9 sm:w-9" />
          </div>

          <div className="flex min-w-0 flex-1 items-center justify-end gap-1.5 sm:gap-2">
            <AgentSelector
              agents={agents}
              value={selectedAgentId}
              onChange={switchAgent}
              disabled={agentSwitching || !agents.length}
            />
            <button
              type="button"
              onClick={startNewSession}
              disabled={!selectedAgentId || agentSwitching}
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

      <main className="relative z-0 flex min-h-0 flex-1 flex-col overflow-hidden">
        {agentSwitching && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 bg-slate-50/85 backdrop-blur-[2px]">
            <div className="h-9 w-9 animate-spin rounded-full border-2 border-brand-500 border-t-transparent" />
            <p className="text-sm font-medium text-slate-600">
              Switching to {selectedAgent?.name ?? 'agent'}...
            </p>
          </div>
        )}
        <div
          className={`flex min-h-0 flex-1 flex-col ${
            agentSwitching ? 'pointer-events-none opacity-50' : ''
          }`}
        >
          {showWelcomeScreen ? (
            <WelcomeScreen
              agentName={selectedAgent?.name ?? 'Data Agent'}
              agentDescription={selectedAgent?.description}
              suggestions={messages[0]?.suggestions ?? []}
              suggestionsLoading={messages[0]?.suggestionsLoading}
              onSuggestionSelect={handleSuggestionSelect}
            />
          ) : (
            <div
              ref={chatScrollRef}
              className="scroll-area flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto overscroll-contain px-3 py-4 sm:gap-4 sm:px-6 sm:py-5"
            >
              {messages.map((message, index) => (
                <ChatBubble
                  key={message.id}
                  role={message.role}
                  charts={message.charts ?? []}
                  animate={message.animate}
                  typewriter={message.typewriter}
                  isWelcome={message.isWelcome}
                  paused={message.paused}
                  resuming={message.resuming}
                  suggestions={message.suggestions ?? []}
                  suggestionsLoading={message.suggestionsLoading}
                  onResumePaused={() => resumePausedAnswer(message.id, message.pendingQuestion)}
                  onSuggestionSelect={handleSuggestionSelect}
                  onTypingProgress={scrollDuringTyping}
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
          )}
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
            loading={loading || agentSwitching}
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
