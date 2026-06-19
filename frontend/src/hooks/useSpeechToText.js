import { useCallback, useEffect, useRef, useState } from 'react';

function getSpeechRecognition() {
  if (typeof window === 'undefined') return null;
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

export function useSpeechToText({ onFinalText, disabled = false }) {
  const [listening, setListening] = useState(false);
  const [supported] = useState(() => Boolean(getSpeechRecognition()));
  const recognitionRef = useRef(null);

  const stopListening = useCallback(() => {
    recognitionRef.current?.stop();
    setListening(false);
  }, []);

  const startListening = useCallback(() => {
    if (disabled) return;

    const SpeechRecognition = getSpeechRecognition();
    if (!SpeechRecognition) {
      onFinalText?.(null, new Error('Speech recognition is not supported in this browser. Try Chrome or Edge.'));
      return;
    }

    if (listening) {
      stopListening();
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = navigator.language || 'en-IN';
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => setListening(true);

    recognition.onresult = (event) => {
      let transcript = '';
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        transcript += event.results[i][0].transcript;
      }

      const isFinal = event.results[event.results.length - 1]?.isFinal;
      if (isFinal && transcript.trim()) {
        onFinalText?.(transcript.trim(), null);
      }
    };

    recognition.onerror = (event) => {
      setListening(false);
      if (event.error === 'aborted' || event.error === 'no-speech') return;
      onFinalText?.(null, new Error(event.error === 'not-allowed' ? 'Microphone permission denied.' : 'Could not capture speech.'));
    };

    recognition.onend = () => setListening(false);

    recognitionRef.current = recognition;
    recognition.start();
  }, [disabled, listening, onFinalText, stopListening]);

  useEffect(() => () => recognitionRef.current?.abort(), []);

  return { listening, supported, startListening, stopListening };
}
