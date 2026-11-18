/* Minimal wrapper over the Web Speech API (SpeechRecognition). */

type Recognition = {
  lang: string;
  interimResults: boolean;
  onresult: ((e: SpeechEvent) => void) | null;
  start: () => void;
  stop: () => void;
};

type SpeechEvent = {
  resultIndex: number;
  results: { [i: number]: { [j: number]: { transcript: string } }; length: number };
};

type RecognizerCtor = new () => Recognition;

function getCtor(): RecognizerCtor | undefined {
  const w = window as unknown as {
    SpeechRecognition?: RecognizerCtor;
    webkitSpeechRecognition?: RecognizerCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition;
}

export function speechAvailable(): boolean {
  return typeof window !== "undefined" && Boolean(getCtor());
}

export function startSpeech(onText: (text: string) => void): () => void {
  const Ctor = getCtor();
  if (!Ctor) return () => {};
  const rec = new Ctor();
  rec.lang = "en-US";
  rec.interimResults = true;
  rec.onresult = (e) => {
    let text = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      text += e.results[i][0].transcript;
    }
    onText(text);
  };
  rec.start();
  return () => rec.stop();
}
