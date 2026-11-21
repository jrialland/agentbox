import { isHttpUrl, requiredText } from "../../lib/validation";

export type ProviderDraft = {
  name: string;
  kind: string;
  baseUrl: string;
  modelsUrl: string;
  apiKey: string;
};

export const EMPTY_PROVIDER_DRAFT: ProviderDraft = {
  name: "",
  kind: "generic",
  baseUrl: "",
  modelsUrl: "",
  apiKey: "",
};

type Preset = { label: string; baseUrl: string; modelsUrl: string };

export const PROVIDER_PRESETS: Record<string, Preset> = {
  generic: { label: "Generic OpenAI-compatible", baseUrl: "", modelsUrl: "" },
  openai_legacy: {
    label: "OpenAI (Chat Completions)",
    baseUrl: "https://api.openai.com/v1",
    modelsUrl: "https://api.openai.com/v1/models",
  },
  openai_responses: {
    label: "OpenAI (Responses)",
    baseUrl: "https://api.openai.com/v1",
    modelsUrl: "https://api.openai.com/v1/models",
  },
  anthropic: {
    label: "Anthropic",
    baseUrl: "https://api.anthropic.com/v1",
    modelsUrl: "",
  },
  moonshot: {
    label: "Moonshot",
    baseUrl: "https://api.moonshot.cn/v1",
    modelsUrl: "https://api.moonshot.cn/v1/models",
  },
  deepseek: {
    label: "DeepSeek",
    baseUrl: "https://api.deepseek.com/v1",
    modelsUrl: "https://api.deepseek.com/v1/models",
  },
  ollama: {
    label: "Ollama",
    baseUrl: "http://localhost:11434",
    modelsUrl: "http://localhost:11434/v1/models",
  },
};

export function validateProviderDraft(
  draft: ProviderDraft,
): Partial<Record<keyof ProviderDraft, string>> {
  const errors: Partial<Record<keyof ProviderDraft, string>> = {};
  const name = requiredText(draft.name, "Name");
  if (name) errors.name = name;
  const base = isHttpUrl(draft.baseUrl, "Base URL");
  if (base) errors.baseUrl = base;
  const models = isHttpUrl(draft.modelsUrl, "Models URL");
  if (models) errors.modelsUrl = models;
  return errors;
}

export function applyProviderPreset(
  current: ProviderDraft,
  nextKind: string,
): ProviderDraft {
  const previous = PROVIDER_PRESETS[current.kind];
  const next = PROVIDER_PRESETS[nextKind];
  const untouched = (value: string, previousValue: string | undefined) =>
    !value || value === previousValue;
  return {
    ...current,
    kind: nextKind,
    baseUrl: untouched(current.baseUrl, previous?.baseUrl)
      ? next?.baseUrl ?? ""
      : current.baseUrl,
    modelsUrl: untouched(current.modelsUrl, previous?.modelsUrl)
      ? next?.modelsUrl ?? ""
      : current.modelsUrl,
  };
}
