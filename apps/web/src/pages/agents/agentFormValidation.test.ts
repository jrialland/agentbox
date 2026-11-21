import { describe, expect, it } from "vitest";

import { validateMcpUrl, validateModes } from "./agentFormValidation";

describe("agent form validation", () => {
  it("rejects blank and duplicate modes", () => {
    expect(validateModes([{ name: " ", write: false }])).toContain("blank");
    expect(
      validateModes([
        { name: "ask", write: false },
        { name: "ask", write: true },
      ]),
    ).toContain("unique");
  });

  it("accepts http and https MCP URLs", () => {
    expect(validateMcpUrl("https://example.test/mcp")).toBeNull();
    expect(validateMcpUrl("http://localhost:9000/mcp")).toBeNull();
    expect(validateMcpUrl("ftp://example.test")).toContain("http");
  });
});
