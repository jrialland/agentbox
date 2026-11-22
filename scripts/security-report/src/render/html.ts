import type { Finding, ReportModel, ScannerResult } from "../model";
import { countSeverities, SEVERITIES, SEVERITY_LABEL, sortFindings } from "../severity";
import {
  displayPath,
  escapeHtml,
  safeUrl,
  severityBadge,
  truncate,
} from "./components";
import { renderDonut, renderSeverityLegend, renderSeverityStrip } from "./charts";
import { STYLES } from "./styles";

export function renderCover(model: ReportModel): string {
  const sca = model.sections.sca.severityCounts;
  const sast = model.sections.sast.severityCounts;
  const total =
    SEVERITIES.reduce((sum, severity) => sum + sca[severity], 0) +
    SEVERITIES.reduce((sum, severity) => sum + sast[severity], 0);
  const high = sca.high + sast.high;
  const critical = sca.critical + sast.critical;
  const status =
    total === 0
      ? `<span class="status clean">No findings</span>`
      : `<span class="status">${total} findings · ${critical} critical · ${high} high</span>`;

  return `<section class="page cover">
    <div>
      <div class="wordmark">[AGENTBOX]<span aria-hidden>▮</span></div>
      <div class="classification">${escapeHtml(model.classification)}</div>
    </div>
    <div class="cover-title">
      <h1>Security Audit Report</h1>
      <div class="cover-subtitle">${escapeHtml(model.project.name)}</div>
      <div class="cover-meta">
        <div><span class="muted">Report ID</span><br><span class="mono">${escapeHtml(model.reportId)}</span></div>
        <div><span class="muted">Generated</span><br><span class="mono">${escapeHtml(model.generatedAt)}</span></div>
        <div><span class="muted">Revision</span><br><span class="mono">${escapeHtml(model.project.git.branch)} @ ${escapeHtml(model.project.git.headShortSha)}</span></div>
        <div><span class="muted">Working tree</span><br><span class="mono">${model.project.git.dirty ? `dirty (${model.project.git.dirtyFiles} files)` : "clean"}</span></div>
      </div>
      ${status}
    </div>
    <div class="footer"><span>Agentbox Security Report</span><span>${escapeHtml(model.project.git.headSha)}</span></div>
  </section>`;
}

export function renderCoordinates(model: ReportModel): string {
  const git = model.project.git;
  const rows: Array<[string, string]> = [
    ["Repository root", escapeHtml(git.root.replace(/^[A-Za-z]:\\Users\\[^\\]+/i, "~"))],
    ["Remote", escapeHtml(git.remoteUrl ?? "none")],
    ["Branch", escapeHtml(git.branch)],
    ["HEAD", escapeHtml(git.headSha)],
    ["Tree", escapeHtml(git.treeSha)],
    ["Describe", escapeHtml(git.describe ?? "none")],
    ["Latest tag", escapeHtml(git.latestTag ?? "none")],
    ["Author", escapeHtml(`${git.authorName} <${git.authorEmail}>`)],
    ["Authored", escapeHtml(git.authoredAt)],
    ["Subject", escapeHtml(git.subject)],
    ["Dirty", escapeHtml(git.dirty ? `yes (${git.dirtyFiles} files)` : "no")],
  ];

  const components = model.project.components
    .map(
      (component) =>
        `<tr><td>${escapeHtml(component.kind)}</td><td>${escapeHtml(component.name)}</td><td class="mono">${escapeHtml(displayPath(model.project.root, component.path) ?? component.path)}</td><td class="mono">${escapeHtml(component.version ?? "—")}</td></tr>`,
    )
    .join("");

  const lockfiles = model.project.lockfiles
    .map(
      (lock) =>
        `<tr><td class="mono">${escapeHtml(displayPath(model.project.root, lock.path) ?? lock.path)}</td><td class="mono">${escapeHtml(lock.sha256)}</td></tr>`,
    )
    .join("");

  const tools = model.tools
    .map(
      (tool) =>
        `<tr><td>${escapeHtml(tool.tool)}</td><td class="mono">${escapeHtml(tool.version)}</td><td class="mono">${escapeHtml(tool.command.join(" "))}</td><td>${escapeHtml(tool.status)}</td></tr>`,
    )
    .join("");

  return `<section class="page page-break" id="coordinates">
    <h2>Audit coordinates</h2>
    <p class="muted">Captured before scanning. Scans started ${escapeHtml(model.scanStartedAt)} and finished ${escapeHtml(model.scanFinishedAt)}.</p>
    <table class="kv"><tbody>${rows.map(([key, value]) => `<tr><th>${key}</th><td class="mono">${value}</td></tr>`).join("")}</tbody></table>
    <h3 style="margin-top:18px">Components</h3>
    <table><thead><tr><th>Kind</th><th>Name</th><th>Path</th><th>Version</th></tr></thead><tbody>${components || '<tr><td colspan="4" class="muted">No components discovered</td></tr>'}</tbody></table>
    <h3 style="margin-top:18px">Lockfiles</h3>
    <table><thead><tr><th>Path</th><th>SHA-256</th></tr></thead><tbody>${lockfiles || '<tr><td colspan="2" class="muted">No lockfiles discovered</td></tr>'}</tbody></table>
    <h3 style="margin-top:18px">Scanners</h3>
    <table><thead><tr><th>Tool</th><th>Version</th><th>Command</th><th>Status</th></tr></thead><tbody>${tools}</tbody></table>
    <p class="muted" style="margin-top:12px">Scope: ${escapeHtml(model.limitations[1] ?? "")}</p>
  </section>`;
}

export function renderExecutiveSummary(model: ReportModel): string {
  const scaCounts = model.sections.sca.severityCounts;
  const sastCounts = model.sections.sast.severityCounts;
  const top = sortFindings([
    ...model.sections.sca.findings,
    ...model.sections.sast.findings,
  ])
    .filter((finding) => !finding.suppressed)
    .slice(0, 10);

  const matrixRows = SEVERITIES.map(
    (severity) =>
      `<tr><td>${severityBadge(severity)}</td><td class="mono">${scaCounts[severity]}</td><td class="mono">${sastCounts[severity]}</td><td class="mono">${scaCounts[severity] + sastCounts[severity]}</td></tr>`,
  ).join("");

  const topRows = top
    .map(
      (finding) =>
        `<tr><td>${severityBadge(finding.severity)}</td><td>${escapeHtml(finding.tool)}</td><td class="mono">${escapeHtml(finding.ruleId ?? "—")}</td><td>${escapeHtml(finding.packageName ?? `${finding.file ?? ""}${finding.line ? `:${finding.line}` : ""}`)}</td><td>${escapeHtml(finding.title)}</td></tr>`,
    )
    .join("");

  return `<section class="page page-break" id="summary">
    <h2>Executive summary</h2>
    <div class="grid">
      <div class="card"><h3>SCA</h3><div class="summary">${renderDonut(SEVERITIES.map((severity) => ({ severity, count: scaCounts[severity] })), { label: "SCA" })}${renderSeverityLegend(scaCounts)}</div></div>
      <div class="card"><h3>SAST</h3><div class="summary">${renderDonut(SEVERITIES.map((severity) => ({ severity, count: sastCounts[severity] })), { label: "SAST" })}${renderSeverityLegend(sastCounts)}</div></div>
    </div>
    <h3 style="margin-top:18px">Severity matrix</h3>
    <table><thead><tr><th>Severity</th><th>SCA</th><th>SAST</th><th>Total</th></tr></thead><tbody>${matrixRows}</tbody></table>
    <h3 style="margin-top:18px">Top findings</h3>
    <table><thead><tr><th>Severity</th><th>Tool</th><th>Rule</th><th>Target</th><th>Title</th></tr></thead><tbody>${topRows || '<tr><td colspan="5" class="muted">No findings</td></tr>'}</tbody></table>
  </section>`;
}

export function renderFindingsTable(findings: Finding[]): string {
  const rows = findings
    .filter((finding) => !finding.suppressed)
    .map((finding) => {
      const target = finding.packageName
        ? escapeHtml(
            finding.installedVersion
              ? `${finding.packageName}@${finding.installedVersion}`
              : finding.packageName,
          )
        : escapeHtml(
            `${finding.file ?? "—"}${finding.line ? `:${finding.line}` : ""}`,
          );
      const reference = safeUrl(finding.referenceUrl);
      const link = reference
        ? `<a href="${escapeHtml(reference)}">${escapeHtml(reference)}</a>`
        : escapeHtml(finding.referenceUrl ?? "");
      return `<tr><td>${severityBadge(finding.severity)}</td><td class="mono">${escapeHtml(finding.ruleId ?? "—")}</td><td class="mono">${target}</td><td>${escapeHtml(truncate(finding.title, 200))}${finding.detail ? `<div class="detail">${escapeHtml(truncate(finding.detail, 280))}</div>` : ""}</td><td>${escapeHtml(finding.confidence ?? "—")}</td><td>${finding.fix ? escapeHtml(finding.fix) : link || "—"}</td></tr>`;
    })
    .join("");
  return `<table><thead><tr><th>Severity</th><th>Rule</th><th>Target</th><th>Title</th><th>Confidence</th><th>Fix / reference</th></tr></thead><tbody>${rows || '<tr><td colspan="6" class="muted">No findings</td></tr>'}</tbody></table>`;
}

function renderToolBlock(
  tool: ScannerResult,
  section: "sca" | "sast",
): string {
  const findings = tool.findings.filter((finding) => finding.section === section);
  const counts = countSeverities(findings);
  const stats = Object.entries(tool.stats)
    .map(([key, value]) => `<span>${escapeHtml(key)}: <b>${escapeHtml(value)}</b></span>`)
    .join("");
  const warnings = tool.warnings.length
    ? `<div class="banner">Warnings: ${tool.warnings.map(escapeHtml).join("; ")}</div>`
    : "";
  const errors = tool.errors.length
    ? `<div class="banner">Errors: ${tool.errors.map(escapeHtml).join("; ")}</div>`
    : "";

  return `<div class="tool-block">
    <div class="tool-head"><h3>${escapeHtml(tool.tool)}</h3><span class="mono muted">${escapeHtml(tool.version)} · ${escapeHtml(tool.status)}</span></div>
    ${renderSeverityStrip(counts)}
    <div class="stats">${stats || '<span class="muted">No statistics</span>'}</div>
    ${warnings}${errors}
    ${renderFindingsTable(findings)}
  </div>`;
}

function renderMaintenance(tools: ScannerResult[]): string {
  const issues = tools.flatMap((tool) => tool.maintenance);
  if (issues.length === 0) return "";
  const rows = issues
    .map(
      (issue) =>
        `<tr><td class="mono">${escapeHtml(issue.packageName)}@${escapeHtml(issue.installedVersion)}</td><td>${escapeHtml(issue.issueType)}</td><td>${escapeHtml(issue.reason ?? "—")}</td><td>${issue.isDirect ? "direct" : "transitive"}</td></tr>`,
    )
    .join("");
  return `<h3 style="margin-top:18px">Maintenance issues</h3><table><thead><tr><th>Package</th><th>Issue</th><th>Reason</th><th>Dependency</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function renderFixSuggestions(findings: Finding[]): string {
  const fixes = findings.filter((finding) => finding.fix && !finding.suppressed);
  if (fixes.length === 0) return "";
  const rows = fixes
    .map(
      (finding) =>
        `<tr><td class="mono">${escapeHtml(finding.packageName ?? "—")}@${escapeHtml(finding.installedVersion ?? "—")}</td><td class="mono">${escapeHtml(finding.ruleId ?? "—")}</td><td>${escapeHtml(finding.fix ?? "")}</td></tr>`,
    )
    .join("");
  return `<h3 style="margin-top:18px">Fix suggestions</h3><table><thead><tr><th>Package</th><th>Advisory</th><th>Fix</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function toolSection(tool: ScannerResult): "sca" | "sast" {
  return tool.tool === "PySentry" || tool.tool === "Bun audit" || tool.tool === "NPM audit"
    ? "sca"
    : "sast";
}

function renderSection(
  model: ReportModel,
  section: "sca" | "sast",
  title: string,
  description: string,
): string {
  const summary = section === "sca" ? model.sections.sca : model.sections.sast;
  const tools = model.tools.filter(
    (tool) =>
      toolSection(tool) === section ||
      (section === "sca" && tool.maintenance.length > 0),
  );
  const banner = tools.some((tool) => tool.status !== "ok")
    ? `<div class="banner">One or more scanners did not complete a full scan. See the tool blocks and appendix for details.</div>`
    : "";

  return `<section class="page page-break" id="${section}">
    <h2>${title}</h2>
    <p class="muted">${description}</p>
    ${banner}
    <div class="card"><div class="summary">${renderDonut(SEVERITIES.map((severity) => ({ severity, count: summary.severityCounts[severity] })), { label: title })}${renderSeverityLegend(summary.severityCounts)}</div></div>
    ${tools.map((tool) => renderToolBlock(tool, section)).join("")}
    ${section === "sca" ? renderMaintenance(model.tools) : ""}
    ${section === "sca" ? renderFixSuggestions(summary.findings) : ""}
  </section>`;
}

export function renderSca(model: ReportModel): string {
  return renderSection(
    model,
    "sca",
    "Software composition analysis",
    "Known vulnerabilities in declared and transitive dependencies.",
  );
}

export function renderSast(model: ReportModel): string {
  return renderSection(
    model,
    "sast",
    "Static application security testing",
    "Suspicious or vulnerable patterns in first-party source code.",
  );
}

export function renderAppendix(model: ReportModel): string {
  const suppressed = model.tools
    .flatMap((tool) => tool.findings)
    .filter((finding) => finding.suppressed);
  const suppressedRows = suppressed
    .map(
      (finding) =>
        `<tr><td>${severityBadge(finding.severity)}</td><td>${escapeHtml(finding.tool)}</td><td class="mono">${escapeHtml(finding.ruleId ?? "—")}</td><td>${escapeHtml(finding.packageName ?? finding.file ?? "—")}</td><td>${escapeHtml(finding.suppressed ?? "")}</td></tr>`,
    )
    .join("");

  const toolRows = model.tools
    .map(
      (tool) =>
        `<tr><td>${escapeHtml(tool.tool)}</td><td class="mono">${escapeHtml(tool.version)}</td><td class="mono">${escapeHtml(tool.command.join(" "))}</td><td>${escapeHtml(tool.status)}</td><td class="mono">${escapeHtml(tool.exitCode ?? "—")}</td><td class="mono">${tool.durationMs} ms</td></tr>`,
    )
    .join("");

  const limitations = model.limitations
    .map((limitation) => `<li>${escapeHtml(limitation)}</li>`)
    .join("");

  const glossary = SEVERITIES.map(
    (severity) => `<tr><td>${severityBadge(severity)}</td><td>${SEVERITY_LABEL[severity]}</td></tr>`,
  ).join("");

  return `<section class="page page-break" id="appendix">
    <h2>Appendix</h2>
    <h3>Scanner inventory</h3>
    <table><thead><tr><th>Tool</th><th>Version</th><th>Command</th><th>Status</th><th>Exit</th><th>Duration</th></tr></thead><tbody>${toolRows}</tbody></table>
    <h3 style="margin-top:18px">Suppressed findings</h3>
    <table><thead><tr><th>Severity</th><th>Tool</th><th>Rule</th><th>Target</th><th>Reason</th></tr></thead><tbody>${suppressedRows || '<tr><td colspan="5" class="muted">None</td></tr>'}</tbody></table>
    <h3 style="margin-top:18px">Limitations</h3>
    <ul>${limitations}</ul>
    <h3 style="margin-top:18px">Severity glossary</h3>
    <table><thead><tr><th>Badge</th><th>Meaning</th></tr></thead><tbody>${glossary}</tbody></table>
  </section>`;
}

export function renderReport(
  model: ReportModel,
  options: { fontCss: string },
): string {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escapeHtml(model.project.name)} — Security Audit Report</title>
<style>${options.fontCss}\n${STYLES}</style>
</head>
<body>
${renderCover(model)}
${renderCoordinates(model)}
${renderExecutiveSummary(model)}
${renderSca(model)}
${renderSast(model)}
${renderAppendix(model)}
<footer class="footer"><span>${escapeHtml(model.reportId)}</span><span>${escapeHtml(model.generatedAt)}</span></footer>
</body>
</html>`;
}
