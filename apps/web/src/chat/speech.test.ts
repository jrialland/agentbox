import { speechAvailable, startSpeech } from "./speech";

class FakeRecognition {
  lang = "";
  interimResults = false;
  onresult: ((e: unknown) => void) | null = null;
  start() {
    this.onresult?.({ resultIndex: 0, results: [[{ transcript: "spoken words" }]] });
  }
  stop() {}
}

beforeEach(() => {
  (window as unknown as Record<string, unknown>).webkitSpeechRecognition = FakeRecognition;
});

test("speechAvailable is true when the API exists", () => {
  expect(speechAvailable()).toBe(true);
});

test("startSpeech forwards the transcript", () => {
  const received: string[] = [];
  startSpeech((t) => received.push(t));
  expect(received).toEqual(["spoken words"]);
});
