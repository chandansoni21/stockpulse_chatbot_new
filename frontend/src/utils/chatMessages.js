export function createPausedMessage(questionText) {
  return {
    id: crypto.randomUUID(),
    role: 'assistant',
    text: 'Your answer was paused. Tap below when you are ready to continue.',
    paused: true,
    pendingQuestion: questionText,
    animate: false,
    typewriter: false,
    suggestions: [],
  };
}

export function finalizePausedMessages(messages, questionText) {
  if (!questionText || !Array.isArray(messages) || !messages.length) {
    return messages;
  }

  const last = messages[messages.length - 1];
  if (last?.role === 'assistant' && last?.paused && last?.pendingQuestion === questionText) {
    return messages;
  }

  if (last?.role !== 'user' || last.text !== questionText) {
    return messages;
  }

  return [...messages, createPausedMessage(questionText)];
}

export function isWelcomeOnlyChat(messageList) {
  if (!Array.isArray(messageList) || messageList.length !== 1) return false;
  const message = messageList[0];
  if (message?.role !== 'assistant') return false;
  if (message.paused || message.pendingQuestion) return false;
  return true;
}
