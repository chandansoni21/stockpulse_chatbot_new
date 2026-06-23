const REPORT_SPECS_NOTICE = /^File\(s\)\s+report_specs[^\n]*\n?/gim;
const DASHBOARD_CHART_NOTICE = /^\s*(?:you can )?(?:now )?view (?:the |this |your )?(?:pie |bar |line )?(?:chart|graph)[^\n]*(?:dashboard|below|above)[^\n]*\n?/gim;
const DASHBOARD_CHART_AVAILABLE = /^\s*(?:the )?(?:pie |bar |line )?(?:chart|graph) is (?:available|shown)[^\n]*(?:dashboard|below|above)[^\n]*\n?/gim;
const SEE_CHART_ON_DASHBOARD = /^\s*see (?:the |your )?(?:chart|graph) (?:on|in) your dashboard[^\n]*\n?/gim;

export function stripAgentBoilerplate(text) {
  return String(text ?? '')
    .replace(REPORT_SPECS_NOTICE, '')
    .replace(DASHBOARD_CHART_NOTICE, '')
    .replace(DASHBOARD_CHART_AVAILABLE, '')
    .replace(SEE_CHART_ON_DASHBOARD, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

export function normalizeAssistantText(text) {
  return stripAgentBoilerplate(String(text ?? '').replace(/^Error:\s*/i, ''));
}

export function isFabricAccessMessage(text) {
  const normalized = normalizeAssistantText(text).toLowerCase();
  return (
    (normalized.includes('fabric data agent')
      && (
        normalized.includes('could not')
        || normalized.includes("couldn't")
        || normalized.includes('does not have access')
        || normalized.includes('administrator')
      ))
    || normalized.includes('microsoft sign-in no longer matches')
    || normalized.includes("user id")
  );
}
