export type A2ASkill = {
  id: string;
  name: string;
  description: string;
  tags: string[];
  examples: string[];
};

export type StructuredA2ACard = {
  name: string;
  description: string;
  version: string;
  providerOrganization: string;
  providerUrl: string;
  documentationUrl: string;
  capabilities: {
    streaming: boolean;
    pushNotifications: boolean;
    stateTransitionHistory: boolean;
  };
  defaultInputModes: string[];
  defaultOutputModes: string[];
  skills: A2ASkill[];
};

export const EMPTY_A2A_CARD: StructuredA2ACard = {
  name: "",
  description: "",
  version: "1.0.0",
  providerOrganization: "",
  providerUrl: "",
  documentationUrl: "",
  capabilities: {
    streaming: true,
    pushNotifications: false,
    stateTransitionHistory: false,
  },
  defaultInputModes: ["text/plain"],
  defaultOutputModes: ["text/plain"],
  skills: [],
};

type RawCard = Record<string, unknown>;
const str = (value: unknown, fallback = "") =>
  typeof value === "string" ? value : fallback;
const strArray = (value: unknown) =>
  Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];

export function toStructuredCard(
  raw: RawCard | null,
  fallbackName: string,
): StructuredA2ACard {
  const card = raw ?? {};
  const capabilities =
    card.capabilities && typeof card.capabilities === "object"
      ? (card.capabilities as Record<string, unknown>)
      : {};
  const provider =
    card.provider && typeof card.provider === "object"
      ? (card.provider as Record<string, unknown>)
      : {};
  const skills = Array.isArray(card.skills) ? card.skills : [];
  return {
    name: str(card.name, fallbackName),
    description: str(card.description),
    version: str(card.version, "1.0.0"),
    providerOrganization: str(provider.organization),
    providerUrl: str(provider.url),
    documentationUrl: str(card.documentationUrl),
    capabilities: {
      streaming: capabilities.streaming === true,
      pushNotifications: capabilities.pushNotifications === true,
      stateTransitionHistory: capabilities.stateTransitionHistory === true,
    },
    defaultInputModes: strArray(card.defaultInputModes),
    defaultOutputModes: strArray(card.defaultOutputModes),
    skills: skills.map((skill) => {
      const item = (skill ?? {}) as Record<string, unknown>;
      return {
        id: str(item.id),
        name: str(item.name),
        description: str(item.description),
        tags: strArray(item.tags),
        examples: strArray(item.examples),
      };
    }),
  };
}

export function mergeStructuredCard(
  raw: RawCard | null,
  card: StructuredA2ACard,
): RawCard {
  const next: RawCard = { ...(raw ?? {}) };
  next.name = card.name.trim();
  next.description = card.description.trim();
  next.version = card.version.trim();
  if (card.providerOrganization || card.providerUrl) {
    next.provider = {
      organization: card.providerOrganization.trim(),
      url: card.providerUrl.trim(),
    };
  }
  if (card.documentationUrl) next.documentationUrl = card.documentationUrl.trim();
  next.capabilities = { ...card.capabilities };
  next.defaultInputModes = card.defaultInputModes;
  next.defaultOutputModes = card.defaultOutputModes;
  next.skills = card.skills.map((skill) => ({
    id: skill.id.trim(),
    name: skill.name.trim(),
    description: skill.description.trim(),
    tags: skill.tags,
    examples: skill.examples,
  }));
  return next;
}

export function validateStructuredCard(card: StructuredA2ACard) {
  const errors: Record<string, string> = {};
  if (!card.name.trim()) errors.name = "Name is required.";
  if (!/^\d+\.\d+\.\d+/.test(card.version.trim())) {
    errors.version = "Use a version such as 1.0.0.";
  }
  const url = (value: string) => !value || /^https?:\/\/\S+$/i.test(value);
  if (!url(card.providerUrl)) errors.providerUrl = "Use an http/https URL.";
  if (!url(card.documentationUrl)) {
    errors.documentationUrl = "Use an http/https URL.";
  }
  const ids = card.skills.map((skill) => skill.id.trim());
  if (ids.some((id) => !id)) errors.skills = "Every skill needs an id.";
  else if (new Set(ids).size !== ids.length) {
    errors.skills = "Skill ids must be unique.";
  }
  if (card.skills.some((skill) => !skill.name.trim())) {
    errors.skills = "Every skill needs a name.";
  }
  return errors;
}

export function parseCardJson(
  text: string,
):
  | { card: RawCard; error?: undefined }
  | { card?: undefined; error: string } {
  try {
    const parsed = JSON.parse(text);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { error: "The card must be a JSON object." };
    }
    return { card: parsed as RawCard };
  } catch (error) {
    return { error: error instanceof Error ? error.message : "Invalid JSON." };
  }
}
