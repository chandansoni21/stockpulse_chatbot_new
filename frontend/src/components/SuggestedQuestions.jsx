const SuggestedQuestions = ({ questions, onSelect, variant = 'inline' }) => {
  if (!questions?.length) return null;

  const isInline = variant === 'inline';

  return (
    <div className={isInline ? 'mt-3 border-t border-slate-100 pt-3' : 'mb-2'}>
      {isInline && (
        <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-slate-400">
          Suggested questions
        </p>
      )}
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
    </div>
  );
};

export default SuggestedQuestions;
