import { describe, expect, test } from "bun:test";
import type { Finding } from "./model";
import { makeFindingId } from "./model";
import {
  countAtOrAbove,
  countSeverities,
  normalizeSeverity,
  sortFindings,
} from "./severity";

function finding(partial: Partial<Finding>): Finding {
  return {
    id: "id",
    section: "sast",
    ecosystem: "python",
    tool: "tool",
    severity: "low",
    sourceSeverity: "LOW",
    ruleId: "B101",
    title: "title",
    detail: null,
    ...partial,
  };
}

describe("normalizeSeverity", () => {
  test("maps every scanner vocabulary", () => {
    expect(normalizeSeverity("CRITICAL")).toBe("critical");
    expect(normalizeSeverity("HIGH")).toBe("high");
    expect(normalizeSeverity("MEDIUM")).toBe("medium");
    expect(normalizeSeverity("moderate")).toBe("medium");
    expect(normalizeSeverity("Warning")).toBe("medium");
    expect(normalizeSeverity("LOW")).toBe("low");
    expect(normalizeSeverity("Information")).toBe("info");
    expect(normalizeSeverity("unknown")).toBe("unknown");
    expect(normalizeSeverity("")).toBe("unknown");
    expect(normalizeSeverity(null)).toBe("unknown");
  });
});

describe("countSeverities", () => {
  test("counts and excludes suppressed findings", () => {
    const counts = countSeverities([
      finding({ severity: "critical" }),
      finding({ severity: "high" }),
      finding({ severity: "high", suppressed: "ignored_package" }),
    ]);
    expect(counts.critical).toBe(1);
    expect(counts.high).toBe(1);
    expect(counts.low).toBe(0);
  });
});

describe("sortFindings", () => {
  test("sorts by severity then target then rule", () => {
    const sorted = sortFindings([
      finding({ severity: "low", file: "b.ts", ruleId: "B2" }),
      finding({ severity: "critical", file: "z.ts", ruleId: "B1" }),
      finding({ severity: "low", file: "a.ts", ruleId: "B2" }),
    ]);
    expect(sorted.map((item) => item.file)).toEqual(["z.ts", "a.ts", "b.ts"]);
  });
});

describe("countAtOrAbove", () => {
  test("counts only non-suppressed findings at or above the threshold", () => {
    expect(
      countAtOrAbove(
        [
          finding({ severity: "critical" }),
          finding({ severity: "high" }),
          finding({ severity: "medium" }),
          finding({ severity: "high", suppressed: "ignored_package" }),
        ],
        "high",
      ),
    ).toBe(2);
  });
});

describe("makeFindingId", () => {
  test("is stable and target-specific", () => {
    const base = { tool: "Bandit", ruleId: "B101", title: "assert", file: "a.py", line: 4 };
    expect(makeFindingId(base)).toBe(makeFindingId(base));
    expect(makeFindingId(base)).not.toBe(makeFindingId({ ...base, line: 5 }));
    expect(makeFindingId(base)).toHaveLength(12);
  });
});
