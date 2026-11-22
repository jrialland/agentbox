import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  makeFindingId,
  type Finding,
  type MaintenanceIssue,
  type ScannerResult,
} from "../model";
import { safeUrl } from "../render/components";
import { normalizeSeverity } from "../severity";
import { runProcess, tail } from "./process";
import type { ParsedScanner, ScanContext } from "./types";

interface PysentryVulnerability {
  package_name: string;
  installed_version: string;
  is_direct?: boolean;
  id: string;
  summary: string;
  description?: string | null;
  severity: string;
  affected_versions?: Array<{ constraint?: string } | string>;
  fixed_versions?: Array<string | { version?: string }>;
  references?: string[];
  suppressed?: string | null;
}

interface PysentryFix {
  package_name: string;
  current_version: string;
  suggested_version: string;
  vulnerability_id: string;
}

interface PysentryMaintenance {
  package_name: string;
  installed_version: string;
  issue_type: string;
  reason?: string | null;
  is_direct?: boolean;
}

export interface PysentryJson {
  scan_time?: string;
  total_packages?: number;
  vulnerable_packages?: number;
  total_vulnerabilities?: number;
  vulnerabilities?: PysentryVulnerability[];
  fix_suggestions?: PysentryFix[];
  warnings?: string[];
  maintenance_issues?: PysentryMaintenance[];
  partial?: boolean;
  failed_sources?: string[];
}

function fixedVersions(value: PysentryVulnerability["fixed_versions"]): string[] {
  return (value ?? [])
    .map((item) => (typeof item === "string" ? item : item?.version))
    .filter((item): item is string => typeof item === "string" && item.length > 0);
}

function ranges(value: PysentryVulnerability["affected_versions"]): string {
  return (value ?? [])
    .map((item) => (typeof item === "string" ? item : item?.constraint))
    .filter((item): item is string => typeof item === "string" && item.length > 0)
    .join(", ");
}

export function parsePysentry(json: PysentryJson): ParsedScanner {
  const fixes = new Map<string, string>();
  for (const fix of json.fix_suggestions ?? []) {
    fixes.set(`${fix.package_name}|${fix.vulnerability_id}`, fix.suggested_version);
  }

  const findings: Finding[] = (json.vulnerabilities ?? []).map((vulnerability) => {
    const severity = normalizeSeverity(vulnerability.severity);
    const reference = (vulnerability.references ?? [])
      .map((url) => safeUrl(url))
      .find((url): url is string => url !== null) ?? null;
    const suggested = fixes.get(
      `${vulnerability.package_name}|${vulnerability.id}`,
    );
    const fixed = fixedVersions(vulnerability.fixed_versions);
    const fix = suggested
      ? `Upgrade to ${suggested}`
      : fixed.length > 0
        ? `Upgrade to ${fixed.join(" or ")}`
        : null;

    return {
      id: makeFindingId({
        tool: "PySentry",
        ruleId: vulnerability.id,
        title: vulnerability.summary,
        packageName: vulnerability.package_name,
        line: 0,
      }),
      section: "sca",
      ecosystem: "python",
      tool: "PySentry",
      severity,
      sourceSeverity: vulnerability.severity,
      ruleId: vulnerability.id,
      title: vulnerability.summary,
      detail: vulnerability.description ?? null,
      packageName: vulnerability.package_name,
      installedVersion: vulnerability.installed_version,
      vulnerableRange: ranges(vulnerability.affected_versions) || undefined,
      referenceUrl: reference,
      fix,
      suppressed: vulnerability.suppressed ?? null,
    };
  });

  const maintenance: MaintenanceIssue[] = (json.maintenance_issues ?? []).map(
    (issue) => ({
      packageName: issue.package_name,
      installedVersion: issue.installed_version,
      issueType: issue.issue_type,
      reason: issue.reason ?? null,
      isDirect: issue.is_direct ?? false,
    }),
  );

  const failedSources = json.failed_sources ?? [];
  return {
    findings,
    stats: {
      totalPackages: json.total_packages ?? 0,
      vulnerablePackages: json.vulnerable_packages ?? 0,
      totalVulnerabilities: json.total_vulnerabilities ?? findings.length,
      fixable: fixes.size,
      maintenanceIssues: maintenance.length,
    },
    warnings: json.warnings ?? [],
    errors: failedSources.map((source) => `Vulnerability source failed: ${source}`),
    partial: Boolean(json.partial) || failedSources.length > 0,
    maintenance,
  };
}

export async function scanPysentry(ctx: ScanContext): Promise<ScannerResult> {
  const dir = mkdtempSync(join(tmpdir(), "pysentry-report-"));
  const output = join(dir, "report.json");
  const command = ["uvx", "pysentry-rs", ctx.root, "--format", "json", "--output", output];

  let parsed: ParsedScanner | null = null;
  const errors: string[] = [];
  try {
    const result = await runProcess("uvx", command.slice(1), {
      cwd: ctx.root,
      timeoutMs: ctx.timeoutMs,
    });

    try {
      parsed = parsePysentry(JSON.parse(readFileSync(output, "utf8")) as PysentryJson);
    } catch (error) {
      errors.push(
        `Invalid PySentry JSON: ${error instanceof Error ? error.message : String(error)}`,
      );
      if (result.stderr.trim()) errors.push(tail(result.stderr));
    }

    const accepted =
      result.exitCode === 0 ||
      ((result.exitCode === 1 || result.exitCode === 2) && parsed !== null);
    const status = !accepted || parsed === null
      ? "failed"
      : result.exitCode === 2 || parsed.partial
        ? "partial"
        : "ok";

    return {
      tool: "PySentry",
      version: ctx.versions.pysentry ?? "unknown",
      command,
      status,
      exitCode: result.exitCode,
      durationMs: result.durationMs,
      stats: parsed?.stats ?? {},
      warnings: parsed?.warnings ?? [],
      errors: [...errors, ...(parsed?.errors ?? [])],
      findings: parsed?.findings ?? [],
      maintenance: parsed?.maintenance ?? [],
    };
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}
