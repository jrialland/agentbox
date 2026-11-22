import { describe, expect, test } from "bun:test";
import { parseArgs } from "./cli";

describe("parseArgs", () => {
  test("parses defaults", () => {
    const options = parseArgs([]);
    expect(options.projectPath).toBeNull();
    expect(options.outDir).toBe("reports/security");
    expect(options.classification).toBe("Internal");
    expect(options.failOn).toBe("none");
    expect(options.allowPartial).toBe(false);
    expect(options.noPdf).toBe(false);
    expect(options.includeTests).toBe(false);
    expect(options.excludes).toEqual([]);
    expect(options.scannerTimeout).toBe(300);
    expect(options.fromFixtures).toBeNull();
    expect(options.help).toBe(false);
  });

  test("parses values and flags", () => {
    const options = parseArgs([
      ".",
      "--out",
      "out",
      "--classification",
      "Confidential",
      "--fail-on",
      "high",
      "--allow-partial",
      "--no-pdf",
      "--include-tests",
      "--exclude",
      "**/vendor/**",
      "--scanner-timeout",
      "60",
      "--from-fixtures",
      "fixtures",
    ]);
    expect(options.projectPath).toBe(".");
    expect(options.outDir).toBe("out");
    expect(options.classification).toBe("Confidential");
    expect(options.failOn).toBe("high");
    expect(options.allowPartial).toBe(true);
    expect(options.noPdf).toBe(true);
    expect(options.includeTests).toBe(true);
    expect(options.excludes).toEqual(["**/vendor/**"]);
    expect(options.scannerTimeout).toBe(60);
    expect(options.fromFixtures).toBe("fixtures");
  });

  test("rejects unknown options and bad values", () => {
    expect(() => parseArgs(["--nope"])).toThrow("Unknown option");
    expect(() => parseArgs(["--fail-on", "severe"])).toThrow("Invalid --fail-on");
    expect(() => parseArgs(["--scanner-timeout", "0"])).toThrow("Invalid --scanner-timeout");
    expect(() => parseArgs(["--out"])).toThrow("Missing value for --out");
  });
});
