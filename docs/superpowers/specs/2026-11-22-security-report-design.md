# Security Audit Report Generator — Design

Date: 2026-11-22
Status: Approved for planning
Owner: Agentbox maintainers

## Context

The company needs every project to emit a full security report suitable for formal
documentation. The report must be generated on demand from a `just` recipe, include precise
git/build coordinates, cover SCA and SAST for the Python and JavaScript parts of the
monorepo, and produce a single self-contained HTML file that is converted to PDF.

This is developer tooling for a repository, not an Agentbox product feature. It does not add
API routes, database tables, or UI surfaces to the application.

## Goals

- Add `just security-report` that audits the current project (default) or a supplied project
  path and writes HTML, PDF, and JSON artifacts under `reports/security/`.
- Report exact git coordinates, component versions, lockfile hashes, scanner versions, and
  scan timestamps so a formal report is reproducible and attributable.
- SCA: PySentry for Python, Bun audit (with an NPM audit fallback) for JavaScript.
- SAST: Bandit for Python, JS-X-Ray for JavaScript/TypeScript.
- Render a print-first, brand-consistent report with severity pie charts per section.
- Convert the HTML to PDF without external services or network access at render time.

## Non-goals

- Runtime/DAST testing, secret scanning, container scanning, or license compliance.
- Continuous monitoring, scheduled scans, or CI workflow files (the optional `--fail-on`
  gate is provided for future CI use).
- Uploading or publishing reports anywhere.
- Committing generated artifacts to git.
- Changing the application's backend, frontend, database, or OpenAPI surface.

## Decisions

| Topic | Decision |
| --- | --- |
| Location | `scripts/security-report/`, a self-contained Bun/TypeScript package |
| Report theme | Light, print-first, app brand accents |
| Scope | Reusable and repo-aware; defaults discover this monorepo correctly |
| Language | English |
| Artifacts | `reports/security/`, gitignored, timestamped plus `latest.*` |
| Exit behavior | Report-first; findings do not fail the run unless `--fail-on` is set |
| Data parsing | Structured formats only; never scrape human-readable output |
| Report format | One self-contained HTML file, A4 PDF, plus a JSON snapshot |

## Architecture

```
scripts/security-report/
  package.json, bun.lock, tsconfig.json, README.md
  assets/fonts/                embedded Silkscreen, Inter, JetBrains Mono woff2
  src/
    main.ts                    CLI: parse args -> orchestrate -> write artifacts -> exit
    cli.ts                     argument parsing, help, defaults
    git.ts                     git coordinates
    project.ts                 component discovery, versions, lockfile hashes/versions
    model.ts                   Report/Component/ScannerResult/Finding/Severity types
    severity.ts                normalization, ordering, labels, colors
    scanners/
      pysentry.ts              Python SCA
      bun-audit.ts             JavaScript SCA (Bun, NPM fallback)
      bandit.ts                Python SAST
      jsxray.ts                JavaScript/TypeScript SAST
    render/
      html.ts                  assembles the full document
      styles.ts                inline print CSS
      charts.ts                inline SVG donut charts
      components.ts            shared markup helpers and HTML escaping
      fonts.ts                 base64 font embedding
    pdf.ts                     Playwright Chromium -> PDF
    fixtures/                  structured scanner fixtures for tests
    *.test.ts                  unit and integration tests
```

### Data flow

1. Resolve the project root (default: `git rev-parse --show-toplevel` from the process cwd;
   otherwise the positional path argument). Record scan start time.
2. Collect metadata before scanning: git coordinates, component versions, lockfile SHA-256
   hashes, resolved JavaScript package versions from the lockfiles, tool versions, and the
   report ID.
3. Run the four scanner adapters concurrently (JS-X-Ray runs in-process; the others are
   subprocesses). Each adapter returns a `ScannerResult`.
4. Normalize findings into the shared model and compute per-section severity counts.
5. Render the HTML from the model, then render the PDF from the HTML.
6. Write timestamped artifacts plus `latest.*`, print a summary, and exit with the code
   defined below.

### Structured-only invariant

Adapters consume only native structured output. No adapter parses console text, logos,
progress lines, banners, or human summaries.

| Tool | Structured source |
| --- | --- |
| PySentry | `pysentry-rs --format json` (`vulnerabilities`, `fix_suggestions`, `maintenance_issues`, `partial`, `failed_sources`) |
| Bandit | `bandit -f json` (`results[].issue_severity`, `issue_confidence`) |
| Bun audit | `bun audit --json` |
| NPM audit | `npm audit --json` (fallback) |
| JS-X-Ray | In-process `AstAnalyser` warning objects |
| Component metadata | `pyproject.toml` via `Bun.TOML`, `package.json` via JSON |
| Lockfiles | Read as data: SHA-256; `bun.lock` via `Bun.JSONC.parse`; `package-lock.json` via JSON |
| Git | `git rev-parse`, `git status --porcelain=v2`, `git log --format`, `git for-each-ref` |

Tool and runtime versions come from structured sources where possible: JS-X-Ray and
Playwright from their `package.json`; PySentry, Bandit, Bun, Python, and Git from their
`--version` output, which is used only for scanner identity. A missing version is recorded
as `unknown`, never inferred from findings.

Tool `--version` output is used only to identify the scanner version, never to derive
findings. If a version cannot be obtained, record `unknown` rather than failing the scan.

## Component discovery and exclusions

### Python

- Read the root `pyproject.toml`. If `[tool.uv.workspace].members` exists, resolve each member
  directory; otherwise treat the root as the only Python component.
- Component version comes from `[project].version` when present, else `null`.
- SCA runs PySentry once at the project root so it can read the uv workspace and `uv.lock`.
- SAST source roots are each member directory (for this repo: `packages/agentbox-*`).

### JavaScript

- Find directories containing `package.json` outside `node_modules` (for this repo:
  `apps/web`). Prefer directories with `bun.lock` or `bun.lockb`.
- Component version comes from `package.json` `version` when present, else `null`.
- SCA runs `bun audit --json` in each component with a Bun lockfile. If only
  `package-lock.json` exists, use `npm audit --json` instead.
- Resolved versions are read from `bun.lock` (`Bun.JSONC.parse`, the `packages` map) or
  `package-lock.json` (`packages["node_modules/<name>"].version`) so SCA findings can show
  both the installed and vulnerable versions.
- SAST walks the component source tree for `.js`, `.jsx`, `.mjs`, `.cjs`, `.ts`, `.tsx`,
  `.mts`, `.cts`.

### Default exclusions

Both SAST tools exclude generated and dependency directories:

```
.venv, venv, node_modules, dist, build, coverage, .next, out, .git,
__pycache__, .pytest_cache, .ruff_cache, .mypy_cache, site-packages
```

SAST additionally excludes tests and stories by default, because shipped code is the audit
target and test assertions produce large volumes of low-value findings:

```
**/tests/**, **/fixtures/**, **/*.test.*, **/*.spec.*, **/*.stories.*
```

`--include-tests` disables this second exclusion set. Excluded paths and the reason are
listed in the report's scope section.

Measured on this repository: Bandit without exclusions hangs on nested
`packages/*/.venv` and reports 643 mostly-LOW test asserts; with the defaults it reports
6 LOW findings in about 3 seconds. JS-X-Ray without test exclusions reports 17 mostly
`shady-link` test warnings; with defaults it reports 4 warnings in about 1 second.

## Scanner adapters

### PySentry (SCA — Python)

Command: `uvx pysentry-rs <root> --format json --output <temp-file>`.

- Accept exit `0` or `1` when the JSON file parses. Exit `1` means findings exceeded the
  default fail threshold and is not treated as a failure.
- Exit `2`, `partial: true`, or a non-empty `failed_sources` marks the scan `partial`.
- Anything else, or unparseable JSON, marks the scan `failed`.
- Record: total packages, vulnerable packages, vulnerabilities, fix suggestions,
  maintenance issues (archived/deprecated/quarantined), warnings, partial/failed sources.

### Bandit (SAST — Python)

Command: `uv run bandit -r <python-roots...> -x <excluded-paths...> -f json -q`.

- Accept exit `0` or `1` when JSON parses.
- Record: metrics totals (lines of code, issues), results with severity and confidence, the
  number of files with findings, and the JSON `errors` array.
- Resolve file paths relative to the project root for display.

### Bun audit (SCA — JavaScript)

Command: `bun audit --json` run in the component directory.

- Accept exit `0` or `1` when JSON parses.
- The JSON is keyed by package name; each value is an advisory array. Record advisory ID,
  URL, title, severity, vulnerable range, CWE, and CVSS.
- Enrich each advisory with the resolved installed version from the component lockfile when
  the package can be matched; omit it otherwise rather than guessing.
- Fall back to `npm audit --json` when the component has `package-lock.json` and no Bun
  lockfile. Parse its `vulnerabilities` map, including `via` advisories and `fixAvailable`,
  and enrich installed versions from `package-lock.json` the same way.

### JS-X-Ray (SAST — JavaScript/TypeScript)

In-process scanner:

- Use `AstAnalyser.analyse(source, { customParser, location })`, not `analyseFile`. The
  `analyseFile` implementation throws on any path containing the substring `d.ts`.
- Choose `TsSourceParser` for `.ts`, `.tsx`, `.mts`, `.cts` and `JsSourceParser` for
  `.js`, `.jsx`, `.mjs`, `.cjs`. The `typescript` package is required by `TsSourceParser`.
- Skip `.d.ts` files entirely.
- Enable only the `crypto.*` and `unsafe-vm-context` optional warnings; leave noisy
  performance/log warnings off.
- Resolve warning descriptions through `@nodesecure/i18n`:
  `extendFromSystemPath(jsxray.i18nLocation())`, then `getLocalLang()`, then
  `getTokenSync(warning.i18n)`. Fall back to the warning `kind` when resolution fails.
- Attach the scanned file path to each warning and extract line/column from the warning
  `location` array defensively; malformed locations are omitted, never guessed.

## Severity normalization

Normalized buckets, ordered most to least severe: `critical`, `high`, `medium`, `low`,
`info`, `unknown`.

| Source | Critical | High | Medium | Low | Info |
| --- | --- | --- | --- | --- | --- |
| PySentry | critical | high | medium | low | unknown → unknown |
| Bandit | — | HIGH | MEDIUM | LOW | — |
| Bun/NPM audit | critical | high | moderate | low | info |
| JS-X-Ray | Critical | — | Warning | — | Information |

Bandit confidence (`HIGH`/`MEDIUM`/`LOW`) is retained as a separate column, not folded into
severity. Unknown values map to `unknown`.

## Report model and JSON snapshot

`report.json` records the model that produced the HTML, with `schemaVersion: 1`:

```ts
type Severity = "critical" | "high" | "medium" | "low" | "info" | "unknown";
type Section = "sca" | "sast";
type Ecosystem = "python" | "javascript";
type ScannerStatus = "ok" | "partial" | "failed";

interface Finding {
  id: string;                 // stable: tool + rule + target + location
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
  file?: string;              // project-relative
  line?: number;
  column?: number;
  confidence?: string;        // Bandit only
  referenceUrl?: string | null;
  fix?: string | null;
  suppressed?: string | null;
}

interface ScannerResult {
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
}

interface ReportModel {
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
    lockfiles: { path: string; sha256: string }[];
  };
  tools: ScannerResult[];
  sections: {
    sca: { severityCounts: Record<Severity, number>; findings: Finding[] };
    sast: { severityCounts: Record<Severity, number>; findings: Finding[] };
  };
  limitations: string[];
}
```

Severity counts exclude findings that the scanner marked `suppressed` (PySentry can emit
this field). Suppressed findings are still listed in the appendix and appear in
`report.json` under their scanner, with the suppression reason.

`GitCoordinates` includes: repository root, remote URL (or null), branch, full and short
HEAD SHA, tree SHA, `git describe --tags --always --dirty` when available, latest tag when
available, author name/email, author date, subject, dirty flag, and per-status file counts
from porcelain v2.

## Report layout and visual system

The HTML is one self-contained document (`lang="en"`): inline CSS, inline SVG, embedded
base64 fonts, no JavaScript, and no network requests.

### Theme

Light, print-first, derived from the app's design tokens:

- Body: Inter. Headings and cover wordmark: Silkscreen. SHAs, paths, commands: JetBrains Mono.
- Phosphor-green accent (`#087a43` on light), 1px borders, 2–4px radii.
- Subtle phosphor grid on the cover only; no scanlines.
- Static `[AGENTBOX]▮` wordmark.
- Classification label in uppercase monospace at the top right of the cover and in footers.

Severity colors: critical `#b42318`, high `#a31c8c`, medium `#9a5a00`, low `#007a99`,
info `#5a6658`, unknown grey. Legends always carry text labels and counts, never color
alone.

### Pages and sections

1. **Cover** — wordmark, “Security Audit Report”, project name, classification, generation
   date, `branch @ short-SHA`, dirty state, overall status (`N findings · M high` or a green
   “No findings”), report ID.
2. **Audit coordinates** — repository root (home prefix collapsed to `~`), remote, branch,
   HEAD SHA, tree SHA, describe, latest tag, author/date/subject, dirty file count;
   component versions; lockfile SHA-256 hashes; scanner versions; scan start/end UTC; scope
   and exclusion summary.
3. **Executive summary** — overall verdict, two summary cards (SCA and SAST) each with a
   donut pie and severity counts/total, a combined severity matrix (rows: severity buckets;
   columns: SCA, SAST, total), and up to 10 top findings sorted by severity.
4. **SCA** — combined SCA donut; a Python (PySentry) block and a JavaScript (Bun/NPM audit)
   block. Each block shows packages scanned, findings table, and tool warnings. PySentry fix
   suggestions and maintenance issues get their own tables. A partial-scan banner appears
   when applicable.
5. **SAST** — combined SAST donut; a Bandit block (files scanned, severity, confidence, rule,
   file:line, text, reference) and a JS-X-Ray block (files scanned, warning kind, file:line,
   code snippet, description).
6. **Appendix** — tool inventory with commands, exit statuses, durations and warnings;
   component and lockfile inventory; scanner-suppressed findings (excluded from counts, with
   reasons); limitations; severity glossary.

### Charts

Inline SVG donuts, fixed 180px, center total, legend with count and percentage for every
bucket. One combined donut per section, plus a per-tool stacked severity strip instead of
extra pies. Zero findings renders a green “clean” ring with an explicit “0 findings” label.

### Tables

Columns: severity badge, rule/advisory ID, target (package or file:line), title/detail,
confidence (Bandit), fix/reference. Sorted by severity descending, then target, then rule.
Long detail text is truncated in the table and included in `report.json`. External reference
URLs are displayed as text and hyperlinked only when they use `http` or `https`.

### Print and PDF

- A4, `preferCSSPageSize`, print backgrounds, approximately 16 mm margins.
- Page break before each major section; table headers repeat; rows avoid splitting.
- Footer includes page number, report ID, short SHA, and generation timestamp.
- Playwright Chromium renders the local HTML file with JavaScript disabled.

## CLI and artifacts

```
bun run scripts/security-report/src/main.ts [path] [options]

  path                       project to audit (default: git root of cwd)
  --out <dir>                output directory (default: reports/security)
  --classification <text>    label on the report (default: Internal)
  --fail-on <level>          none|low|medium|high|critical (default: none)
  --allow-partial            exit 0 when a scanner is partial or failed
  --no-pdf                   skip PDF generation
  --include-tests            include tests/fixtures/specs/stories in SAST
  --exclude <glob>           additional source exclusion (repeatable)
  --scanner-timeout <secs>   per-subprocess-scanner timeout (default: 300)
  --from-fixtures <dir>      test mode: load structured fixtures, do not run scanners
  --verbose                  progress and diagnostics on stderr
  -h, --help
```

Artifacts, where `<id>` is `<shortsha|nogit>-<YYYYMMDDTHHMMSSZ>` and the report ID is
`agentbox-security-<id>`:

```
reports/security/agentbox-security-<id>.html
reports/security/agentbox-security-<id>.pdf
reports/security/agentbox-security-<id>.json
reports/security/latest.html
reports/security/latest.pdf
reports/security/latest.json
```

The project name comes from the root `package.json` name, then `[project].name`, then the
root directory basename. Print a concise summary to stderr: section counts, artifact paths,
partial/failed scanners, and the exit reason.

## Failure handling and exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success; report written; no gate triggered |
| 1 | A scanner is partial/failed (unless `--allow-partial`), or PDF generation failed |
| 2 | Usage or configuration error |
| 3 | `--fail-on` threshold met; artifacts are written first |

- Findings never fail the run unless `--fail-on` is set.
- A scanner timeout, unavailable tool, or unparseable payload marks that scanner `failed`
  with the command, exit code, and escaped stderr tail (bounded length). Other scanners
  still run and the report is still written with a banner.
- If every scanner fails, the exit code is `1` even with `--allow-partial`, and the report
  states that no usable results were produced.
- PDF failure leaves HTML and JSON written and prints the
  `bunx playwright install chromium` hint.
- `--no-pdf` is an explicit opt-out and does not affect the exit code.

## Security considerations

- HTML-escape every scanner-provided value: titles, details, package names, file paths,
  snippets, warnings, stderr tails.
- Allowlist reference URLs to `http`/`https`; render anything else as inert text.
- The HTML contains no scripts and performs no network requests. PDF rendering disables
  JavaScript.
- Do not read or emit environment variables, credentials, tokens, or scanner command lines
  containing secrets (the commands used here take none).
- Truncate embedded code snippets and stderr tails to bounded lengths.
- Write only under the requested output directory; create it if missing.

## Testing

Run with `bun test` in `scripts/security-report`; all tests are offline.

- Fixtures: PySentry JSON (all severities, partial scan, fixes, maintenance issues), Bandit
  JSON (severities and confidence), Bun audit JSON, NPM audit JSON, JS-X-Ray warnings with
  locations, a `bun.lock`/`package-lock.json` version map, and git metadata. The
  `--from-fixtures` directory uses one file per source: `pysentry.json`, `bandit.json`,
  `bun-audit.json`, `npm-audit.json`, `jsxray.json`, `lockfiles.json`, `git.json`, and
  `project.json`.
- Unit tests: severity normalization and ordering; finding ID stability; table sorting;
  donut slice math (sums to 360°, zero and single-bucket cases); HTML escaping with a
  malicious advisory title; URL allowlisting; discovery and exclusion logic; git parsing
  from structured output.
- Integration test: `--from-fixtures <dir> --no-pdf` writes deterministic HTML and JSON;
  assert all required sections, severity counts, and that injected markup is escaped.
- Optional PDF smoke test behind `SECURITY_REPORT_PDF_TEST=1`: render a fixture report and
  assert a `%PDF` header and non-empty output.
- Type-check with `tsc --noEmit`.

## Dependencies

`scripts/security-report/package.json` pins:

- `@nodesecure/js-x-ray@16.2.0`
- `@nodesecure/i18n@4.1.1`
- `playwright@1.65.1` (reuses the Chromium already installed for the web app)
- `typescript@5.9.3` (required for `TsSourceParser`)
- `@types/bun` (compatible with the Bun version in use)

Commit `bun.lock`. The tool shells out to `uvx`/`uv`, `bun`/`npm`, and `git`; these are
already required by the repository.

## Repository integration

Add to the root `justfile`:

```
_security-report-deps:
    bun install --cwd scripts/security-report --frozen-lockfile

security-report *args: _security-report-deps
    bun run scripts/security-report/src/main.ts {{args}}

test-security-report: _security-report-deps
    bun run --cwd scripts/security-report test
    bun run --cwd scripts/security-report typecheck
```

- Add `bun install --cwd scripts/security-report` to `setup`.
- Add `test-security-report` to `check`.
- Add `/reports/` to `.gitignore`.
- Add a short `scripts/security-report/README.md` covering usage, flags, exit codes,
  artifacts, exclusions, and adding a scanner.
- Add the new recipe and test command to `AGENTS.md`.
- Do not modify `docs/ROADMAP.md`; this is developer tooling, not a product feature.

## Limitations to state in the report

- SCA relies on the vulnerability sources reachable at scan time (PyPA, PyPI, OSV, GitHub
  advisories); partial scans are flagged.
- SAST excludes tests/fixtures/stories by default; use `--include-tests` for full coverage.
- No runtime, dynamic, container, secret, or license scanning is performed.
- JS-X-Ray reports its own confidence/severity model; normalization is documented above.
- Findings marked suppressed by a scanner are listed in the appendix but excluded from
  severity counts and gates.
- Reports reflect the working tree at scan time, including uncommitted changes; the git
  coordinates section records the dirty state.
