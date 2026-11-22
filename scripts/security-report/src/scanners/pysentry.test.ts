import { describe, expect, test } from "bun:test";
import { parsePysentry } from "./pysentry";

const fixture = {
  scan_time: "2026-11-22T10:00:00Z",
  total_packages: 10,
  vulnerable_packages: 2,
  total_vulnerabilities: 3,
  vulnerabilities: [
    {
      package_name: "requests",
      installed_version: "2.0.0",
      is_direct: true,
      id: "GHSA-high",
      summary: "High issue",
      description: "Details",
      severity: "high",
      affected_versions: [{ constraint: ">=2.0.0,<2.1.0" }],
      fixed_versions: ["2.1.0"],
      references: ["https://example.com/advisory", "javascript:alert(1)"],
      aliases: [],
      cvss_score: 7.5,
    },
    {
      package_name: "flask",
      installed_version: "1.0.0",
      is_direct: false,
      id: "GHSA-low",
      summary: "Low issue",
      description: null,
      severity: "low",
      affected_versions: [],
      fixed_versions: [],
      references: [],
    },
    {
      package_name: "old",
      installed_version: "0.1.0",
      is_direct: true,
      id: "GHSA-suppressed",
      summary: "Suppressed issue",
      description: null,
      severity: "critical",
      affected_versions: [],
      fixed_versions: [],
      references: [],
      suppressed: "ignored_package",
    },
  ],
  fix_suggestions: [
    {
      package_name: "requests",
      current_version: "2.0.0",
      suggested_version: "2.1.0",
      vulnerability_id: "GHSA-high",
    },
  ],
  warnings: ["cache stale"],
  maintenance_issues: [
    {
      package_name: "old",
      installed_version: "0.1.0",
      issue_type: "deprecated",
      reason: "Use new-lib",
      is_direct: true,
      source_file: "uv.lock",
    },
  ],
  partial: true,
  failed_sources: ["osv"],
  failing: null,
};

describe("parsePysentry", () => {
  test("normalizes findings, fixes, maintenance, and partial state", () => {
    const parsed = parsePysentry(fixture);
    expect(parsed.findings).toHaveLength(3);
    expect(parsed.partial).toBe(true);
    expect(parsed.errors).toContain("Vulnerability source failed: osv");
    expect(parsed.stats.totalPackages).toBe(10);
    expect(parsed.stats.vulnerablePackages).toBe(2);

    const high = parsed.findings.find((finding) => finding.ruleId === "GHSA-high");
    expect(high?.severity).toBe("high");
    expect(high?.packageName).toBe("requests");
    expect(high?.installedVersion).toBe("2.0.0");
    expect(high?.vulnerableRange).toBe(">=2.0.0,<2.1.0");
    expect(high?.referenceUrl).toBe("https://example.com/advisory");
    expect(high?.fix).toBe("Upgrade to 2.1.0");
    expect(high?.id).toHaveLength(12);

    const suppressed = parsed.findings.find((finding) => finding.ruleId === "GHSA-suppressed");
    expect(suppressed?.suppressed).toBe("ignored_package");
    expect(parsed.maintenance[0]?.issueType).toBe("deprecated");
  });
});
