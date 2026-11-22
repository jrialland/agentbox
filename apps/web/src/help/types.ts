export type HelpId =
  | "provider.kind"
  | "provider.urls"
  | "provider.api-key"
  | "provider.models"
  | "agent.modes"
  | "agent.tools"
  | "agent.mcp"
  | "agent.subagents"
  | "a2a.card"
  | "a2a.skills"
  | "api.scopes"
  | "skills.overview"
  | "plugins.overview"
  | "onboarding.provider"
  | "onboarding.agent"
  | "onboarding.session";

export type HelpSection = {
  heading: string;
  paragraphs?: string[];
  bullets?: string[];
  code?: string;
};

export type HelpEntry = {
  id: HelpId;
  title: string;
  summary: string;
  sections: HelpSection[];
  related?: HelpId[];
};
