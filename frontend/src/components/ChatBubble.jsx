import { useCallback, useEffect } from 'react';
import ChartBlock from './ChartBlock';
import MessageContent from './MessageContent';
import SuggestedQuestions from './SuggestedQuestions';
import { useTypewriter } from '../hooks/useTypewriter';

const ChatBubble = ({
  role,
  children,
  charts = [],
  animate = false,
  typewriter = false,
  suggestions = [],
  suggestionsLoading = false,
  isWelcome = false,
  paused = false,
  resuming = false,
  onResumePaused,
  onSuggestionSelect,
  onTypingProgress,
}) => {
  const isUser = role === 'user';
  const shouldType = typewriter && !isUser && !paused && !resuming;

  const handleProgress = useCallback(() => {
    onTypingProgress?.();
  }, [onTypingProgress]);

  const { displayed, done, isTyping } = useTypewriter(children, shouldType, {
    onProgress: handleProgress,
  });

  const content = shouldType ? displayed : children;
  const showCharts = !isUser && done && charts?.length > 0;

  useEffect(() => {
    if (showCharts) {
      onTypingProgress?.();
    }
  }, [showCharts, onTypingProgress]);

  return (
    <div
      className={`flex w-full min-w-0 flex-col gap-2 ${isUser ? 'items-end' : 'items-start'} ${
        animate ? (isUser ? 'message-enter-user' : 'message-enter-assistant') : ''
      }`}
    >
      <div
        className={`min-w-0 max-w-[95%] rounded-2xl px-3 py-2.5 sm:max-w-[90%] sm:px-4 sm:py-3 ${
          isUser
            ? 'bg-brand-500 text-white shadow-sm'
            : 'w-full max-w-full border border-slate-200 bg-white text-slate-700 shadow-sm sm:max-w-[95%]'
        }`}
      >
        <MessageContent text={resuming ? '' : content} isUser={isUser} />
        {isTyping && (
          <span className={`ml-0.5 inline-block h-4 w-0.5 animate-pulse align-middle ${isUser ? 'bg-white/80' : 'bg-brand-500'}`} />
        )}
        {!isUser && paused && !resuming && (
          <div className="mt-3 rounded-xl border border-amber-200/80 bg-amber-50/60 px-3 py-2.5">
            <p className="text-xs font-medium text-amber-800 sm:text-sm">Answer paused</p>
            <p className="mt-0.5 text-xs text-amber-700/90">
              Your question is saved. Resume when you are ready.
            </p>
            <button
              type="button"
              onClick={onResumePaused}
              className="mt-2.5 inline-flex items-center gap-1.5 rounded-lg bg-brand-500 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition hover:bg-brand-600 sm:text-sm"
            >
              <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path d="M6.3 2.841A1.5 1.5 0 004 4.11V15.89a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z" />
              </svg>
              Get answer
            </button>
          </div>
        )}
        {!isUser && resuming && (
          <div className="mt-3 flex items-center gap-2 text-sm text-slate-500">
            <div className="h-2 w-2 animate-pulse rounded-full bg-brand-500" />
            Getting your answer...
          </div>
        )}
        {!isUser && !isWelcome && done && (suggestionsLoading || (suggestions?.length ?? 0) > 0) && (
          <SuggestedQuestions
            questions={suggestions}
            onSelect={onSuggestionSelect}
            variant="inline"
            loading={suggestionsLoading}
          />
        )}
      </div>

      {showCharts && (
        <div className="w-full max-w-full space-y-3 sm:max-w-[95%]">
          {charts.map((chart) => (
            <ChartBlock key={chart.id || chart.title} chart={chart} />
          ))}
        </div>
      )}
    </div>
  );
};

export default ChatBubble;
