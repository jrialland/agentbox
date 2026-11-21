import type { HelpEntry, HelpId } from "./types";

export const HELP_ENTRIES: Record<HelpId, HelpEntry> = {
  "provider.kind": {
    id: "provider.kind",
    title: "Provider kind",
    summary:
      "Choose the API style your provider exposes. Most hosted services are OpenAI-compatible APIs.",
    sections: [
      {
        heading: "Which kind should I choose?",
        bullets: [
          "OpenAI (Chat Completions) for the classic /v1/chat/completions API.",
          "OpenAI (Responses) for OpenAI's newer responses API.",
          "Generic OpenAI-compatible for DeepSeek-style or self-hosted gateways.",
          "Ollama for a local Ollama server.",
        ],
      },
      {
        heading: "Not sure?",
        paragraphs: [
          "Start with the provider's documentation. If it shows an OpenAI-compatible base URL, choose Generic OpenAI-compatible.",
        ],
      },
    ],
    related: ["provider.urls", "provider.models"],
  },
  "provider.urls": {
    id: "provider.urls",
    title: "Provider URLs",
    summary:
      "Base URL is the API root. Models URL must return a JSON list of models.",
    sections: [
      {
        heading: "Typical values",
        code: "Base URL: https://api.deepseek.com/v1\nModels URL: https://api.deepseek.com/v1/models",
      },
      {
        heading: "Rules of thumb",
        bullets: [
          "Include /v1 when the provider documentation includes it.",
          "Do not add a trailing slash.",
          "Models URL must return { \"data\": [{ \"id\": \"model-name\" }] }.",
        ],
      },
    ],
    related: ["provider.kind", "provider.models"],
  },
  "provider.api-key": {
    id: "provider.api-key",
    title: "Provider API key",
    summary:
      "The key is stored by Agentbox and reused when you leave the field blank while editing.",
    sections: [
      {
        heading: "Key handling",
        bullets: [
          "The key is never shown again after saving.",
          "A connection test does not save the key.",
          "If the provider rejects the key, check for extra spaces or a missing prefix.",
        ],
      },
    ],
    related: ["provider.kind"],
  },
  "provider.models": {
    id: "provider.models",
    title: "Model discovery",
    summary:
      "Agentbox reads an OpenAI-style data[].id list and adds new models on refresh.",
    sections: [
      {
        heading: "Expected response",
        code: '{ "object": "list", "data": [{ "id": "model-a" }, { "id": "model-b" }] }',
      },
      {
        heading: "If discovery fails",
        bullets: [
          "Check the Models URL and API key.",
          "Some providers require a different model-list endpoint.",
          "Ollama may need its OpenAI-compatible /v1 endpoint enabled.",
        ],
      },
    ],
    related: ["provider.urls"],
  },
  "agent.modes": {
    id: "agent.modes",
    title: "Agent modes",
    summary:
      "Modes let the same agent offer read-only Ask and write-enabled Agent behavior.",
    sections: [
      {
        heading: "Write flag",
        paragraphs: [
          "A mode with Write enabled can use file-changing and terminal tools. A mode without it should be limited to read-only tools.",
        ],
      },
      {
        heading: "Naming",
        bullets: [
          "Use short, stable names such as ask and agent.",
          "The name appears in the chat composer.",
        ],
      },
    ],
    related: ["agent.tools", "onboarding.agent"],
  },
  "agent.tools": {
    id: "agent.tools",
    title: "Agent tools",
    summary:
      "Tools are grouped by risk. Write tools can modify files or run commands.",
    sections: [
      {
        heading: "Groups",
        bullets: [
          "Filesystem read: inspect files without changing them.",
          "Filesystem write: create, edit, move, copy, or delete paths.",
          "Web: search and fetch remote content.",
          "Terminal: run commands and manage background jobs.",
        ],
      },
      {
        heading: "Start small",
        paragraphs: [
          "Enable read-only tools first. Add write or terminal tools only when the task requires them.",
        ],
      },
    ],
    related: ["agent.modes"],
  },
  "agent.mcp": {
    id: "agent.mcp",
    title: "MCP servers",
    summary:
      "MCP servers add tools and apps, either from a remote endpoint or a local command.",
    sections: [
      {
        heading: "Remote URL",
        paragraphs: [
          "Enter the HTTP or HTTPS URL for a remote MCP server. Authentication and transport settings belong to the server.",
        ],
      },
      {
        heading: "Local command",
        paragraphs: [
          "A local MCP server runs as a child process of a session. Its working directory defaults to the project root and can be narrowed to a subdirectory; absolute paths must stay inside the project or its extra roots.",
          "Environment variables can be set explicitly or passed through from the host by name. Values are stored with the agent and never written to logs.",
          "The process starts on the session's first run and is reused for later turns. It stops when the session is deleted or closed, after an idle timeout, or when the server shuts down.",
        ],
      },
      {
        heading: "Failures",
        bullets: [
          "A broken local server shows a warning and the rest of the agent keeps working.",
          "An unreachable remote server appears as a tool error in chat.",
          "Remove servers you no longer trust or need.",
        ],
      },
    ],
    related: ["agent.tools"],
  },
  "agent.subagents": {
    id: "agent.subagents",
    title: "Sub-agents",
    summary:
      "Sub-agents run delegated work and add latency and token cost.",
    sections: [
      {
        heading: "When to use them",
        paragraphs: [
          "Use sub-agents for separable work such as research or review. Keep simple tasks in the parent agent.",
        ],
      },
    ],
    related: ["agent.modes"],
  },
  "a2a.card": {
    id: "a2a.card",
    title: "A2A agent card",
    summary:
      "The card publishes your agent's identity, capabilities, and skills to A2A clients.",
    sections: [
      {
        heading: "Structured or JSON",
        paragraphs: [
          "Use the structured tab for normal editing. Use JSON when you need fields not shown in the form; unknown fields are preserved.",
        ],
      },
      {
        heading: "Required",
        bullets: ["Name", "Version", "At least one valid skill for useful discovery"],
      },
    ],
    related: ["a2a.skills"],
  },
  "a2a.skills": {
    id: "a2a.skills",
    title: "A2A skills",
    summary:
      "Each skill describes one capability the agent can perform.",
    sections: [
      {
        heading: "Good skill entries",
        bullets: [
          "Use a stable lowercase id such as code-review.",
          "Give the skill a human-readable name.",
          "List concrete examples of requests it handles.",
        ],
      },
    ],
    related: ["a2a.card"],
  },
  "api.scopes": {
    id: "api.scopes",
    title: "API scopes",
    summary:
      "Scopes limit what an API key can do. A key with no scopes cannot authenticate useful work.",
    sections: [
      {
        heading: "Recommended start",
        paragraphs: [
          "For read-only integrations, use providers:read and sessions:read. Add create or manage scopes only when needed.",
        ],
      },
    ],
  },
  "skills.overview": {
    id: "skills.overview",
    title: "Skills",
    summary:
      "Skills are reusable Markdown instruction packs invoked from the composer with /.",
    sections: [
      {
        heading: "Using skills",
        paragraphs: [
          "Type / in the chat composer, choose a skill, and send the message. The skill instructions are prepended for that turn.",
        ],
      },
    ],
  },
  "onboarding.provider": {
    id: "onboarding.provider",
    title: "Connect a provider",
    summary:
      "Start with one model endpoint so Agentbox can discover models.",
    sections: [
      {
        heading: "Suggested first provider",
        paragraphs: [
          "Use the provider you already pay for. Test the connection before creating it.",
        ],
      },
    ],
    related: ["provider.kind", "provider.urls"],
  },
  "onboarding.agent": {
    id: "onboarding.agent",
    title: "Create an agent",
    summary:
      "Pick a discovered model and keep write tools disabled until needed.",
    sections: [
      {
        heading: "Essentials",
        bullets: [
          "Name the agent after its job.",
          "Choose a model from the discovered list.",
          "Start with read-only filesystem tools.",
        ],
      },
    ],
    related: ["agent.tools", "agent.modes"],
  },
  "onboarding.session": {
    id: "onboarding.session",
    title: "Start a session",
    summary: "A session pairs a project folder with an agent.",
    sections: [
      {
        heading: "Project path",
        paragraphs: [
          "Use an absolute path on this machine, or . for the current working directory.",
        ],
      },
    ],
    related: ["onboarding.agent"],
  },
};

export function getHelpEntry(id: HelpId): HelpEntry {
  return HELP_ENTRIES[id];
}
