export type AgentMode = { name: string; write: boolean };

export function validateModes(modes: AgentMode[]): string | null {
  if (modes.some((mode) => !mode.name.trim())) return "Mode names cannot be blank.";
  const names = modes.map((mode) => mode.name.trim().toLowerCase());
  if (new Set(names).size !== names.length) return "Mode names must be unique.";
  return null;
}

export function validateMcpUrl(value: string): string | null {
  try {
    const url = new URL(value);
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      return "MCP URLs must use http or https.";
    }
    return null;
  } catch {
    return "Enter a valid http/https MCP URL.";
  }
}
