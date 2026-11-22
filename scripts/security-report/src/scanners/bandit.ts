import { makeFindingId, type Finding, type ScannerResult } from "../model";
import { displayPath, safeUrl } from "../render/components";
import { normalizeSeverity } from "../severity";
import { runProcess, tail } from "./process";
import type { ParsedScanner, ScanContext } from "./types";

interface BanditResult {
  filename: string;
  line_number: number;
  col_offset?: number;
  issue_severity: string;
  issue_confidence: string;
  issue_text: string;
  test_id: string;
  test_name: string;
  more_info?: string;
}

export interface BanditJson {
  results?: BanditResult[];
  metrics?: { _totals?: { loc?: number } };
  errors?: Array<{ filename?: string; reason?: string }>;
}

const BASE_EXCLUDES = [
  "**/.venv/**",
  "**/venv/**",
  "**/__pycache__/**",
  "**/.pytest_cache/**",
  "**/.ruff_cache/**",
  "**/.mypy_cache/**",
  "**/site-packages/**",
];

const TEST_EXCLUDES = ["**/tests/**", "**/fixtures/**"];

export function parseBandit(json: BanditJson, root: string): ParsedScanner {
  const results = json.results ?? [];
  const findings: Finding[] = results.map((result) => {
    const file = displayPath(root, result.filename) ?? result.filename;
    return {
      id: makeFindingId({
        tool: "Bandit",
        ruleId: result.test_id,
        title: result.issue_text,
        file,
        line: result.line_number,
      }),
      section: "sast",
      ecosystem: "python",
      tool: "Bandit",
      severity: normalizeSeverity(result.issue_severity),
      sourceSeverity: result.issue_severity,
      ruleId: result.test_id,
      title: result.issue_text,
      detail: `${result.test_name} (${result.issue_confidence} confidence)`,
      file,
      line: result.line_number,
      column: result.col_offset,
      confidence: result.issue_confidence,
      referenceUrl: safeUrl(result.more_info),
    };
  });

  const files = new Set(findings.map((finding) => finding.file).filter(Boolean));
  return {
    findings,
    stats: {
      filesWithFindings: files.size,
      loc: json.metrics?._totals?.loc ?? 0,
      issues: findings.length,
    },
    warnings: [],
    errors: (json.errors ?? []).map(
      (error) => `${error.filename ?? "unknown"}: ${error.reason ?? "error"}`,
    ),
    partial: false,
    maintenance: [],
  };
}

export function banditArgs(ctx: ScanContext): string[] {
  const excludes = [...BASE_EXCLUDES, ...(ctx.includeTests ? [] : TEST_EXCLUDES)];
  return [
    "run",
    "bandit",
    "-r",
    ...ctx.pythonRoots,
    "-x",
    excludes.join(","),
    "-f",
    "json",
    "-q",
  ];
}

export async function scanBandit(ctx: ScanContext): Promise<ScannerResult> {
  const args = banditArgs(ctx);
  const result = await runProcess("uv", args, {
    cwd: ctx.root,
    timeoutMs: ctx.timeoutMs,
  });

  let parsed: ParsedScanner | null = null;
  const errors: string[] = [];
  try {
    parsed = parseBandit(JSON.parse(result.stdout) as BanditJson, ctx.root);
  } catch (error) {
    errors.push(
      `Invalid Bandit JSON: ${error instanceof Error ? error.message : String(error)}`,
    );
    if (result.stderr.trim()) errors.push(tail(result.stderr));
  }

  const accepted = result.exitCode === 0 || (result.exitCode === 1 && parsed !== null);
  const status = !accepted || parsed === null ? "failed" : "ok";

  return {
    tool: "Bandit",
    version: ctx.versions.bandit ?? "unknown",
    command: ["uv", ...args],
    status,
    exitCode: result.exitCode,
    durationMs: result.durationMs,
    stats: parsed?.stats ?? {},
    warnings: parsed?.warnings ?? [],
    errors: [...errors, ...(parsed?.errors ?? [])],
    findings: parsed?.findings ?? [],
    maintenance: [],
  };
}
