export interface SpeechRecognitionResultLike {
  readonly 0?: { readonly transcript?: string };
}

export interface SpeechRecognitionEventLike {
  readonly results: ArrayLike<SpeechRecognitionResultLike>;
}

export interface SpeechRecognitionLike {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
}

export type RecognitionController = { stop: () => void };
type SpeechWindow = Window & {
  SpeechRecognition?: new () => SpeechRecognitionLike;
  webkitSpeechRecognition?: new () => SpeechRecognitionLike;
};

export function startBrowserRecognition(
  onText: (text: string) => void,
  onError: (message: string) => void,
  onStateChange: (listening: boolean) => void,
): RecognitionController | null {
  const speechWindow = window as SpeechWindow;
  const Constructor = speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition;
  if (!Constructor) return null;
  const recognition = new Constructor();
  recognition.lang = 'en-IN';
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  recognition.onresult = (event) => {
    const transcript = event.results[0]?.[0]?.transcript;
    if (transcript) onText(transcript.trim());
  };
  recognition.onerror = (event) => onError(`Microphone error: ${event.error}. You can continue using text.`);
  recognition.onend = () => onStateChange(false);
  try {
    recognition.start();
    onStateChange(true);
  } catch {
    onError('Could not start speech recognition. Check microphone permission or use text input.');
    onStateChange(false);
    return null;
  }
  return { stop: () => recognition.stop() };
}

export function speakResponse(text: string): boolean {
  if (!('speechSynthesis' in window) || typeof SpeechSynthesisUtterance === 'undefined') return false;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = 'en-IN';
  window.speechSynthesis.speak(utterance);
  return true;
}
