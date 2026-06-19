const AppLogo = ({ className = 'h-9 w-9' }) => (
  <svg
    className={className}
    viewBox="0 0 40 40"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    aria-hidden="true"
  >
    <rect width="40" height="40" rx="10" className="fill-white" />
    <rect x="8" y="8" width="24" height="24" rx="6" className="stroke-brand-500" strokeWidth="1.5" />
    <rect x="13" y="22" width="3" height="6" rx="1" className="fill-brand-500/80" />
    <rect x="18.5" y="18" width="3" height="10" rx="1" className="fill-brand-500" />
    <rect x="24" y="14" width="3" height="14" rx="1" className="fill-sky-400" />
    <path
      d="M28 10l1.2 2.4 2.6.4-1.9 1.8.5 2.6L28 15.8l-2.4 1.4.5-2.6-1.9-1.8 2.6-.4L28 10z"
      className="fill-sky-300"
    />
  </svg>
);

export default AppLogo;
