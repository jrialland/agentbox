import type {
  GitCoordinates,
  ReportModel,
  ScannerResult,
} from "./model";

export function makeGit(partial: Partial<GitCoordinates> = {}): GitCoordinates {
  return {
    root: "/repo",
    remoteUrl: "git@example.com:org/repo.git",
    branch: "main",
    headSha: "a".repeat(40),
    headShortSha: "aaaaaaa",
    treeSha: "b".repeat(40),
    describe: "v1.2.3",
    latestTag: "v1.2.3",
    authorName: "Ada",
    authorEmail: "ada@example.com",
    authoredAt: "2026-11-22T10:00:00Z",
    subject: "Add report",
    dirty: false,
    dirtyFiles: 0,
    statusCounts: {
      added: 0,
      modified: 0,
      deleted: 0,
      renamed: 0,
      untracked: 0,
      unmerged: 0,
    },
    ...partial,
  };
}

export function makeScanner(partial: Partial<ScannerResult> = {}): ScannerResult {
  return {
    tool: "Bandit",
    version: "1.9.4",
    command: ["uv", "run", "bandit"],
    status: "ok",
    exitCode: 0,
    durationMs: 10,
    stats: {},
    warnings: [],
    errors: [],
    findings: [],
    maintenance: [],
    ...partial,
  };
}

export function makeModel(partial: Partial<ReportModel> = {}): ReportModel {
  return {
    schemaVersion: 1,
    reportId: "agentbox-security-aaaaaaa-20261122T120000Z",
    classification: "Internal",
    generatedAt: "2026-11-22T12:00:00.000Z",
    scanStartedAt: "2026-11-22T11:59:00.000Z",
    scanFinishedAt: "2026-11-22T12:00:00.000Z",
    project: {
      name: "demo",
      root: "/repo",
      git: makeGit(),
      components: [],
      lockfiles: [],
    },
    tools: [makeScanner()],
    sections: {
      sca: {
        severityCounts: { critical: 0, high: 0, medium: 0, low: 0, info: 0, unknown: 0 },
        findings: [],
      },
      sast: {
        severityCounts: { critical: 0, high: 0, medium: 0, low: 0, info: 0, unknown: 0 },
        findings: [],
      },
    },
    limitations: ["Limitation"],
    ...partial,
  };
}
