import AppLogo from './AppLogo';

const MicrosoftIcon = () => (
  <svg className="h-5 w-5" viewBox="0 0 21 21" aria-hidden="true">
    <rect x="1" y="1" width="9" height="9" fill="#f25022" />
    <rect x="11" y="1" width="9" height="9" fill="#7fba00" />
    <rect x="1" y="11" width="9" height="9" fill="#00a4ef" />
    <rect x="11" y="11" width="9" height="9" fill="#ffb900" />
  </svg>
);

const SignInModal = ({
  open,
  onLogin,
  onClose,
  loading,
  error,
  sessionDays = 7,
}) => {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="sign-in-title"
    >
      <button
        type="button"
        className="absolute inset-0 bg-slate-900/30 backdrop-blur-sm"
        aria-label="Close sign in"
        onClick={onClose}
      />

      <div className="relative w-full max-w-xs animate-[modalIn_0.2s_ease-out] rounded-2xl border border-slate-200 bg-white p-5 shadow-xl sm:max-w-sm sm:p-6">
        <button
          type="button"
          onClick={onClose}
          className="absolute right-3 top-3 rounded-lg p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
          aria-label="Close"
        >
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>

        <div className="mb-4 flex flex-col items-center text-center">
          <AppLogo className="mb-3 h-10 w-10" />
          <h2 id="sign-in-title" className="text-base font-semibold text-slate-900 sm:text-lg">
            Sign in to continue
          </h2>
          <p className="mt-1.5 text-xs leading-relaxed text-slate-500 sm:text-sm">
            Use your Microsoft account to ask questions.
          </p>
        </div>

        {error && (
          <p className="mb-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700 sm:text-sm">
            {error}
          </p>
        )}

        <button
          type="button"
          onClick={onLogin}
          disabled={loading}
          className="flex w-full items-center justify-center gap-2.5 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 shadow-sm transition hover:border-brand-500 hover:bg-slate-50 disabled:opacity-60"
        >
          <MicrosoftIcon />
          {loading ? 'Opening Microsoft login...' : 'Sign in with Microsoft'}
        </button>

        <p className="mt-3 text-center text-[11px] text-slate-400 sm:text-xs">
          Stay signed in for {sessionDays} days.
        </p>
      </div>
    </div>
  );
};

export default SignInModal;
