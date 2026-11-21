import { describe, expect, it } from "vitest";

import { TOOL_GROUPS, TOOL_META } from "./toolCatalog";

describe("tool catalog", () => {
  it("catalogs every selectable tool", () => {
    expect(TOOL_META.read_text_file.category).toBe("filesystem-read");
    expect(TOOL_META.write_file.risk).toBe("write");
    expect(TOOL_META.web_search.category).toBe("web");
    expect(TOOL_GROUPS.map((group) => group.category)).toContain("terminal");
  });

  it("catalogs grep as a content-search read tool", () => {
    expect(TOOL_META.grep.category).toBe("filesystem-read");
    expect(TOOL_META.grep.risk).toBe("read");
    expect(TOOL_META.grep.label).toMatch(/grep/i);
  });
});
