export function normalizeAssistantText(text) {
  return String(text ?? '').replace(/^Error:\s*/i, '').trim();
}

export function isFabricAccessMessage(text) {
  const normalized = normalizeAssistantText(text).toLowerCase();
  return (
    normalized.includes('fabric data agent')
    && (
      normalized.includes('could not')
      || normalized.includes("couldn't")
      || normalized.includes('does not have access')
      || normalized.includes('administrator')
    )
  );
}
