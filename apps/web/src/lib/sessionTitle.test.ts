import { describe, expect, it } from "vitest";

import { sessionTitle, UNTITLED_SESSION_TITLE } from "./sessionTitle";

describe("sessionTitle", () => {
  it("uses the trimmed title when present", () => {
    expect(sessionTitle("  Release plan  ")).toBe("Release plan");
  });

  it("falls back for empty, whitespace, and missing titles", () => {
    expect(sessionTitle("")).toBe(UNTITLED_SESSION_TITLE);
    expect(sessionTitle("   ")).toBe(UNTITLED_SESSION_TITLE);
    expect(sessionTitle(null)).toBe(UNTITLED_SESSION_TITLE);
  });
});
