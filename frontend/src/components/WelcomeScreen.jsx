import AppLogo from './AppLogo';

const WelcomeScreen = ({
  agentName,
  agentDescription,
  suggestions = [],
  suggestionsLoading = false,
  onSuggestionSelect,
}) => (
  <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain scroll-area">
    <div className="flex min-h-full flex-col items-center px-4 py-6 sm:px-6 sm:py-10">
      <div className="my-auto w-full max-w-md animate-[fadeIn_0.35s_ease-out]">
        <div className="text-center">
          <div className="mx-auto inline-flex items-center justify-center rounded-2xl bg-white p-3 shadow-sm ring-1 ring-slate-200/80 sm:p-3.5">
            <AppLogo className="block h-11 w-11 sm:h-14 sm:w-14" />
          </div>
          <h1 className="mt-4 text-xl font-bold tracking-tight text-slate-800 sm:mt-5 sm:text-2xl">
            {agentName}
          </h1>
          {agentDescription && (
            <p className="mx-auto mt-1.5 max-w-sm text-sm text-slate-500">
              {agentDescription}
            </p>
          )}
          <p className="mx-auto mt-3 max-w-sm text-sm leading-relaxed text-slate-600 sm:mt-4">
            Ask anything about your data — or pick a starter question below.
          </p>
        </div>

        <div className="mt-6 space-y-2.5 sm:mt-8 sm:space-y-3">
          {suggestionsLoading ? (
            [0, 1, 2, 3].map((index) => (
              <div
                key={index}
                className="h-[3.25rem] animate-pulse rounded-xl bg-slate-100/90 sm:h-14"
                style={{ animationDelay: `${index * 80}ms` }}
              />
            ))
          ) : suggestions.length > 0 ? (
            suggestions.map((question, index) => (
              <button
                key={question}
                type="button"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => onSuggestionSelect(question)}
                className="group flex w-full items-center gap-3 rounded-xl border border-slate-200/90 bg-white px-3.5 py-3 text-left shadow-sm transition duration-200 hover:-translate-y-px hover:border-brand-400 hover:bg-gradient-to-r hover:from-brand-50/80 hover:to-white hover:shadow-md active:translate-y-0 sm:px-4 sm:py-3.5"
              >
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-brand-600 text-sm font-semibold text-white shadow-sm transition group-hover:scale-105">
                  {index + 1}
                </span>
                <span className="min-w-0 flex-1 text-sm leading-snug text-slate-700 group-hover:text-slate-900 sm:text-[15px]">
                  {question}
                </span>
                <svg
                  className="h-4 w-4 shrink-0 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-brand-500"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  aria-hidden="true"
                >
                  <path
                    fillRule="evenodd"
                    d="M3 10a.75.75 0 01.75-.75h10.638L10.23 5.29a.75.75 0 111.04-1.08l5.5 5.25a.75.75 0 010 1.08l-5.5 5.25a.75.75 0 11-1.04-1.08l4.158-3.96H3.75A.75.75 0 013 10z"
                    clipRule="evenodd"
                  />
                </svg>
              </button>
            ))
          ) : (
            <p className="text-center text-sm text-slate-400">
              Type a question below to get started.
            </p>
          )}

          {suggestionsLoading && (
            <p className="pt-1 text-center text-xs text-slate-400">
              Preparing suggestions for you...
            </p>
          )}
        </div>
      </div>
    </div>
  </div>
);

export default WelcomeScreen;
