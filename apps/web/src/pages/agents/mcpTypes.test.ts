import { describe, expect, test } from "vitest";

import { fromBinding, toBinding, validateMcpServers } from "./mcpTypes";

describe("mcpTypes", () => {
  test("round-trips a stdio binding", () => {
    const draft = fromBinding({
      id: "time",
      command: "uvx",
      args: ["mcp-server-time"],
      env: { TZ: "UTC" },
      env_passthrough: ["PATH"],
      cwd: "sub",
    });
    expect(draft?.kind).toBe("stdio");
    expect(toBinding(draft!)).toEqual({
      id: "time",
      command: "uvx",
      args: ["mcp-server-time"],
      env: { TZ: "UTC" },
      env_passthrough: ["PATH"],
      cwd: "sub",
    });
  });

  test("round-trips a remote binding", () => {
    const draft = fromBinding({ id: "app", server_url: "https://x/mcp" });
    expect(draft?.kind).toBe("remote");
    expect(toBinding(draft!)).toEqual({ id: "app", server_url: "https://x/mcp" });
  });

  test("rejects duplicate stdio ids", () => {
    const base = fromBinding({ id: "a", command: "python" })!;
    const error = validateMcpServers([base, { ...base }]);
    expect(error).toContain("unique");
  });
});
