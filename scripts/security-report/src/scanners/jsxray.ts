import { readFileSync } from "node:fs";
import { extname } from "node:path";
import {
  AstAnalyser,
  JsSourceParser,
  TsSourceParser,
  i18nLocation,
} from "@nodesecure/js-x-ray";
import * as i18n from "@nodesecure/i18n";
import { makeFindingId, type Finding, type ScannerResult } from "../model";
import { displayPath } from "../render/components";
import { normalizeSeverity } from "../severity";
import { walkSourceFiles } from "../project";
import type { ScanContext } from "./types";

const TS_EXTENSIONS = new Set([".ts", ".tsx", ".mts", ".cts"]);

export interface JsxrayWarning {
  kind: string;
  severity: string;
  value?: string | null;
  source?: string;
  i18n?: string;
  experimental?: boolean;
  location?: unknown;
}

export function locationStart(
  location: unknown,
): { line?: number; column?: number } {
  if (!Array.isArray(location) || location.length === 0) return {};
  const first = location[0];

  if (
    Array.isArray(first) &&
    first.length >= 2 &&
    typeof first[0] === "number"
  ) {
    return { line: first[0], column: first[1] };
  }

  if (Array.isArray(first) && Array.isArray(first[0])) {
    const start = first[0];
    if (start.length >= 2 && typeof start[0] === "number") {
      return { line: start[0], column: start[1] };
    }
  }

  return {};
}

export function parseJsxrayWarnings(
  warnings: JsxrayWarning[],
  file: string,
  root: string,
  describe: (warning: JsxrayWarning) => string | null,
): Finding[] {
  return warnings.map((warning) => {
    const title = describe(warning) ?? warning.kind;
    const position = locationStart(warning.location);
    const relative = displayPath(root, file) ?? file;
    return {
      id: makeFindingId({
        tool: "JS-X-Ray",
        ruleId: warning.kind,
        title,
        file: relative,
        line: position.line,
      }),
      section: "sast",
      ecosystem: "javascript",
      tool: "JS-X-Ray",
      severity: normalizeSeverity(warning.severity),
      sourceSeverity: warning.severity,
      ruleId: warning.kind,
      title,
      detail: warning.value ? `Value: ${warning.value}` : null,
      file: relative,
      line: position.line,
      column: position.column,
    };
  });
}

let i18nReady = false;

async function ensureI18n(): Promise<void> {
  if (i18nReady) return;
  await i18n.extendFromSystemPath(i18nLocation());
  await i18n.getLocalLang();
  i18nReady = true;
}

function describe(warning: JsxrayWarning): string | null {
  if (!warning.i18n) return null;
  try {
    return i18n.getTokenSync(warning.i18n);
  } catch {
    return null;
  }
}

export async function scanJsxray(ctx: ScanContext): Promise<ScannerResult> {
  const started = performance.now();
  const scanner = new AstAnalyser({
    optionalWarnings: ["crypto.*"],
  });
  const findings: Finding[] = [];
  const errors: string[] = [];
  let filesScanned = 0;

  try {
    await ensureI18n();
  } catch {
    // Descriptions fall back to the warning kind.
  }

  for (const component of ctx.jsComponents) {
    const files = walkSourceFiles(component.sourceRoot, {
      includeTests: ctx.includeTests,
      extraExcludes: ctx.extraExcludes,
    });
    for (const file of files) {
      filesScanned += 1;
      try {
        const extension = extname(file);
        const customParser = TS_EXTENSIONS.has(extension)
          ? new TsSourceParser()
          : new JsSourceParser();
        const report = scanner.analyse(readFileSync(file, "utf8"), {
          customParser,
          location: file,
        });
        findings.push(
          ...parseJsxrayWarnings(
            report.warnings as JsxrayWarning[],
            file,
            ctx.root,
            describe,
          ),
        );
      } catch (error) {
        errors.push(
          `${displayPath(ctx.root, file) ?? file}: ${error instanceof Error ? error.message : String(error)}`,
        );
      }
    }
  }

  const filesWithFindings = new Set(
    findings.map((finding) => finding.file).filter(Boolean),
  ).size;

  return {
    tool: "JS-X-Ray",
    version: ctx.versions.jsxray ?? "unknown",
    command: ["js-x-ray", "in-process"],
    status: errors.length > 0 ? "partial" : "ok",
    exitCode: null,
    durationMs: Math.round(performance.now() - started),
    stats: { filesScanned, filesWithFindings },
    warnings: [],
    errors,
    findings,
    maintenance: [],
  };
}
