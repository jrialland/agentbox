import type {
  ComponentInfo,
  GitCoordinates,
  LockfileInfo,
  ReportModel,
  ScannerResult,
} from "./model";
import {
  countAtOrAbove,
  countSeverities,
  sortFindings,
  type Severity,
} from "./severity";

export const DEFAULT_LIMITATIONS = [
  "SCA relies on the vulnerability sources reachable at scan time (PyPA, PyPI, OSV, GitHub advisories); partial scans are flagged.",
  "SAST excludes tests, fixtures, and stories by default; use --include-tests for full coverage.",
  "No runtime, dynamic, container, secret, or license scanning is performed.",
  "JS-X-Ray uses its own warning severity model; normalization is documented in the severity glossary.",
  "Findings marked suppressed by a scanner are listed in the appendix but excluded from counts and gates.",
  "The report reflects the working tree at scan time, including uncommitted changes.",
];

export interface BuildReportInput {
  reportId: string;
  classification: string;
  generatedAt: Date;
  scanStartedAt: Date;
  scanFinishedAt: Date;
  projectName: string;
  root: string;
  git: GitCoordinates;
  components: ComponentInfo[];
  lockfiles: LockfileInfo[];
  tools: ScannerResult[];
  limitations?: string[];
}

export function buildReportModel(input: BuildReportInput): ReportModel {
  const findings = input.tools.flatMap((tool) => tool.findings);
  const sca = sortFindings(findings.filter((finding) => finding.section === "sca"));
  const sast = sortFindings(findings.filter((finding) => finding.section === "sast"));

  return {
    schemaVersion: 1,
    reportId: input.reportId,
    classification: input.classification,
    generatedAt: input.generatedAt.toISOString(),
    scanStartedAt: input.scanStartedAt.toISOString(),
    scanFinishedAt: input.scanFinishedAt.toISOString(),
    project: {
      name: input.projectName,
      root: input.root,
      git: input.git,
      components: input.components,
      lockfiles: input.lockfiles,
    },
    tools: input.tools,
    sections: {
      sca: { severityCounts: countSeverities(sca), findings: sca },
      sast: { severityCounts: countSeverities(sast), findings: sast },
    },
    limitations: input.limitations ?? DEFAULT_LIMITATIONS,
  };
}

export function determineExitCode(
  model: ReportModel,
  options: { allowPartial: boolean; failOn: Severity | "none" },
  pdfFailed: boolean,
): number {
  if (pdfFailed) return 1;
  if (model.tools.length === 0) return 1;
  if (model.tools.every((tool) => tool.status === "failed")) return 1;

  const incomplete = model.tools.some((tool) => tool.status !== "ok");
  if (incomplete && !options.allowPartial) return 1;

  if (options.failOn !== "none") {
    const findings = [...model.sections.sca.findings, ...model.sections.sast.findings];
    if (countAtOrAbove(findings, options.failOn) > 0) return 3;
  }

  return 0;
}
