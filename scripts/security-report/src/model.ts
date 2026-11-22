import { createHash } from "node:crypto";
import type { Severity } from "./severity";

export type Section = "sca" | "sast";
export type Ecosystem = "python" | "javascript";
export type ScannerStatus = "ok" | "partial" | "failed";

export interface Finding {
  id: string;
  section: Section;
  ecosystem: Ecosystem;
  tool: string;
  severity: Severity;
  sourceSeverity: string;
  ruleId: string | null;
  title: string;
  detail: string | null;
  packageName?: string;
  installedVersion?: string;
  vulnerableRange?: string;
  file?: string;
  line?: number;
  column?: number;
  confidence?: string;
  referenceUrl?: string | null;
  fix?: string | null;
  suppressed?: string | null;
}

export interface MaintenanceIssue {
  packageName: string;
  installedVersion: string;
  issueType: string;
  reason: string | null;
  isDirect: boolean;
}

export interface ScannerResult {
  tool: string;
  version: string;
  command: string[];
  status: ScannerStatus;
  exitCode: number | null;
  durationMs: number;
  stats: Record<string, number | string>;
  warnings: string[];
  errors: string[];
  findings: Finding[];
  maintenance: MaintenanceIssue[];
}

export interface StatusCounts {
  added: number;
  modified: number;
  deleted: number;
  renamed: number;
  untracked: number;
  unmerged: number;
}

export interface GitCoordinates {
  root: string;
  remoteUrl: string | null;
  branch: string;
  headSha: string;
  headShortSha: string;
  treeSha: string;
  describe: string | null;
  latestTag: string | null;
  authorName: string;
  authorEmail: string;
  authoredAt: string;
  subject: string;
  dirty: boolean;
  dirtyFiles: number;
  statusCounts: StatusCounts;
}

export interface ComponentInfo {
  kind: "python" | "javascript";
  name: string;
  path: string;
  version: string | null;
  lockfile: string | null;
}

export interface LockfileInfo {
  path: string;
  sha256: string;
  resolvedVersions?: Record<string, string>;
}

export interface SectionSummary {
  severityCounts: Record<Severity, number>;
  findings: Finding[];
}

export interface ReportModel {
  schemaVersion: 1;
  reportId: string;
  classification: string;
  generatedAt: string;
  scanStartedAt: string;
  scanFinishedAt: string;
  project: {
    name: string;
    root: string;
    git: GitCoordinates;
    components: ComponentInfo[];
    lockfiles: LockfileInfo[];
  };
  tools: ScannerResult[];
  sections: {
    sca: SectionSummary;
    sast: SectionSummary;
  };
  limitations: string[];
}

export function findingTarget(finding: Finding): string {
  return finding.packageName ?? finding.file ?? "";
}

export function makeFindingId(input: {
  tool: string;
  ruleId: string | null;
  title: string;
  packageName?: string;
  file?: string;
  line?: number;
}): string {
  const raw = [
    input.tool,
    input.ruleId ?? "",
    input.packageName ?? input.file ?? "",
    input.line ?? 0,
    input.title,
  ].join("|");
  return createHash("sha256").update(raw).digest("hex").slice(0, 12);
}
