const AgentSelector = ({ agents, value, onChange, disabled = false }) => {
  if (!agents?.length) return null;

  return (
    <div className="relative min-w-0 max-w-[140px] flex-1 sm:max-w-[180px] sm:flex-none">
      <select
        id="agent-select"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        aria-label="Select agent"
        className="w-full appearance-none truncate rounded-lg border border-slate-200 bg-white py-1.5 pl-2.5 pr-7 text-xs text-slate-700 shadow-sm outline-none transition hover:border-slate-300 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 disabled:opacity-60 sm:py-2 sm:pl-3 sm:pr-8 sm:text-sm"
      >
        {agents.map((agent) => (
          <option key={agent.id} value={agent.id}>
            {agent.name}
          </option>
        ))}
      </select>
      <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-[10px] text-slate-400 sm:text-xs">
        ▾
      </span>
    </div>
  );
};

export default AgentSelector;
