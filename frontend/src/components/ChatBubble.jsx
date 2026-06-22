import { useCallback } from 'react';
import MessageContent from './MessageContent';
import SuggestedQuestions from './SuggestedQuestions';
import { useTypewriter } from '../hooks/useTypewriter';

const ChatBubble = ({
  role,
  children,
  animate = false,
  typewriter = false,
  suggestions = [],
  suggestionsLoading = false,
  onSuggestionSelect,
  onTypingProgress,
}) => {
  const isUser = role === 'user';
  const shouldType = typewriter && !isUser;

  const handleProgress = useCallback(() => {
    onTypingProgress?.();
  }, [onTypingProgress]);

  const { displayed, done, isTyping } = useTypewriter(children, shouldType, {
    onProgress: handleProgress,
  });

  const content = shouldType ? displayed : children;

  return (
    <div
      className={`flex w-full min-w-0 ${isUser ? 'justify-end' : 'justify-start'} ${
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
        <MessageContent text={content} isUser={isUser} />
        {isTyping && (
          <span className={`ml-0.5 inline-block h-4 w-0.5 animate-pulse align-middle ${isUser ? 'bg-white/80' : 'bg-brand-500'}`} />
        )}
        {!isUser && done && (suggestionsLoading || (suggestions?.length ?? 0) > 0) && (
          <SuggestedQuestions
            questions={suggestions}
            onSelect={onSuggestionSelect}
            variant="inline"
            loading={suggestionsLoading}
          />
        )}
      </div>
    </div>
  );
};

export default ChatBubble;
