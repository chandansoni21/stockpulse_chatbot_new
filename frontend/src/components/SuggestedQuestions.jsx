const SuggestedQuestions = ({ questions, onSelect, variant = 'inline', loading = false }) => {
  if (!loading && !questions?.length) return null;

  const isInline = variant === 'inline';

  return (
    <div className={isInline ? 'mt-3 border-t border-slate-100 pt-3' : 'mb-2'}>
      {isInline && (
        <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-slate-400">
          Suggested questions
        </p>
      )}
      {loading ? (
        <div className="flex flex-wrap items-center gap-2 py-0.5">
          {[0, 1, 2, 3].map((index) => (
            <span
              key={index}
              className="inline-block h-8 animate-pulse rounded-full bg-slate-100"
              style={{ width: `${88 + index * 24}px` }}
            />
          ))}
          <span className="w-full text-[11px] text-slate-400 sm:text-xs">
            Preparing suggestions...
          </span>
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          {questions.map((question) => (
            <button
              key={question}
              type="button"
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => onSelect(question)}
              className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-left text-xs text-slate-600 transition hover:border-brand-500 hover:bg-brand-50 hover:text-brand-700 sm:text-sm"
            >
              {question}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

export default SuggestedQuestions;
