import { useEffect, useState } from 'react';

export function useTypewriter(text, active, { onComplete, onProgress } = {}) {
  const [displayed, setDisplayed] = useState(active ? '' : text);
  const [done, setDone] = useState(!active);

  useEffect(() => {
    if (!active) {
      setDisplayed(text);
      setDone(true);
      return undefined;
    }

    setDisplayed('');
    setDone(false);

    const length = text.length;
    const charsPerTick = length > 2500 ? 4 : length > 1200 ? 3 : length > 400 ? 2 : 1;
    const intervalMs = length > 2500 ? 6 : length > 1200 ? 10 : 16;

    let index = 0;
    const timer = window.setInterval(() => {
      index = Math.min(index + charsPerTick, length);
      const next = text.slice(0, index);
      setDisplayed(next);
      onProgress?.();

      if (index >= length) {
        window.clearInterval(timer);
        setDone(true);
        onComplete?.();
      }
    }, intervalMs);

    return () => window.clearInterval(timer);
  }, [active, text, onComplete, onProgress]);

  return { displayed, done, isTyping: active && !done };
}
