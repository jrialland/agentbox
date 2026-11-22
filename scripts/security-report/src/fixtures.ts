import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { GitCoordinates, ScannerResult } from "./model";
import type { ProjectDiscovery } from "./project";
import { parseBandit, type BanditJson } from "./scanners/bandit";
import { parseBunAudit, type BunAdvisory } from "./scanners/bun-audit";
import { parseJsxrayWarnings, type JsxrayWarning } from "./scanners/jsxray";
import { parsePysentry } from "./scanners/pysentry";
import type { ParsedScanner } from "./scanners/types";

function readJson<T>(dir: string, file: string): T {
  return JSON.parse(readFileSync(join(dir, file), "utf8")) as T;
}

function wrap(tool: string, parsed: ParsedScanner, version: string): ScannerResult {
  return {
    tool,
    version,
    command: [],
    status: parsed.partial ? "partial" : "ok",
    exitCode: 0,
    durationMs: 0,
    stats: parsed.stats,
    warnings: parsed.warnings,
    errors: parsed.errors,
    findings: parsed.findings,
    maintenance: parsed.maintenance,
  };
}

export interface FixtureProject {
  git: GitCoordinates;
  project: ProjectDiscovery;
}

export function loadFixtureProject(dir: string): FixtureProject {
  return {
    git: readJson<GitCoordinates>(dir, "git.json"),
    project: readJson<ProjectDiscovery>(dir, "project.json"),
  };
}

export async function loadFixtureResults(
  dir: string,
  project: ProjectDiscovery,
): Promise<ScannerResult[]> {
  const results: ScannerResult[] = [];
  results.push(wrap("PySentry", parsePysentry(readJson(dir, "pysentry.json")), "fixture"));
  results.push(
    wrap(
      "Bandit",
      parseBandit(readJson<BanditJson>(dir, "bandit.json"), project.root),
      "fixture",
    ),
  );
  results.push(
    wrap(
      "Bun audit",
      parseBunAudit(
        readJson<Record<string, BunAdvisory[]>>(dir, "bun-audit.json"),
        project.lockfiles[0]?.resolvedVersions ?? {},
      ),
      "fixture",
    ),
  );

  const jsxrayFixture = readJson<
    Array<JsxrayWarning & { file: string; description?: string | null }>
  >(dir, "jsxray.json");
  const jsxrayFindings = jsxrayFixture.flatMap((warning) =>
    parseJsxrayWarnings(
      [warning],
      warning.file,
      project.root,
      () => warning.description ?? warning.kind,
    ),
  );
  results.push({
    tool: "JS-X-Ray",
    version: "fixture",
    command: [],
    status: "ok",
    exitCode: null,
    durationMs: 0,
    stats: {
      filesScanned: new Set(jsxrayFixture.map((warning) => warning.file)).size,
    },
    warnings: [],
    errors: [],
    findings: jsxrayFindings,
    maintenance: [],
  });

  return results;
}
