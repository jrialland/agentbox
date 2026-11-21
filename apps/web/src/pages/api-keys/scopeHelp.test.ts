import { describe, expect, it } from "vitest";

import { RECOMMENDED_SCOPES, describeScope } from "./scopeHelp";

describe("scope help", () => {
  it("describes known scopes and falls back safely", () => {
    expect(describeScope("sessions:create")).toContain("Create");
    expect(describeScope("custom:thing")).toBe("custom:thing");
    expect(RECOMMENDED_SCOPES).toContain("providers:read");
  });
});
