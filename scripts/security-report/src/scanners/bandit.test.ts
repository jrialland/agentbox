import { describe, expect, test } from "bun:test";
import { banditArgs, parseBandit } from "./bandit";
import type { ScanContext } from "./types";

const json = {
  results: [
    {
      filename: "/repo/packages/a/src/a.py",
      line_number: 4,
      col_offset: 0,
      issue_severity: "HIGH",
      issue_confidence: "MEDIUM",
      issue_text: "Use of eval",
      test_id: "B307",
      test_name: "blacklist",
      more_info: "https://bandit.readthedocs.io/b307",
    },
    {
      filename: "/repo/packages/a/src/b.py",
      line_number: 9,
      issue_severity: "LOW",
      issue_confidence: "HIGH",
      issue_text: "Assert used",
      test_id: "B101",
      test_name: "assert_used",
      more_info: "",
    },
  ],
  metrics: { _totals: { loc: 120, nosec: 0, skipped_tests: 0 } },
  errors: [],
};

function context(includeTests: boolean): ScanContext {
  return {
    root: "/repo",
    pythonRoots: ["/repo/packages/a"],
    jsComponents: [],
    includeTests,
    extraExcludes: [],
    timeoutMs: 1000,
    versions: {},
  };
}

describe("parseBandit", () => {
  test("normalizes findings and stats", () => {
    const parsed = parseBandit(json, "/repo");
    expect(parsed.findings).toHaveLength(2);
    expect(parsed.findings[0]?.severity).toBe("high");
    expect(parsed.findings[0]?.confidence).toBe("MEDIUM");
    expect(parsed.findings[0]?.file).toBe("packages/a/src/a.py");
    expect(parsed.findings[0]?.referenceUrl).toBe("https://bandit.readthedocs.io/b307");
    expect(parsed.findings[1]?.severity).toBe("low");
    expect(parsed.stats.filesWithFindings).toBe(2);
    expect(parsed.stats.loc).toBe(120);
  });
});

describe("banditArgs", () => {
  test("excludes tests by default", () => {
    const args = banditArgs(context(false)).join(" ");
    expect(args).toContain("run bandit -r");
    expect(args).toContain("**/tests/**");
    expect(args).toContain("-f json");
  });

  test("includes tests when asked", () => {
    const args = banditArgs(context(true)).join(" ");
    expect(args).not.toContain("**/tests/**");
  });
});
