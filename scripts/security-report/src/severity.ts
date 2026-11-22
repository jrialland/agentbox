import { findingTarget, type Finding } from "./model";

export type Severity = "critical" | "high" | "medium" | "low" | "info" | "unknown";

export const SEVERITIES: Severity[] = [
  "critical",
  "high",
  "medium",
  "low",
  "info",
  "unknown",
];

export const SEVERITY_LABEL: Record<Severity, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
  info: "Info",
  unknown: "Unknown",
};

export const SEVERITY_COLOR: Record<Severity, string> = {
  critical: "#b42318",
  high: "#a31c8c",
  medium: "#9a5a00",
  low: "#007a99",
  info: "#5a6658",
  unknown: "#8e9c8e",
};

const ALIASES: Record<string, Severity> = {
  critical: "critical",
  crit: "critical",
  high: "high",
  error: "high",
  medium: "medium",
  moderate: "medium",
  warning: "medium",
  warn: "medium",
  low: "low",
  info: "info",
  information: "info",
  informational: "info",
  unknown: "unknown",
  none: "unknown",
};

export function normalizeSeverity(value: string | null | undefined): Severity {
  return ALIASES[(value ?? "").trim().toLowerCase()] ?? "unknown";
}

export function severityRank(severity: Severity): number {
  return SEVERITIES.indexOf(severity);
}

export function emptySeverityCounts(): Record<Severity, number> {
  return { critical: 0, high: 0, medium: 0, low: 0, info: 0, unknown: 0 };
}

export function countSeverities(findings: Finding[]): Record<Severity, number> {
  const counts = emptySeverityCounts();
  for (const finding of findings) {
    if (finding.suppressed) continue;
    counts[finding.severity] += 1;
  }
  return counts;
}

export function sortFindings(findings: Finding[]): Finding[] {
  return [...findings].sort(
    (a, b) =>
      severityRank(a.severity) - severityRank(b.severity) ||
      findingTarget(a).localeCompare(findingTarget(b)) ||
      (a.ruleId ?? "").localeCompare(b.ruleId ?? "") ||
      a.title.localeCompare(b.title),
  );
}

export function countAtOrAbove(findings: Finding[], threshold: Severity): number {
  const limit = severityRank(threshold);
  return findings.filter(
    (finding) => !finding.suppressed && severityRank(finding.severity) <= limit,
  ).length;
}
