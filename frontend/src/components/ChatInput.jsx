import MicIcon from './MicIcon';
import SendIcon from './SendIcon';

const ChatInput = ({
  value,
  onChange,
  onKeyDown,
  onSend,
  onMicClick,
  onFocus,
  onBlur,
  listening,
  loading,
  micSupported,
  placeholder,
}) => {
  const canSend = value.trim().length > 0 && !loading;

  return (
    <div className="flex min-h-[52px] items-center gap-1 rounded-2xl border border-slate-200 bg-white px-1.5 py-1.5 shadow-sm transition-colors focus-within:border-brand-500 focus-within:ring-2 focus-within:ring-brand-500/20 sm:min-h-[56px] sm:gap-1.5 sm:px-2">
      <textarea
        rows={1}
        value={value}
        onChange={onChange}
        onKeyDown={onKeyDown}
        onFocus={onFocus}
        onBlur={onBlur}
        placeholder={placeholder}
        disabled={loading}
        className="min-h-[36px] max-h-32 flex-1 resize-none self-center bg-transparent py-2 pl-1 text-base leading-6 text-slate-800 outline-none placeholder:text-slate-400 disabled:opacity-60 sm:min-h-[40px] sm:pl-0.5 sm:text-sm"
      />

      <div className="flex shrink-0 items-center gap-0.5 sm:gap-1">
        <button
          type="button"
          onClick={onMicClick}
          disabled={loading || !micSupported}
          aria-label={listening ? 'Stop listening' : 'Speech to text'}
          className={`flex h-9 w-9 items-center justify-center rounded-lg transition sm:h-10 sm:w-10 ${
            listening
              ? 'bg-rose-100 text-rose-600 ring-1 ring-rose-200'
              : 'text-slate-400 hover:bg-slate-100 hover:text-slate-600 disabled:text-slate-300'
          }`}
        >
          <MicIcon className={`h-[18px] w-[18px] sm:h-5 sm:w-5 ${listening ? 'animate-pulse' : ''}`} />
        </button>
        <button
          type="button"
          onClick={onSend}
          disabled={!canSend}
          aria-label="Send message"
          className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-500 text-white transition hover:bg-brand-600 disabled:bg-slate-200 disabled:text-slate-400 sm:h-10 sm:w-10"
        >
          <SendIcon className="h-[18px] w-[18px] sm:h-5 sm:w-5" />
        </button>
      </div>
    </div>
  );
};

export default ChatInput;
