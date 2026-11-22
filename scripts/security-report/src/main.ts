import { copyFileSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { parseArgs, helpText, type CliOptions } from "./cli";
import { loadFixtureProject, loadFixtureResults } from "./fixtures";
import { collectGit, resolveRepoRoot } from "./git";
import type { GitCoordinates, ScannerResult } from "./model";
import { renderPdf } from "./pdf";
import {
  discoverProject,
  readPackageVersion,
  type ProjectDiscovery,
} from "./project";
import { buildReportModel, determineExitCode } from "./report";
import { buildFontCss } from "./render/fonts";
import { renderReport } from "./render/html";
import { scanBandit } from "./scanners/bandit";
import { scanJsSca } from "./scanners/bun-audit";
import { scanJsxray } from "./scanners/jsxray";
import { commandVersion } from "./scanners/process";
import { scanPysentry } from "./scanners/pysentry";
import type { ScanContext } from "./scanners/types";

export interface RunDeps {
  now?: () => Date;
}

export interface RunArtifacts {
  html: string;
  pdf: string | null;
  json: string;
}

function timestamp(date: Date): string {
  return date.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
}

async function collectVersions(
  root: string,
  toolRoot: string,
): Promise<Record<string, string>> {
  return {
    pysentry: await commandVersion("uvx", ["pysentry-rs", "--version"], root),
    bandit: await commandVersion("uv", ["run", "bandit", "--version"], root),
    bun: await commandVersion("bun", ["--version"], root),
    npm: await commandVersion("npm", ["--version"], root),
    jsxray: readPackageVersion("@nodesecure/js-x-ray", toolRoot) ?? "unknown",
    playwright: readPackageVersion("playwright", toolRoot) ?? "unknown",
  };
}

function failedScan(tool: string, error: unknown): ScannerResult {
  return {
    tool,
    version: "unknown",
    command: [],
    status: "failed",
    exitCode: null,
    durationMs: 0,
    stats: {},
    warnings: [],
    errors: [error instanceof Error ? error.message : String(error)],
    findings: [],
    maintenance: [],
  };
}

async function collectTools(
  options: CliOptions,
  project: ProjectDiscovery,
  root: string,
  versions: Record<string, string>,
): Promise<ScannerResult[]> {
  const ctx: ScanContext = {
    root,
    pythonRoots: project.pythonRoots,
    jsComponents: project.jsComponents,
    includeTests: options.includeTests,
    extraExcludes: options.excludes,
    timeoutMs: options.scannerTimeout * 1000,
    versions,
  };
  const [pysentry, bandit, jsxray, jsSca] = await Promise.all([
    scanPysentry(ctx).catch((error) => failedScan("PySentry", error)),
    scanBandit(ctx).catch((error) => failedScan("Bandit", error)),
    scanJsxray(ctx).catch((error) => failedScan("JS-X-Ray", error)),
    scanJsSca(ctx).catch((error) => [failedScan("JavaScript SCA", error)]),
  ]);
  return [pysentry, bandit, jsxray, ...jsSca];
}

export async function runReport(
  options: CliOptions,
  deps: RunDeps = {},
): Promise<{ exitCode: number; artifacts: RunArtifacts }> {
  const now = deps.now ?? (() => new Date());
  const scanStartedAt = now();
  const toolRoot = resolve(import.meta.dir, "..");

  let root: string;
  let project: ProjectDiscovery;
  let git: GitCoordinates;

  if (options.fromFixtures) {
    const fixture = loadFixtureProject(options.fromFixtures);
    root = fixture.project.root;
    project = fixture.project;
    git = fixture.git;
  } else {
    root = options.projectPath
      ? resolve(options.projectPath)
      : await resolveRepoRoot(process.cwd());
    project = await discoverProject(root, {
      includeTests: options.includeTests,
      extraExcludes: options.excludes,
    });
    git = await collectGit(root);
  }

  const versions = options.fromFixtures ? {} : await collectVersions(root, toolRoot);

  if (options.verbose) {
    console.error(`Project root: ${root}`);
    console.error(
      `Components: ${project.components.length}; Python roots: ${project.pythonRoots.length}; JS components: ${project.jsComponents.length}`,
    );
    console.error(`Tool versions: ${JSON.stringify(versions)}`);
    console.error(`Output directory: ${resolve(root, options.outDir)}`);
  }

  const tools = options.fromFixtures
    ? await loadFixtureResults(options.fromFixtures, project)
    : await collectTools(options, project, root, versions);

  const scanFinishedAt = now();
  const shortSha = git.headShortSha || "nogit";
  const reportId = `agentbox-security-${shortSha}-${timestamp(scanStartedAt)}`;
  const model = buildReportModel({
    reportId,
    classification: options.classification,
    generatedAt: scanFinishedAt,
    scanStartedAt,
    scanFinishedAt,
    projectName: project.name,
    root,
    git,
    components: project.components,
    lockfiles: project.lockfiles,
    tools,
  });

  const outDir = resolve(root, options.outDir);
  mkdirSync(outDir, { recursive: true });
  const htmlPath = join(outDir, `${reportId}.html`);
  const jsonPath = join(outDir, `${reportId}.json`);
  const fontCss = buildFontCss(join(toolRoot, "assets", "fonts"));
  writeFileSync(htmlPath, renderReport(model, { fontCss }));
  writeFileSync(jsonPath, `${JSON.stringify(model, null, 2)}\n`);

  let pdfPath: string | null = null;
  let pdfFailed = false;
  if (!options.noPdf) {
    pdfPath = join(outDir, `${reportId}.pdf`);
    try {
      await renderPdf(htmlPath, pdfPath);
    } catch (error) {
      pdfFailed = true;
      pdfPath = null;
      console.error(
        `PDF generation failed: ${error instanceof Error ? error.message : String(error)}`,
      );
      console.error(
        "Run `bun run --cwd scripts/security-report playwright install chromium` and retry.",
      );
    }
  }

  copyFileSync(htmlPath, join(outDir, "latest.html"));
  copyFileSync(jsonPath, join(outDir, "latest.json"));
  const latestPdf = join(outDir, "latest.pdf");
  if (pdfPath) {
    copyFileSync(pdfPath, latestPdf);
  } else {
    rmSync(latestPdf, { force: true });
  }

  const exitCode = determineExitCode(model, options, pdfFailed);
  const sca = model.sections.sca.severityCounts;
  const sast = model.sections.sast.severityCounts;
  console.error(
    `SCA: ${Object.values(sca).reduce((sum, count) => sum + count, 0)} findings | SAST: ${Object.values(sast).reduce((sum, count) => sum + count, 0)} findings`,
  );
  for (const tool of model.tools) {
    console.error(
      `  ${tool.tool}: ${tool.status}${tool.errors.length > 0 ? ` (${tool.errors[0]})` : ""}`,
    );
  }
  console.error(`HTML: ${htmlPath}`);
  if (pdfPath) console.error(`PDF:  ${pdfPath}`);
  console.error(`JSON: ${jsonPath}`);
  console.error(`Exit: ${exitCode}`);

  return { exitCode, artifacts: { html: htmlPath, pdf: pdfPath, json: jsonPath } };
}

export async function main(argv = process.argv.slice(2)): Promise<void> {
  let options: CliOptions;
  try {
    options = parseArgs(argv);
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    console.error(helpText());
    process.exitCode = 2;
    return;
  }

  if (options.help) {
    console.log(helpText());
    return;
  }

  try {
    const result = await runReport(options);
    process.exitCode = result.exitCode;
  } catch (error) {
    console.error(error instanceof Error ? error.stack ?? error.message : String(error));
    process.exitCode = 2;
  }
}

if (import.meta.main) {
  await main();
}
