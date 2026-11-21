import { describe, expect, it } from "vitest";

import {
  EMPTY_A2A_CARD,
  mergeStructuredCard,
  parseCardJson,
  toStructuredCard,
  validateStructuredCard,
} from "./a2aCard";

describe("a2aCard", () => {
  it("preserves unknown fields when merging", () => {
    const raw = { name: "Old", version: "1.0.0", securitySchemes: { api: {} } };
    const merged = mergeStructuredCard(raw, {
      ...EMPTY_A2A_CARD,
      name: "Reviewer",
      version: "1.2.0",
      skills: [
        { id: "review", name: "Review", description: "", tags: [], examples: [] },
      ],
    });
    expect(merged.name).toBe("Reviewer");
    expect(merged.securitySchemes).toEqual({ api: {} });
  });

  it("reads core fields from a raw card", () => {
    const card = toStructuredCard(
      {
        name: "Reviewer",
        description: "Reviews code",
        version: "1.0.0",
        capabilities: { streaming: true },
        skills: [{ id: "review", name: "Review" }],
      },
      "Fallback",
    );
    expect(card.name).toBe("Reviewer");
    expect(card.capabilities.streaming).toBe(true);
    expect(card.skills[0].id).toBe("review");
  });

  it("rejects duplicate skill ids and invalid URLs", () => {
    const errors = validateStructuredCard({
      ...EMPTY_A2A_CARD,
      name: "A",
      version: "1.0.0",
      documentationUrl: "not-a-url",
      skills: [
        { id: "x", name: "One", description: "", tags: [], examples: [] },
        { id: "x", name: "Two", description: "", tags: [], examples: [] },
      ],
    });
    expect(errors.documentationUrl).toBeTruthy();
    expect(errors.skills).toContain("unique");
  });

  it("parses valid JSON and rejects malformed JSON", () => {
    expect(parseCardJson('{"name":"A"}').card).toEqual({ name: "A" });
    expect(parseCardJson("{bad").error).toBeTruthy();
  });
});
