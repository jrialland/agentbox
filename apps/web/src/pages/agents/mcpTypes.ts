export type McpServerDraft = {
  id: string;
  kind: "remote" | "stdio";
  server_url: string;
  command: string;
  args: string;
  env: { name: string; value: string }[];
  envPassthrough: string;
  cwd: string;
};

export function emptyMcpServer(): McpServerDraft {
  return {
    id: "",
    kind: "remote",
    server_url: "",
    command: "",
    args: "",
    env: [],
    envPassthrough: "",
    cwd: "",
  };
}

export function fromBinding(
  binding: Record<string, unknown>,
): McpServerDraft | null {
  const isStdio = typeof binding.command === "string" && binding.command !== "";
  if (!isStdio && typeof binding.server_url !== "string") return null;
  const env = (binding.env as Record<string, string> | undefined) ?? {};
  const passthrough = (binding.env_passthrough as string[] | undefined) ?? [];
  const args = (binding.args as string[] | undefined) ?? [];
  return {
    id: String(binding.id ?? ""),
    kind: isStdio ? "stdio" : "remote",
    server_url: String(binding.server_url ?? ""),
    command: String(binding.command ?? ""),
    args: args.join("\n"),
    env: Object.entries(env).map(([name, value]) => ({
      name,
      value: String(value),
    })),
    envPassthrough: passthrough.join(", "),
    cwd: String(binding.cwd ?? ""),
  };
}

function splitArgs(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function splitNames(value: string): string[] {
  return value
    .split(/[\n,]/)
    .map((name) => name.trim())
    .filter(Boolean);
}

export function toBinding(draft: McpServerDraft): Record<string, unknown> {
  const id = draft.id.trim();
  if (draft.kind === "remote") {
    return id
      ? { id, server_url: draft.server_url.trim() }
      : { server_url: draft.server_url.trim() };
  }
  const env = Object.fromEntries(
    draft.env
      .filter((row) => row.name.trim())
      .map((row) => [row.name.trim(), row.value]),
  );
  return {
    id,
    command: draft.command.trim(),
    args: splitArgs(draft.args),
    env,
    env_passthrough: splitNames(draft.envPassthrough),
    cwd: draft.cwd.trim(),
  };
}

const ENV_NAME = /^[A-Za-z_][A-Za-z0-9_]*$/;

export function validateMcpServers(drafts: McpServerDraft[]): string | null {
  const ids: string[] = [];
  for (const draft of drafts) {
    const id = draft.id.trim();
    if (draft.kind === "stdio" && !id) return "Local MCP servers need a name.";
    if (id) ids.push(id);
    if (draft.kind === "remote") {
      try {
        const url = new URL(draft.server_url.trim());
        if (url.protocol !== "http:" && url.protocol !== "https:") {
          return "MCP URLs must use http or https.";
        }
      } catch {
        return "Enter a valid http/https MCP URL.";
      }
    } else if (!draft.command.trim()) {
      return "Local MCP servers need a command.";
    }
    for (const row of draft.env) {
      if (row.name.trim() && !ENV_NAME.test(row.name.trim())) {
        return `Invalid env name: ${row.name}`;
      }
    }
    for (const name of splitNames(draft.envPassthrough)) {
      if (!ENV_NAME.test(name)) return `Invalid env passthrough name: ${name}`;
    }
  }
  if (new Set(ids).size !== ids.length) return "MCP server names must be unique.";
  return null;
}
