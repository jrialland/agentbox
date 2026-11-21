import { useState } from "react";

const KEY = "agentbox-onboarding-v1";

function read() {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "{}") as { dismissed?: boolean };
  } catch {
    return {};
  }
}

export function useOnboardingPreference() {
  const [dismissed, setDismissed] = useState(() => read().dismissed === true);
  const dismiss = () => {
    localStorage.setItem(KEY, JSON.stringify({ dismissed: true }));
    setDismissed(true);
  };
  const reset = () => {
    localStorage.removeItem(KEY);
    setDismissed(false);
  };
  return { dismissed, dismiss, reset };
}
