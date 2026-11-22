import { makeFindingId, type Finding, type ScannerResult } from "../model";
import { safeUrl } from "../render/components";
import { normalizeSeverity } from "../severity";
import { runProcess, tail } from "./process";
import type { ParsedScanner, ScanContext } from "./types";

export interface BunAdvisory {
  id: number | string;
  url?: string;
  title?: string;
  severity?: string;
  vulnerable_versions?: string;
  cwe?: string[];
  cvss?: { score?: number; vectorString?: string | null };
}

interface NpmAdvisory {
  source?: number | string;
  title?: string;
  url?: string;
  severity?: string;
  range?: string;
  cvss?: { vectorString?: string | null };
}

interface NpmVulnerability {
  name?: string;
  severity?: string;
  range?: string;
  via?: Array<string | NpmAdvisory>;
  fixAvailable?: boolean | { name?: string; version?: string };
}

export function parseBunAudit(
  json: Record<string, BunAdvisory[]>,
  versions: Record<string, string>,
): ParsedScanner {
  const findings: Finding[] = [];
  for (const [packageName, advisories] of Object.entries(json)) {
    for (const advisory of advisories ?? []) {
      const title = advisory.title ?? `Vulnerability in ${packageName}`;
      const ruleId = String(advisory.id);
      findings.push({
        id: makeFindingId({ tool: "Bun audit", ruleId, title, packageName }),
        section: "sca",
        ecosystem: "javascript",
        tool: "Bun audit",
        severity: normalizeSeverity(advisory.severity),
        sourceSeverity: advisory.severity ?? "unknown",
        ruleId,
        title,
        detail: advisory.cwe?.length ? advisory.cwe.join(", ") : null,
        packageName,
        installedVersion: versions[packageName],
        vulnerableRange: advisory.vulnerable_versions,
        referenceUrl: safeUrl(advisory.url),
      });
    }
  }

  return {
    findings,
    stats: {
      affectedPackages: Object.keys(json).length,
      advisories: findings.length,
    },
    warnings: [],
    errors: [],
    partial: false,
    maintenance: [],
  };
}

export function parseNpmAudit(
  json: { vulnerabilities?: Record<string, NpmVulnerability> },
  versions: Record<string, string>,
): ParsedScanner {
  const findings: Finding[] = [];
  for (const [packageName, vulnerability] of Object.entries(json.vulnerabilities ?? {})) {
    const advisories = (vulnerability.via ?? []).filter(
      (item): item is NpmAdvisory => typeof item === "object" && item !== null,
    );

    const fix =
      vulnerability.fixAvailable === true
        ? "Run npm audit fix"
        : typeof vulnerability.fixAvailable === "object" &&
            vulnerability.fixAvailable?.version
          ? `Upgrade ${vulnerability.fixAvailable.name ?? packageName} to ${vulnerability.fixAvailable.version}`
          : null;

    if (advisories.length === 0) {
      const title = `Vulnerable dependency: ${packageName}`;
      findings.push({
        id: makeFindingId({ tool: "NPM audit", ruleId: null, title, packageName }),
        section: "sca",
        ecosystem: "javascript",
        tool: "NPM audit",
        severity: normalizeSeverity(vulnerability.severity),
        sourceSeverity: vulnerability.severity ?? "unknown",
        ruleId: null,
        title,
        detail: null,
        packageName,
        installedVersion: versions[packageName],
        vulnerableRange: vulnerability.range,
        fix,
      });
      continue;
    }

    for (const advisory of advisories) {
      const title = advisory.title ?? `Vulnerability in ${packageName}`;
      const ruleId = advisory.source != null ? String(advisory.source) : null;
      findings.push({
        id: makeFindingId({ tool: "NPM audit", ruleId, title, packageName }),
        section: "sca",
        ecosystem: "javascript",
        tool: "NPM audit",
        severity: normalizeSeverity(advisory.severity ?? vulnerability.severity),
        sourceSeverity: advisory.severity ?? vulnerability.severity ?? "unknown",
        ruleId,
        title,
        detail: advisory.cvss?.vectorString ?? null,
        packageName,
        installedVersion: versions[packageName],
        vulnerableRange: advisory.range ?? vulnerability.range,
        referenceUrl: safeUrl(advisory.url),
        fix,
      });
    }
  }

  return {
    findings,
    stats: {
      affectedPackages: Object.keys(json.vulnerabilities ?? {}).length,
      advisories: findings.length,
    },
    warnings: [],
    errors: [],
    partial: false,
    maintenance: [],
  };
}

export async function scanJsSca(ctx: ScanContext): Promise<ScannerResult[]> {
  const results: ScannerResult[] = [];

  for (const component of ctx.jsComponents) {
    const isBun = component.lockfileKind === "bun";
    const command = isBun ? "bun" : "npm";
    const args = ["audit", "--json"];
    const result = await runProcess(command, args, {
      cwd: component.dir,
      timeoutMs: ctx.timeoutMs,
    });

    let parsed: ParsedScanner | null = null;
    const errors: string[] = [];
    try {
      const json = JSON.parse(result.stdout) as unknown;
      parsed = isBun
        ? parseBunAudit(json as Record<string, BunAdvisory[]>, component.resolvedVersions)
        : parseNpmAudit(
            json as { vulnerabilities?: Record<string, NpmVulnerability> },
            component.resolvedVersions,
          );
    } catch (error) {
      errors.push(
        `Invalid ${isBun ? "Bun" : "NPM"} audit JSON: ${error instanceof Error ? error.message : String(error)}`,
      );
      if (result.stderr.trim()) errors.push(tail(result.stderr));
    }

    const accepted = result.exitCode === 0 || (result.exitCode === 1 && parsed !== null);
    const status = !accepted || parsed === null ? "failed" : "ok";
    const tool = isBun ? "Bun audit" : "NPM audit";

    results.push({
      tool,
      version: ctx.versions[isBun ? "bun" : "npm"] ?? "unknown",
      command: [command, ...args],
      status,
      exitCode: result.exitCode,
      durationMs: result.durationMs,
      stats: { ...(parsed?.stats ?? {}), packages: component.packageCount },
      warnings: parsed?.warnings ?? [],
      errors: [...errors, ...(parsed?.errors ?? [])],
      findings: parsed?.findings ?? [],
      maintenance: [],
    });
  }

  return results;
}
