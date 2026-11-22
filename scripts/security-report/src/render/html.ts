import type { ReportModel } from "../model";
import { displayPath, escapeHtml } from "./components";
import { STYLES } from "./styles";

export function renderCover(model: ReportModel): string {
  const counts = model.sections.sca.severityCounts;
  const sast = model.sections.sast.severityCounts;
  const total = Object.values(counts).reduce((sum, count) => sum + count, 0) +
    Object.values(sast).reduce((sum, count) => sum + count, 0);
  const high = counts.high + sast.high;
  const critical = counts.critical + sast.critical;
  const status = total === 0
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
<footer class="footer"><span>${escapeHtml(model.reportId)}</span><span>${escapeHtml(model.generatedAt)}</span></footer>
</body>
</html>`;
}
