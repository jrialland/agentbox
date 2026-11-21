import { describe, expect, it } from "vitest";

import { EMPTY_PROVIDER_DRAFT, applyProviderPreset } from "./providerPresets";

describe("applyProviderPreset", () => {
  it("fills untouched URLs", () => {
    const next = applyProviderPreset(
      { ...EMPTY_PROVIDER_DRAFT, kind: "generic" },
      "deepseek",
    );
    expect(next.baseUrl).toBe("https://api.deepseek.com/v1");
    expect(next.modelsUrl).toBe("https://api.deepseek.com/v1/models");
  });

  it("preserves custom URLs", () => {
    const current = {
      ...EMPTY_PROVIDER_DRAFT,
      kind: "generic",
      baseUrl: "https://custom.test/v1",
    };
    const next = applyProviderPreset(current, "openai_legacy");
    expect(next.baseUrl).toBe("https://custom.test/v1");
    expect(next.modelsUrl).toBe("https://api.openai.com/v1/models");
  });

  it("replaces a previous preset URL when switching kinds", () => {
    const current = applyProviderPreset(
      { ...EMPTY_PROVIDER_DRAFT, kind: "generic" },
      "deepseek",
    );
    const next = applyProviderPreset(current, "moonshot");
    expect(next.baseUrl).toBe("https://api.moonshot.cn/v1");
  });
});
