import { describe, expect, test } from "bun:test";
import { buildReportModel, determineExitCode } from "./report";
import type { Finding, ScannerResult } from "./model";
import { makeGit, makeScanner } from "./test-helpers";

function finding(partial: Partial<Finding>): Finding {
  return {
    id: "id",
    section: "sast",
    ecosystem: "python",
    tool: "Bandit",
    severity: "low",
    sourceSeverity: "LOW",
    ruleId: "B101",
    title: "title",
    detail: null,
    ...partial,
  };
}

function build(tools: ScannerResult[]) {
  return buildReportModel({
    reportId: "agentbox-security-abc",
    classification: "Internal",
    generatedAt: new Date("2026-11-22T12:00:00Z"),
    scanStartedAt: new Date("2026-11-22T11:59:00Z"),
    scanFinishedAt: new Date("2026-11-22T12:00:00Z"),
    projectName: "demo",
    root: "/repo",
    git: makeGit(),
    components: [],
    lockfiles: [],
    tools,
  });
}

describe("buildReportModel", () => {
  test("groups findings and excludes suppressed findings from counts", () => {
    const model = build([
      makeScanner({
        findings: [
          finding({ section: "sca", severity: "critical", tool: "PySentry" }),
          finding({ section: "sast", severity: "high" }),
          finding({ section: "sast", severity: "high", suppressed: "ignored_package" }),
        ],
      }),
    ]);
    expect(model.sections.sca.findings).toHaveLength(1);
    expect(model.sections.sast.findings).toHaveLength(2);
    expect(model.sections.sast.severityCounts.high).toBe(1);
    expect(model.schemaVersion).toBe(1);
    expect(model.limitations.length).toBeGreaterThan(0);
  });
});

describe("determineExitCode", () => {
  test("returns 0 when clean", () => {
    const model = build([makeScanner()]);
    expect(determineExitCode(model, { allowPartial: false, failOn: "none" }, false)).toBe(0);
  });

  test("returns 3 when the gate is met", () => {
    const model = build([
      makeScanner({ findings: [finding({ severity: "critical", section: "sca" })] }),
    ]);
    expect(determineExitCode(model, { allowPartial: false, failOn: "high" }, false)).toBe(3);
  });

  test("returns 1 for partial scans unless allowed", () => {
    const model = build([makeScanner({ status: "partial" })]);
    expect(determineExitCode(model, { allowPartial: false, failOn: "none" }, false)).toBe(1);
    expect(determineExitCode(model, { allowPartial: true, failOn: "none" }, false)).toBe(0);
  });

  test("returns 1 when every scanner failed, even when partials are allowed", () => {
    const model = build([
      makeScanner({ status: "failed" }),
      makeScanner({ status: "failed" }),
    ]);
    expect(determineExitCode(model, { allowPartial: true, failOn: "none" }, false)).toBe(1);
  });

  test("returns 1 when PDF failed", () => {
    const model = build([makeScanner()]);
    expect(determineExitCode(model, { allowPartial: true, failOn: "none" }, true)).toBe(1);
  });
});
