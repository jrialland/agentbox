# Security Audit Report Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `just security-report` to generate a brand-consistent, print-first HTML security audit report, convert it to PDF, and write a machine-readable JSON snapshot.

**Architecture:** A self-contained Bun/TypeScript package under `scripts/security-report/` orchestrates PySentry, Bandit, Bun/NPM audit, and JS-X-Ray, normalizes their structured findings into one model, renders inline CSS/SVG HTML, and renders PDF with Playwright Chromium.

**Tech Stack:** Bun 1.4+, TypeScript 5.9, `@nodesecure/js-x-ray` 16.2.0, `@nodesecure/i18n` 4.1.1, Playwright 1.65.1, PySentry (`uvx pysentry-rs`), Bandit (`uv run bandit`), Bun/NPM audit, Git.

## Global Constraints

- Tool location: `scripts/security-report/`; artifacts: `reports/security/` (gitignored).
- Report theme: light, print-first, app brand tokens; language: English.
- Parse only structured outputs: PySentry JSON, Bandit JSON, Bun/NPM audit JSON, JS-X-Ray warning objects. Never scrape human output.
- Pinned libraries: `@nodesecure/js-x-ray@16.2.0`, `@nodesecure/i18n@4.1.1`, `playwright@1.65.1`, `typescript@5.9.3`.
- Exit codes: `0` success, `1` partial/failed/PDF failure, `2` usage error, `3` `--fail-on` gate. Findings do not fail the run unless gated.
- `--fail-on` default: `none`. `--classification` default: `Internal`. `--scanner-timeout` default: `300` seconds.
- SAST default exclusions: `.venv`, `venv`, `node_modules`, `dist`, `build`, `coverage`, `.next`, `out`, `.git`, `__pycache__`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache`, `site-packages`, plus `tests`, `fixtures`, `*.test.*`, `*.spec.*`, `*.stories.*` unless `--include-tests`.
- A4 PDF, print backgrounds, CSS page size, page breaks before major sections.
- HTML is self-contained: inline CSS/SVG, embedded base64 fonts, no JavaScript, no network requests.
- Do not modify `docs/ROADMAP.md`; this is developer tooling.
- Use conventional commits. Run checks with `bun run --cwd scripts/security-report test` and `typecheck`.

---

## File Structure

```
scripts/security-report/
  package.json
  bun.lock
  tsconfig.json
  README.md
  assets/fonts/                  Silkscreen, Inter, JetBrains Mono woff2 + licenses
  src/
    model.ts                     shared types and finding IDs
    severity.ts                  normalization, ordering, counts, colors
    report.ts                    report model assembly, exit-code gating
    test-helpers.ts              model factory for tests
    cli.ts                       argument parsing and help
    git.ts                       git coordinates
    project.ts                   discovery, lockfile hashes/versions, file walk
    fixtures.ts                  --from-fixtures loader
    main.ts                      orchestration, artifacts, CLI entry
    pdf.ts                       Playwright PDF rendering
    scanners/
      types.ts                   ScanContext and ParsedScanner
      process.ts                 subprocess runner, version helpers, tail
      pysentry.ts                Python SCA
      bandit.ts                  Python SAST
      bun-audit.ts               JavaScript SCA (Bun/NPM)
      jsxray.ts                  JavaScript/TypeScript SAST
    render/
      components.ts              escaping, URL allowlist, paths, badges
      charts.ts                  inline SVG donuts and legends
      fonts.ts                   base64 font CSS
      styles.ts                  print CSS
      html.ts                    document assembly
    *.test.ts
```

---

### Task 1: Scaffold the tool, shared model, and severity normalization

**Files:**
- Create: `scripts/security-report/package.json`
- Create: `scripts/security-report/tsconfig.json`
- Create: `scripts/security-report/src/model.ts`
- Create: `scripts/security-report/src/severity.ts`
- Test: `scripts/security-report/src/severity.test.ts`
- Generated: `scripts/security-report/bun.lock`

**Interfaces:**
- Produces:
  - Types `Severity`, `Section`, `Ecosystem`, `ScannerStatus`, `Finding`, `ScannerResult`, `MaintenanceIssue`, `GitCoordinates`, `ComponentInfo`, `LockfileInfo`, `SectionSummary`, `ReportModel`.
  - `makeFindingId(input)`, `findingTarget(finding)` from `model.ts`.
  - `SEVERITIES`, `SEVERITY_LABEL`, `SEVERITY_COLOR`, `normalizeSeverity`, `severityRank`, `emptySeverityCounts`, `countSeverities`, `sortFindings`, `countAtOrAbove` from `severity.ts`.

- [ ] **Step 1: Create the package manifest and TypeScript config**

`scripts/security-report/package.json`:

```json
{
  "name": "agentbox-security-report",
  "private": true,
  "type": "module",
  "scripts": {
    "report": "bun run src/main.ts",
    "test": "bun test",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "@nodesecure/i18n": "4.1.1",
    "@nodesecure/js-x-ray": "16.2.0",
    "playwright": "1.65.1"
  },
  "devDependencies": {
    "@types/bun": "latest",
    "typescript": "5.9.3"
  }
}
```

`scripts/security-report/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "lib": ["ES2022", "DOM"],
    "types": ["bun"],
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "skipLibCheck": true,
    "noEmit": true
  },
  "include": ["src/**/*.ts"]
}
```

- [ ] **Step 2: Install dependencies and commit the lockfile**

Run: `bun install --cwd scripts/security-report`

Expected: `scripts/security-report/node_modules` and `scripts/security-report/bun.lock` created.

- [ ] **Step 3: Write the failing severity test**

`scripts/security-report/src/severity.test.ts`:

```ts
import { describe, expect, test } from "bun:test";
import type { Finding } from "./model";
import { makeFindingId } from "./model";
import {
  countAtOrAbove,
  countSeverities,
  normalizeSeverity,
  sortFindings,
} from "./severity";

function finding(partial: Partial<Finding>): Finding {
  return {
    id: "id",
    section: "sast",
    ecosystem: "python",
    tool: "tool",
    severity: "low",
    sourceSeverity: "LOW",
    ruleId: "B101",
    title: "title",
    detail: null,
    ...partial,
  };
}

describe("normalizeSeverity", () => {
  test("maps every scanner vocabulary", () => {
    expect(normalizeSeverity("CRITICAL")).toBe("critical");
    expect(normalizeSeverity("HIGH")).toBe("high");
    expect(normalizeSeverity("MEDIUM")).toBe("medium");
    expect(normalizeSeverity("moderate")).toBe("medium");
    expect(normalizeSeverity("Warning")).toBe("medium");
    expect(normalizeSeverity("LOW")).toBe("low");
    expect(normalizeSeverity("Information")).toBe("info");
    expect(normalizeSeverity("unknown")).toBe("unknown");
    expect(normalizeSeverity("")).toBe("unknown");
    expect(normalizeSeverity(null)).toBe("unknown");
  });
});

describe("countSeverities", () => {
  test("counts and excludes suppressed findings", () => {
    const counts = countSeverities([
      finding({ severity: "critical" }),
      finding({ severity: "high" }),
      finding({ severity: "high", suppressed: "ignored_package" }),
    ]);
    expect(counts.critical).toBe(1);
    expect(counts.high).toBe(1);
    expect(counts.low).toBe(0);
  });
});

describe("sortFindings", () => {
  test("sorts by severity then target then rule", () => {
    const sorted = sortFindings([
      finding({ severity: "low", file: "b.ts", ruleId: "B2" }),
      finding({ severity: "critical", file: "z.ts", ruleId: "B1" }),
      finding({ severity: "low", file: "a.ts", ruleId: "B2" }),
    ]);
    expect(sorted.map((item) => item.file)).toEqual(["z.ts", "a.ts", "b.ts"]);
  });
});

describe("countAtOrAbove", () => {
  test("counts only non-suppressed findings at or above the threshold", () => {
    expect(
      countAtOrAbove(
        [
          finding({ severity: "critical" }),
          finding({ severity: "high" }),
          finding({ severity: "medium" }),
          finding({ severity: "high", suppressed: "ignored_package" }),
        ],
        "high",
      ),
    ).toBe(2);
  });
});

describe("makeFindingId", () => {
  test("is stable and target-specific", () => {
    const base = { tool: "Bandit", ruleId: "B101", title: "assert", file: "a.py", line: 4 };
    expect(makeFindingId(base)).toBe(makeFindingId(base));
    expect(makeFindingId(base)).not.toBe(makeFindingId({ ...base, line: 5 }));
    expect(makeFindingId(base)).toHaveLength(12);
  });
});
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `bun run --cwd scripts/security-report test -- src/severity.test.ts`

Expected: FAIL with a module-not-found error for `./severity`.

- [ ] **Step 5: Write `model.ts`**

`scripts/security-report/src/model.ts`:

```ts
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
```

- [ ] **Step 6: Write `severity.ts`**

`scripts/security-report/src/severity.ts`:

```ts
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
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `bun run --cwd scripts/security-report test -- src/severity.test.ts`

Expected: PASS (5 describe blocks).

- [ ] **Step 8: Type-check**

Run: `bun run --cwd scripts/security-report typecheck`

Expected: no errors.

- [ ] **Step 9: Commit**

```bash
git add scripts/security-report/package.json scripts/security-report/bun.lock scripts/security-report/tsconfig.json scripts/security-report/src/model.ts scripts/security-report/src/severity.ts scripts/security-report/src/severity.test.ts
git commit -m "feat(security-report): scaffold tool and severity model"
```

---

### Task 2: HTML escaping, URL allowlisting, path display, badges

**Files:**
- Create: `scripts/security-report/src/render/components.ts`
- Test: `scripts/security-report/src/render/components.test.ts`

**Interfaces:**
- Produces: `escapeHtml(value)`, `safeUrl(value)`, `toPosix(value)`, `displayPath(root, file)`, `severityBadge(severity)`.
- Consumes: `Severity`, `SEVERITY_LABEL` from Task 1.

- [ ] **Step 1: Write the failing test**

`scripts/security-report/src/render/components.test.ts`:

```ts
import { describe, expect, test } from "bun:test";
import { displayPath, escapeHtml, safeUrl, severityBadge, truncate } from "./components";

describe("escapeHtml", () => {
  test("escapes every HTML metacharacter", () => {
    expect(escapeHtml(`<script>"x" & 'y'</script>`)).toBe(
      "&lt;script&gt;&quot;x&quot; &amp; &#39;y&#39;&lt;/script&gt;",
    );
    expect(escapeHtml(null)).toBe("");
  });
});

describe("safeUrl", () => {
  test("allows only http and https", () => {
    expect(safeUrl("https://example.com/a")).toBe("https://example.com/a");
    expect(safeUrl("http://example.com")).toBe("http://example.com/");
    expect(safeUrl("javascript:alert(1)")).toBeNull();
    expect(safeUrl("file:///etc/passwd")).toBeNull();
    expect(safeUrl(null)).toBeNull();
  });
});

describe("displayPath", () => {
  test("returns a project-relative posix path", () => {
    expect(displayPath("/repo", "/repo/src/a.ts")).toBe("src/a.ts");
    expect(displayPath("/repo", "/elsewhere/a.ts")).toBe("/elsewhere/a.ts");
    expect(displayPath("/repo", undefined)).toBeNull();
  });
});

describe("truncate", () => {
  test("bounds text and marks the cut", () => {
    expect(truncate("abcdef", 3)).toBe("ab…");
    expect(truncate("abc", 10)).toBe("abc");
  });
});

describe("severityBadge", () => {
  test("renders a labeled badge", () => {
    expect(severityBadge("high")).toBe('<span class="badge badge-high">High</span>');
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `bun run --cwd scripts/security-report test -- src/render/components.test.ts`

Expected: FAIL with module-not-found for `./components`.

- [ ] **Step 3: Implement `components.ts`**

`scripts/security-report/src/render/components.ts`:

```ts
import { relative, sep } from "node:path";
import type { Severity } from "../severity";
import { SEVERITY_LABEL } from "../severity";

const ESCAPES: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

export function escapeHtml(value: unknown): string {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ESCAPES[char] ?? char);
}

export function safeUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}

export function toPosix(value: string): string {
  return value.split(sep).join("/");
}

export function displayPath(root: string, file: string | null | undefined): string | null {
  if (!file) return null;
  const rel = relative(root, file);
  return toPosix(rel.startsWith("..") ? file : rel);
}

export function truncate(value: string, max: number): string {
  return value.length <= max ? value : `${value.slice(0, Math.max(0, max - 1))}…`;
}

export function severityBadge(severity: Severity): string {
  return `<span class="badge badge-${severity}">${SEVERITY_LABEL[severity]}</span>`;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `bun run --cwd scripts/security-report test -- src/render/components.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/security-report/src/render/components.ts scripts/security-report/src/render/components.test.ts
git commit -m "feat(security-report): add safe HTML rendering primitives"
```

---

### Task 3: Inline SVG donut charts and severity legend

**Files:**
- Create: `scripts/security-report/src/render/charts.ts`
- Test: `scripts/security-report/src/render/charts.test.ts`

**Interfaces:**
- Produces: `SeveritySlice`, `renderDonut(slices, options)`, `renderSeverityLegend(counts)`, `renderSeverityStrip(counts)`.
- Consumes: `Severity`, `SEVERITIES`, `SEVERITY_COLOR`, `SEVERITY_LABEL`, `emptySeverityCounts`, `escapeHtml`.

- [ ] **Step 1: Write the failing test**

`scripts/security-report/src/render/charts.test.ts`:

```ts
import { describe, expect, test } from "bun:test";
import { emptySeverityCounts } from "../severity";
import { renderDonut, renderSeverityLegend, renderSeverityStrip } from "./charts";

describe("renderDonut", () => {
  test("renders one segment per non-zero bucket", () => {
    const svg = renderDonut([
      { severity: "critical", count: 1 },
      { severity: "high", count: 1 },
      { severity: "low", count: 0 },
    ]);
    expect(svg).toContain('data-total="2"');
    expect(svg.match(/class="pie-slice"/g)).toHaveLength(2);
    expect(svg).toContain('data-severity="critical"');
    expect(svg).toContain('data-severity="high"');
    expect(svg).not.toContain('data-severity="low"');
  });

  test("renders a clean ring when there are no findings", () => {
    const svg = renderDonut([{ severity: "critical", count: 0 }]);
    expect(svg).toContain('data-empty="true"');
    expect(svg).toContain("0");
  });
});

describe("renderSeverityLegend", () => {
  test("shows every bucket with counts and percentages", () => {
    const counts = emptySeverityCounts();
    counts.critical = 1;
    counts.high = 1;
    const html = renderSeverityLegend(counts);
    expect(html).toContain("Critical");
    expect(html).toContain(">1<");
    expect(html).toContain("50%");
    expect(html).toContain("Unknown");
  });
});

describe("renderSeverityStrip", () => {
  test("renders one segment per non-zero bucket", () => {
    const counts = emptySeverityCounts();
    counts.high = 1;
    counts.low = 1;
    const html = renderSeverityStrip(counts);
    expect(html).toContain('data-total="2"');
    expect(html.match(/strip-seg/g)).toHaveLength(2);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `bun run --cwd scripts/security-report test -- src/render/charts.test.ts`

Expected: FAIL with module-not-found for `./charts`.

- [ ] **Step 3: Implement `charts.ts`**

`scripts/security-report/src/render/charts.ts`:

```ts
import type { Severity } from "../severity";
import {
  SEVERITIES,
  SEVERITY_COLOR,
  SEVERITY_LABEL,
} from "../severity";
import { escapeHtml } from "./components";

export interface SeveritySlice {
  severity: Severity;
  count: number;
}

export function renderDonut(
  slices: SeveritySlice[],
  options: { size?: number; label?: string } = {},
): string {
  const size = options.size ?? 180;
  const stroke = Math.round(size * 0.16);
  const radius = (size - stroke) / 2;
  const center = size / 2;
  const circumference = 2 * Math.PI * radius;
  const total = slices.reduce((sum, slice) => sum + slice.count, 0);
  const label = escapeHtml(options.label ?? "findings");

  if (total === 0) {
    return `<svg class="donut" viewBox="0 0 ${size} ${size}" role="img" aria-label="No findings" data-empty="true" data-total="0"><circle cx="${center}" cy="${center}" r="${radius}" fill="none" stroke="#087a43" stroke-width="${stroke}" /><text x="${center}" y="${center}" dominant-baseline="central" text-anchor="middle" class="donut-total">0</text><text x="${center}" y="${center + 22}" dominant-baseline="central" text-anchor="middle" class="donut-label">${label}</text></svg>`;
  }

  let offset = 0;
  const segments = slices
    .filter((slice) => slice.count > 0)
    .map((slice) => {
      const length = (slice.count / total) * circumference;
      const segment = `<circle class="pie-slice" data-severity="${slice.severity}" cx="${center}" cy="${center}" r="${radius}" fill="none" stroke="${SEVERITY_COLOR[slice.severity]}" stroke-width="${stroke}" stroke-dasharray="${length} ${circumference - length}" stroke-dashoffset="${-offset}" transform="rotate(-90 ${center} ${center})"><title>${SEVERITY_LABEL[slice.severity]}: ${slice.count}</title></circle>`;
      offset += length;
      return segment;
    })
    .join("");

  return `<svg class="donut" viewBox="0 0 ${size} ${size}" role="img" aria-label="${total} ${label}" data-empty="false" data-total="${total}">${segments}<text x="${center}" y="${center}" dominant-baseline="central" text-anchor="middle" class="donut-total">${total}</text><text x="${center}" y="${center + 22}" dominant-baseline="central" text-anchor="middle" class="donut-label">${label}</text></svg>`;
}

export function renderSeverityLegend(counts: Record<Severity, number>): string {
  const total = SEVERITIES.reduce((sum, severity) => sum + counts[severity], 0);
  const rows = SEVERITIES.map((severity) => {
    const percent = total === 0 ? 0 : Math.round((counts[severity] / total) * 100);
    return `<li><span class="legend-dot" style="background:${SEVERITY_COLOR[severity]}"></span><span class="legend-label">${SEVERITY_LABEL[severity]}</span><span class="legend-count">${counts[severity]}</span><span class="legend-pct">${percent}%</span></li>`;
  }).join("");
  return `<ul class="legend">${rows}</ul>`;
}

export function renderSeverityStrip(counts: Record<Severity, number>): string {
  const total = SEVERITIES.reduce((sum, severity) => sum + counts[severity], 0);
  if (total === 0) {
    return `<div class="strip" data-total="0"><span class="strip-empty"></span></div>`;
  }
  const segments = SEVERITIES.filter((severity) => counts[severity] > 0)
    .map(
      (severity) =>
        `<span class="strip-seg" style="width:${(counts[severity] / total) * 100}%;background:${SEVERITY_COLOR[severity]}" title="${SEVERITY_LABEL[severity]}: ${counts[severity]}"></span>`,
    )
    .join("");
  return `<div class="strip" data-total="${total}">${segments}</div>`;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `bun run --cwd scripts/security-report test -- src/render/charts.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/security-report/src/render/charts.ts scripts/security-report/src/render/charts.test.ts
git commit -m "feat(security-report): add severity donut charts"
```

---

### Task 4: Subprocess runner, version helpers, stderr tail

**Files:**
- Create: `scripts/security-report/src/scanners/process.ts`
- Test: `scripts/security-report/src/scanners/process.test.ts`

**Interfaces:**
- Produces:
  - `ProcessResult`, `runProcess(command, args, options)`
  - `CommandResult`, `CommandRunner`, `defaultCommandRunner`
  - `commandVersion(command, args, cwd)`, `tail(value, max)`
- Consumes: Bun only.

- [ ] **Step 1: Write the failing test**

`scripts/security-report/src/scanners/process.test.ts`:

```ts
import { describe, expect, test } from "bun:test";
import { commandVersion, runProcess, tail } from "./process";

describe("runProcess", () => {
  test("captures stdout and exit code", async () => {
    const result = await runProcess("bun", ["-e", "console.log('hello')"], {
      cwd: process.cwd(),
      timeoutMs: 10_000,
    });
    expect(result.exitCode).toBe(0);
    expect(result.stdout.trim()).toBe("hello");
    expect(result.timedOut).toBe(false);
  });

  test("marks a timeout", async () => {
    const result = await runProcess("bun", ["-e", "await Bun.sleep(2000)"], {
      cwd: process.cwd(),
      timeoutMs: 100,
    });
    expect(result.timedOut).toBe(true);
  });
});

describe("commandVersion", () => {
  test("extracts a version token", async () => {
    const version = await commandVersion("bun", ["--version"], process.cwd());
    expect(version).toMatch(/^\d+\.\d+\.\d+/);
  });
});

describe("tail", () => {
  test("bounds long text to the end", () => {
    expect(tail("abcdef", 3)).toBe("def");
    expect(tail("abc", 10)).toBe("abc");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `bun run --cwd scripts/security-report test -- src/scanners/process.test.ts`

Expected: FAIL with module-not-found for `./process`.

- [ ] **Step 3: Implement `process.ts`**

`scripts/security-report/src/scanners/process.ts`:

```ts
export interface ProcessResult {
  stdout: string;
  stderr: string;
  exitCode: number;
  timedOut: boolean;
  durationMs: number;
}

export interface CommandResult {
  stdout: string;
  stderr: string;
  exitCode: number;
}

export type CommandRunner = (
  command: string,
  args: string[],
  cwd: string,
) => Promise<CommandResult>;

export async function runProcess(
  command: string,
  args: string[],
  options: { cwd: string; timeoutMs: number },
): Promise<ProcessResult> {
  const started = performance.now();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeoutMs);

  try {
    const proc = Bun.spawn([command, ...args], {
      cwd: options.cwd,
      stdout: "pipe",
      stderr: "pipe",
      signal: controller.signal,
    });
    const [stdout, stderr, exitCode] = await Promise.all([
      new Response(proc.stdout).text(),
      new Response(proc.stderr).text(),
      proc.exited,
    ]);
    return {
      stdout,
      stderr,
      exitCode,
      timedOut: controller.signal.aborted,
      durationMs: Math.round(performance.now() - started),
    };
  } catch (error) {
    return {
      stdout: "",
      stderr: error instanceof Error ? error.message : String(error),
      exitCode: -1,
      timedOut: controller.signal.aborted,
      durationMs: Math.round(performance.now() - started),
    };
  } finally {
    clearTimeout(timer);
  }
}

export const defaultCommandRunner: CommandRunner = async (command, args, cwd) => {
  const result = await runProcess(command, args, { cwd, timeoutMs: 30_000 });
  return {
    stdout: result.stdout,
    stderr: result.stderr,
    exitCode: result.exitCode,
  };
};

export async function commandVersion(
  command: string,
  args: string[],
  cwd: string,
): Promise<string> {
  const result = await runProcess(command, args, { cwd, timeoutMs: 20_000 });
  const firstLine = (result.stdout || result.stderr)
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find((line) => line.length > 0);
  const match = firstLine?.match(/\d+\.\d+\.\d+[\w.-]*/);
  return match?.[0] ?? "unknown";
}

export function tail(value: string, max = 2000): string {
  return value.length <= max ? value : value.slice(value.length - max);
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `bun run --cwd scripts/security-report test -- src/scanners/process.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/security-report/src/scanners/process.ts scripts/security-report/src/scanners/process.test.ts
git commit -m "feat(security-report): add subprocess runner and version helpers"
```

---

### Task 5: Git coordinates

**Files:**
- Create: `scripts/security-report/src/git.ts`
- Test: `scripts/security-report/src/git.test.ts`

**Interfaces:**
- Produces: `resolveRepoRoot(cwd, run)`, `collectGit(cwd, run)`.
- Consumes: `GitCoordinates`, `StatusCounts` from Task 1; `CommandRunner`, `defaultCommandRunner` from Task 4.

- [ ] **Step 1: Write the failing test**

`scripts/security-report/src/git.test.ts`:

```ts
import { describe, expect, test } from "bun:test";
import type { CommandRunner } from "./scanners/process";
import { collectGit, resolveRepoRoot } from "./git";

const outputs: Record<string, string> = {
  "rev-parse --show-toplevel": "/repo\n",
  "remote get-url origin": "git@example.com:org/repo.git\n",
  "rev-parse --abbrev-ref HEAD": "main\n",
  "rev-parse HEAD": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n",
  "rev-parse --short HEAD": "aaaaaaa\n",
  "rev-parse HEAD^{tree}": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n",
  "describe --tags --always --dirty": "v1.2.3-2-gaaaaaaa-dirty\n",
  "for-each-ref refs/tags --sort=-creatordate --format=%(refname:short) --count=1": "v1.2.3\n",
  "log -1 --format=%H%x00%T%x00%an%x00%ae%x00%aI%x00%s":
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\u0000bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\u0000Ada\u0000ada@example.com\u00002026-11-22T10:00:00+00:00\u0000Add report\n",
  "status --porcelain=v2 --untracked-files=normal":
    "1 .M N... 100644 100644 100644 aaa bbb src/a.ts\n? new-file.ts\n2 R. N... 100644 100644 100644 aaa bbb src/b.ts\tsrc/c.ts\n",
};

const fakeRun: CommandRunner = async (_command, args) => {
  const key = args.join(" ");
  const stdout = outputs[key];
  return { stdout: stdout ?? "", stderr: "", exitCode: stdout === undefined ? 1 : 0 };
};

describe("resolveRepoRoot", () => {
  test("returns the git top-level directory", async () => {
    expect(await resolveRepoRoot("/repo/src", fakeRun)).toBe("/repo");
  });
});

describe("collectGit", () => {
  test("parses coordinates and dirty status", async () => {
    const git = await collectGit("/repo", fakeRun);
    expect(git.remoteUrl).toBe("git@example.com:org/repo.git");
    expect(git.branch).toBe("main");
    expect(git.headSha).toHaveLength(40);
    expect(git.headShortSha).toBe("aaaaaaa");
    expect(git.describe).toBe("v1.2.3-2-gaaaaaaa-dirty");
    expect(git.latestTag).toBe("v1.2.3");
    expect(git.authorName).toBe("Ada");
    expect(git.subject).toBe("Add report");
    expect(git.dirty).toBe(true);
    expect(git.dirtyFiles).toBe(3);
    expect(git.statusCounts.untracked).toBe(1);
    expect(git.statusCounts.renamed).toBe(1);
    expect(git.statusCounts.modified).toBe(1);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `bun run --cwd scripts/security-report test -- src/git.test.ts`

Expected: FAIL with module-not-found for `./git`.

- [ ] **Step 3: Implement `git.ts`**

`scripts/security-report/src/git.ts`:

```ts
import type { GitCoordinates, StatusCounts } from "./model";
import {
  defaultCommandRunner,
  type CommandRunner,
} from "./scanners/process";

async function git(
  cwd: string,
  args: string[],
  run: CommandRunner,
): Promise<string | null> {
  const result = await run("git", args, cwd);
  if (result.exitCode !== 0) return null;
  return result.stdout.trim();
}

export async function resolveRepoRoot(
  cwd: string,
  run: CommandRunner = defaultCommandRunner,
): Promise<string> {
  const root = await git(cwd, ["rev-parse", "--show-toplevel"], run);
  return root && root.length > 0 ? root : cwd;
}

function parseStatus(porcelain: string): {
  dirty: boolean;
  dirtyFiles: number;
  statusCounts: StatusCounts;
} {
  const lines = porcelain.split(/\r?\n/).filter((line) => line.length > 0);
  const counts: StatusCounts = {
    added: 0,
    modified: 0,
    deleted: 0,
    renamed: 0,
    untracked: 0,
    unmerged: 0,
  };

  for (const line of lines) {
    if (line.startsWith("? ")) {
      counts.untracked += 1;
      continue;
    }
    if (line.startsWith("u ")) {
      counts.unmerged += 1;
      continue;
    }
    if (!line.startsWith("1 ") && !line.startsWith("2 ")) continue;

    const index = line[2];
    const worktree = line[3];
    const codes = `${index}${worktree}`;
    if (codes.includes("A")) counts.added += 1;
    else if (codes.includes("D")) counts.deleted += 1;
    else if (codes.includes("R") || codes.includes("C")) counts.renamed += 1;
    else counts.modified += 1;
  }

  return { dirty: lines.length > 0, dirtyFiles: lines.length, statusCounts: counts };
}

export async function collectGit(
  cwd: string,
  run: CommandRunner = defaultCommandRunner,
): Promise<GitCoordinates> {
  const root = (await git(cwd, ["rev-parse", "--show-toplevel"], run)) ?? cwd;
  const log = await git(
    cwd,
    ["log", "-1", "--format=%H%x00%T%x00%an%x00%ae%x00%aI%x00%s"],
    run,
  );
  const [headSha = "", treeSha = "", authorName = "", authorEmail = "", authoredAt = "", subject = ""] =
    (log ?? "").split("\u0000");

  const status = parseStatus(
    (await git(cwd, ["status", "--porcelain=v2", "--untracked-files=normal"], run)) ?? "",
  );

  return {
    root,
    remoteUrl: await git(cwd, ["remote", "get-url", "origin"], run),
    branch: (await git(cwd, ["rev-parse", "--abbrev-ref", "HEAD"], run)) ?? "unknown",
    headSha: headSha || (await git(cwd, ["rev-parse", "HEAD"], run)) || "unknown",
    headShortSha:
      (await git(cwd, ["rev-parse", "--short", "HEAD"], run)) ??
      headSha.slice(0, 7) ??
      "unknown",
    treeSha: treeSha || (await git(cwd, ["rev-parse", "HEAD^{tree}"], run)) || "unknown",
    describe: await git(cwd, ["describe", "--tags", "--always", "--dirty"], run),
    latestTag: await git(
      cwd,
      [
        "for-each-ref",
        "refs/tags",
        "--sort=-creatordate",
        "--format=%(refname:short)",
        "--count=1",
      ],
      run,
    ),
    authorName: authorName || "unknown",
    authorEmail: authorEmail || "unknown",
    authoredAt: authoredAt || "unknown",
    subject: subject || "unknown",
    dirty: status.dirty,
    dirtyFiles: status.dirtyFiles,
    statusCounts: status.statusCounts,
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `bun run --cwd scripts/security-report test -- src/git.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/security-report/src/git.ts scripts/security-report/src/git.test.ts
git commit -m "feat(security-report): collect git coordinates"
```

---

### Task 6: Project discovery, lockfile hashes and resolved versions, file walk

**Files:**
- Create: `scripts/security-report/src/project.ts`
- Test: `scripts/security-report/src/project.test.ts`

**Interfaces:**
- Produces:
  - `ProjectDiscovery`, `JsComponent`
  - `discoverProject(root, options)`
  - `parseBunLock(content)`, `parsePackageLock(content)`
  - `sha256(content)`, `walkSourceFiles(root, options)`, `isExcluded(relPath, options)`
  - `readPackageVersion(packageName, cwd)`
- Consumes: `ComponentInfo`, `LockfileInfo` from Task 1.

- [ ] **Step 1: Write the failing test**

`scripts/security-report/src/project.test.ts`:

```ts
import { describe, expect, test } from "bun:test";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  discoverProject,
  isExcluded,
  parseBunLock,
  parsePackageLock,
  sha256,
  walkSourceFiles,
} from "./project";

function tempDir(): string {
  return mkdtempSync(join(tmpdir(), "security-report-project-"));
}

describe("parseBunLock", () => {
  test("extracts resolved versions", () => {
    const versions = parseBunLock(
      JSON.stringify({
        packages: {
          react: ["react@19.3.1", "", {}, "sha512-x"],
          "@scope/pkg": ["@scope/pkg@2.0.0", "", {}, "sha512-y"],
        },
      }),
    );
    expect(versions.react).toBe("19.3.1");
    expect(versions["@scope/pkg"]).toBe("2.0.0");
  });
});

describe("parsePackageLock", () => {
  test("extracts versions from node_modules entries", () => {
    const versions = parsePackageLock(
      JSON.stringify({
        packages: {
          "": { name: "root" },
          "node_modules/react": { version: "19.3.1" },
        },
      }),
    );
    expect(versions.react).toBe("19.3.1");
  });
});

describe("sha256", () => {
  test("hashes content", () => {
    expect(sha256("abc")).toHaveLength(64);
  });
});

describe("isExcluded", () => {
  test("excludes dependencies, generated output, and tests by default", () => {
    const options = { includeTests: false, extraExcludes: [] };
    expect(isExcluded("packages/a/.venv/lib/x.py", options)).toBe(true);
    expect(isExcluded("apps/web/node_modules/x/a.js", options)).toBe(true);
    expect(isExcluded("packages/a/tests/test_a.py", options)).toBe(true);
    expect(isExcluded("apps/web/src/a.test.ts", options)).toBe(true);
    expect(isExcluded("apps/web/src/a.ts", options)).toBe(false);
  });

  test("includes tests when asked", () => {
    expect(
      isExcluded("packages/a/tests/test_a.py", {
        includeTests: true,
        extraExcludes: [],
      }),
    ).toBe(false);
  });
});

describe("walkSourceFiles", () => {
  test("walks JS/TS files and skips declarations", () => {
    const root = tempDir();
    try {
      mkdirSync(join(root, "src"));
      writeFileSync(join(root, "src", "a.ts"), "export const a = 1;");
      writeFileSync(join(root, "src", "a.test.ts"), "test");
      writeFileSync(join(root, "src", "types.d.ts"), "declare const x: number;");
      writeFileSync(join(root, "src", "b.js"), "console.log(1);");
      const files = walkSourceFiles(root, { includeTests: false, extraExcludes: [] });
      expect(files.map((file) => file.replace(root, "")).sort()).toEqual([
        "/src/a.ts",
        "/src/b.js",
      ]);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});

describe("discoverProject", () => {
  test("finds uv workspace members and JavaScript components", async () => {
    const root = tempDir();
    try {
      writeFileSync(
        join(root, "pyproject.toml"),
        `[project]\nname = "demo"\nversion = "1.0.0"\n[tool.uv.workspace]\nmembers = ["packages/*"]\n`,
      );
      mkdirSync(join(root, "packages", "lib"), { recursive: true });
      writeFileSync(
        join(root, "packages", "lib", "pyproject.toml"),
        `[project]\nname = "demo-lib"\nversion = "0.2.0"\n`,
      );
      writeFileSync(join(root, "uv.lock"), "version = 1");
      mkdirSync(join(root, "web", "src"), { recursive: true });
      writeFileSync(
        join(root, "web", "package.json"),
        JSON.stringify({ name: "demo-web", version: "3.0.0" }),
      );
      writeFileSync(
        join(root, "web", "bun.lock"),
        JSON.stringify({ packages: { react: ["react@19.0.0", "", {}, ""] } }),
      );
      writeFileSync(join(root, "web", "src", "a.ts"), "export const a = 1;");

      const project = await discoverProject(root, {
        includeTests: false,
        extraExcludes: [],
      });
      expect(project.components.some((component) => component.name === "demo-lib")).toBe(true);
      expect(project.components.some((component) => component.name === "demo-web")).toBe(true);
      expect(project.jsComponents[0]?.resolvedVersions.react).toBe("19.0.0");
      expect(project.lockfiles.some((lock) => lock.path.endsWith("uv.lock"))).toBe(true);
      expect(project.lockfiles.some((lock) => lock.path.endsWith("bun.lock"))).toBe(true);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `bun run --cwd scripts/security-report test -- src/project.test.ts`

Expected: FAIL with module-not-found for `./project`.

- [ ] **Step 3: Implement `project.ts`**

`scripts/security-report/src/project.ts`:

```ts
import { createHash } from "node:crypto";
import {
  existsSync,
  readFileSync,
  readdirSync,
} from "node:fs";
import { basename, dirname, extname, join, resolve } from "node:path";
import type { ComponentInfo, LockfileInfo } from "./model";

const BASE_EXCLUDES = new Set([
  ".venv",
  "venv",
  "node_modules",
  "dist",
  "build",
  "coverage",
  ".next",
  "out",
  ".git",
  "__pycache__",
  ".pytest_cache",
  ".ruff_cache",
  ".mypy_cache",
  "site-packages",
]);

const TEST_SEGMENTS = new Set(["tests", "fixtures"]);
const TEST_FILE = /\.(test|spec|stories)\.[^.]+$/;
const SOURCE_EXTENSIONS = new Set([
  ".js",
  ".jsx",
  ".mjs",
  ".cjs",
  ".ts",
  ".tsx",
  ".mts",
  ".cts",
]);

export interface DiscoveryOptions {
  includeTests: boolean;
  extraExcludes: string[];
}

export interface JsComponent {
  dir: string;
  sourceRoot: string;
  name: string;
  version: string | null;
  lockfile: string;
  lockfileKind: "bun" | "npm";
  resolvedVersions: Record<string, string>;
  packageCount: number;
}

export interface ProjectDiscovery {
  name: string;
  root: string;
  components: ComponentInfo[];
  lockfiles: LockfileInfo[];
  pythonRoots: string[];
  jsComponents: JsComponent[];
}

export function sha256(content: string | Buffer): string {
  return createHash("sha256").update(content).digest("hex");
}

export function isExcluded(relPath: string, options: DiscoveryOptions): boolean {
  const posix = relPath.split("\\").join("/");
  const segments = posix.split("/").filter(Boolean);
  const file = segments.at(-1) ?? "";

  if (segments.some((segment) => BASE_EXCLUDES.has(segment))) return true;
  if (!options.includeTests) {
    if (segments.some((segment) => TEST_SEGMENTS.has(segment))) return true;
    if (TEST_FILE.test(file)) return true;
  }
  for (const pattern of options.extraExcludes) {
    if (new Bun.Glob(pattern).match(posix)) return true;
  }
  return false;
}

export function walkSourceFiles(root: string, options: DiscoveryOptions): string[] {
  const files: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name);
      const rel = full.slice(root.length).replace(/^[\\/]/, "");
      if (isExcluded(rel, options)) continue;
      if (entry.isDirectory()) {
        walk(full);
        continue;
      }
      const extension = extname(entry.name);
      if (!SOURCE_EXTENSIONS.has(extension)) continue;
      if (entry.name.endsWith(".d.ts")) continue;
      files.push(full);
    }
  };
  if (existsSync(root)) walk(root);
  return files;
}

export function parseBunLock(content: string): Record<string, string> {
  const parsed = Bun.JSONC.parse(content) as {
    packages?: Record<string, unknown>;
  };
  const versions: Record<string, string> = {};
  for (const [name, value] of Object.entries(parsed.packages ?? {})) {
    if (!Array.isArray(value)) continue;
    const first = value[0];
    if (typeof first !== "string") continue;
    const at = first.lastIndexOf("@");
    if (at <= 0) continue;
    const version = first.slice(at + 1);
    if (version.includes(":") || version.includes("/")) continue;
    versions[name] = version;
  }
  return versions;
}

export function parsePackageLock(content: string): Record<string, string> {
  const parsed = JSON.parse(content) as {
    packages?: Record<string, { version?: string }>;
  };
  const versions: Record<string, string> = {};
  for (const [path, meta] of Object.entries(parsed.packages ?? {})) {
    if (!path.startsWith("node_modules/")) continue;
    if (typeof meta?.version !== "string") continue;
    versions[path.slice("node_modules/".length)] = meta.version;
  }
  return versions;
}

export function readPackageVersion(packageName: string, cwd: string): string | null {
  const path = resolve(cwd, "node_modules", packageName, "package.json");
  if (!existsSync(path)) return null;
  try {
    const parsed = JSON.parse(readFileSync(path, "utf8")) as { version?: string };
    return typeof parsed.version === "string" ? parsed.version : null;
  } catch {
    return null;
  }
}

function expandWorkspaceMembers(root: string, members: string[]): string[] {
  const dirs = new Set<string>();
  for (const member of members) {
    if (!member.includes("*")) {
      const dir = resolve(root, member);
      if (existsSync(join(dir, "pyproject.toml"))) dirs.add(dir);
      continue;
    }
    const glob = new Bun.Glob(`${member.replace(/\/$/, "")}/pyproject.toml`);
    for (const match of glob.scanSync({ cwd: root, onlyFiles: true })) {
      dirs.add(resolve(root, dirname(match)));
    }
  }
  return [...dirs].sort();
}

function pythonComponent(dir: string): ComponentInfo {
  let name = basename(dir);
  let version: string | null = null;
  const pyproject = join(dir, "pyproject.toml");
  if (existsSync(pyproject)) {
    try {
      const parsed = Bun.TOML.parse(readFileSync(pyproject, "utf8")) as {
        project?: { name?: string; version?: string };
      };
      if (typeof parsed.project?.name === "string") name = parsed.project.name;
      if (typeof parsed.project?.version === "string") version = parsed.project.version;
    } catch {
      // Keep defaults; discovery should not fail on an unreadable manifest.
    }
  }
  return { kind: "python", name, path: dir, version, lockfile: null };
}

function findPackageJsonDirs(root: string, options: DiscoveryOptions): string[] {
  const dirs: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      if (!entry.isDirectory()) continue;
      if (entry.name === "node_modules" || entry.name === ".git") continue;
      const full = join(dir, entry.name);
      const rel = full.slice(root.length).replace(/^[\\/]/, "");
      if (isExcluded(rel, options)) continue;
      if (existsSync(join(full, "package.json"))) dirs.push(full);
      walk(full);
    }
  };
  if (existsSync(join(root, "package.json"))) dirs.push(root);
  walk(root);
  return [...new Set(dirs)].sort();
}

function jsComponent(dir: string, options: DiscoveryOptions): JsComponent | null {
  let name = basename(dir);
  let version: string | null = null;
  try {
    const parsed = JSON.parse(readFileSync(join(dir, "package.json"), "utf8")) as {
      name?: string;
      version?: string;
    };
    if (typeof parsed.name === "string") name = parsed.name;
    if (typeof parsed.version === "string") version = parsed.version;
  } catch {
    // Keep defaults.
  }

  // The report tool can live inside the audited project (as it does in this
  // repository); never audit the auditor's own package.
  if (name === "agentbox-security-report") return null;

  const bunLock = join(dir, "bun.lock");
  const npmLock = join(dir, "package-lock.json");
  if (!existsSync(bunLock) && !existsSync(npmLock)) return null;

  const kind: "bun" | "npm" = existsSync(bunLock) ? "bun" : "npm";
  const lockfile = kind === "bun" ? bunLock : npmLock;
  const lockContent = readFileSync(lockfile, "utf8");
  const resolvedVersions =
    kind === "bun" ? parseBunLock(lockContent) : parsePackageLock(lockContent);

  return {
    dir,
    sourceRoot: existsSync(join(dir, "src")) ? join(dir, "src") : dir,
    name,
    version,
    lockfile,
    lockfileKind: kind,
    resolvedVersions,
    packageCount: Object.keys(resolvedVersions).length,
  };
}

export async function discoverProject(
  root: string,
  options: DiscoveryOptions,
): Promise<ProjectDiscovery> {
  const rootPyproject = join(root, "pyproject.toml");
  let rootName = basename(root);
  let members: string[] = [];

  if (existsSync(rootPyproject)) {
    try {
      const parsed = Bun.TOML.parse(readFileSync(rootPyproject, "utf8")) as {
        project?: { name?: string };
        tool?: { uv?: { workspace?: { members?: string[] } } };
      };
      if (typeof parsed.project?.name === "string") rootName = parsed.project.name;
      if (Array.isArray(parsed.tool?.uv?.workspace?.members)) {
        members = parsed.tool.uv.workspace.members.filter(
          (member): member is string => typeof member === "string",
        );
      }
    } catch {
      // Keep defaults.
    }
  }

  const pythonRoots = expandWorkspaceMembers(root, members);
  if (pythonRoots.length === 0 && existsSync(rootPyproject)) pythonRoots.push(root);

  const components: ComponentInfo[] = pythonRoots.map(pythonComponent);
  const lockfiles: LockfileInfo[] = [];
  const uvLock = join(root, "uv.lock");
  if (existsSync(uvLock)) {
    lockfiles.push({ path: uvLock, sha256: sha256(readFileSync(uvLock)) });
  }

  const jsComponents = findPackageJsonDirs(root, options)
    .map((dir) => jsComponent(dir, options))
    .filter((component): component is JsComponent => component !== null);

  for (const component of jsComponents) {
    components.push({
      kind: "javascript",
      name: component.name,
      path: component.dir,
      version: component.version,
      lockfile: component.lockfile,
    });
    lockfiles.push({
      path: component.lockfile,
      sha256: sha256(readFileSync(component.lockfile)),
      resolvedVersions: component.resolvedVersions,
    });
  }

  return { name: rootName, root, components, lockfiles, pythonRoots, jsComponents };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `bun run --cwd scripts/security-report test -- src/project.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/security-report/src/project.ts scripts/security-report/src/project.test.ts
git commit -m "feat(security-report): discover components and lockfiles"
```

---

### Task 7: Scanner types and PySentry SCA adapter

**Files:**
- Create: `scripts/security-report/src/scanners/types.ts`
- Create: `scripts/security-report/src/scanners/pysentry.ts`
- Test: `scripts/security-report/src/scanners/pysentry.test.ts`

**Interfaces:**
- Produces:
  - `ScanContext`, `ParsedScanner` from `types.ts`.
  - `PysentryJson`, `parsePysentry(json)`, `scanPysentry(ctx)` from `pysentry.ts`.
- Consumes: `Finding`, `MaintenanceIssue`, `ScannerResult` from Task 1; `normalizeSeverity` from Task 1; `makeFindingId` from Task 1; `safeUrl` from Task 2; `runProcess`, `tail` from Task 4; `JsComponent` from Task 6.

- [ ] **Step 1: Create `types.ts` (no test; compile-only)**

`scripts/security-report/src/scanners/types.ts`:

```ts
import type {
  Finding,
  MaintenanceIssue,
} from "../model";
import type { JsComponent } from "../project";

export interface ScanContext {
  root: string;
  pythonRoots: string[];
  jsComponents: JsComponent[];
  includeTests: boolean;
  extraExcludes: string[];
  timeoutMs: number;
  versions: Record<string, string>;
}

export interface ParsedScanner {
  findings: Finding[];
  stats: Record<string, number | string>;
  warnings: string[];
  errors: string[];
  partial: boolean;
  maintenance: MaintenanceIssue[];
}
```

- [ ] **Step 2: Write the failing PySentry test**

`scripts/security-report/src/scanners/pysentry.test.ts`:

```ts
import { describe, expect, test } from "bun:test";
import { parsePysentry } from "./pysentry";

const fixture = {
  scan_time: "2026-11-22T10:00:00Z",
  total_packages: 10,
  vulnerable_packages: 2,
  total_vulnerabilities: 3,
  vulnerabilities: [
    {
      package_name: "requests",
      installed_version: "2.0.0",
      is_direct: true,
      id: "GHSA-high",
      summary: "High issue",
      description: "Details",
      severity: "high",
      affected_versions: [{ constraint: ">=2.0.0,<2.1.0" }],
      fixed_versions: ["2.1.0"],
      references: ["https://example.com/advisory", "javascript:alert(1)"],
      aliases: [],
      cvss_score: 7.5,
    },
    {
      package_name: "flask",
      installed_version: "1.0.0",
      is_direct: false,
      id: "GHSA-low",
      summary: "Low issue",
      description: null,
      severity: "low",
      affected_versions: [],
      fixed_versions: [],
      references: [],
    },
    {
      package_name: "old",
      installed_version: "0.1.0",
      is_direct: true,
      id: "GHSA-suppressed",
      summary: "Suppressed issue",
      description: null,
      severity: "critical",
      affected_versions: [],
      fixed_versions: [],
      references: [],
      suppressed: "ignored_package",
    },
  ],
  fix_suggestions: [
    {
      package_name: "requests",
      current_version: "2.0.0",
      suggested_version: "2.1.0",
      vulnerability_id: "GHSA-high",
    },
  ],
  warnings: ["cache stale"],
  maintenance_issues: [
    {
      package_name: "old",
      installed_version: "0.1.0",
      issue_type: "deprecated",
      reason: "Use new-lib",
      is_direct: true,
      source_file: "uv.lock",
    },
  ],
  partial: true,
  failed_sources: ["osv"],
  failing: null,
};

describe("parsePysentry", () => {
  test("normalizes findings, fixes, maintenance, and partial state", () => {
    const parsed = parsePysentry(fixture);
    expect(parsed.findings).toHaveLength(3);
    expect(parsed.partial).toBe(true);
    expect(parsed.errors).toContain("Vulnerability source failed: osv");
    expect(parsed.stats.totalPackages).toBe(10);
    expect(parsed.stats.vulnerablePackages).toBe(2);

    const high = parsed.findings.find((finding) => finding.ruleId === "GHSA-high");
    expect(high?.severity).toBe("high");
    expect(high?.packageName).toBe("requests");
    expect(high?.installedVersion).toBe("2.0.0");
    expect(high?.vulnerableRange).toBe(">=2.0.0,<2.1.0");
    expect(high?.referenceUrl).toBe("https://example.com/advisory");
    expect(high?.fix).toBe("Upgrade to 2.1.0");
    expect(high?.id).toHaveLength(12);

    const suppressed = parsed.findings.find((finding) => finding.ruleId === "GHSA-suppressed");
    expect(suppressed?.suppressed).toBe("ignored_package");
    expect(parsed.maintenance[0]?.issueType).toBe("deprecated");
  });
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `bun run --cwd scripts/security-report test -- src/scanners/pysentry.test.ts`

Expected: FAIL with module-not-found for `./pysentry`.

- [ ] **Step 4: Implement `pysentry.ts`**

`scripts/security-report/src/scanners/pysentry.ts`:

```ts
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  makeFindingId,
  type Finding,
  type MaintenanceIssue,
  type ScannerResult,
} from "../model";
import { safeUrl } from "../render/components";
import { normalizeSeverity } from "../severity";
import { runProcess, tail } from "./process";
import type { ParsedScanner, ScanContext } from "./types";

interface PysentryVulnerability {
  package_name: string;
  installed_version: string;
  is_direct?: boolean;
  id: string;
  summary: string;
  description?: string | null;
  severity: string;
  affected_versions?: Array<{ constraint?: string } | string>;
  fixed_versions?: Array<string | { version?: string }>;
  references?: string[];
  suppressed?: string | null;
}

interface PysentryFix {
  package_name: string;
  current_version: string;
  suggested_version: string;
  vulnerability_id: string;
}

interface PysentryMaintenance {
  package_name: string;
  installed_version: string;
  issue_type: string;
  reason?: string | null;
  is_direct?: boolean;
}

export interface PysentryJson {
  scan_time?: string;
  total_packages?: number;
  vulnerable_packages?: number;
  total_vulnerabilities?: number;
  vulnerabilities?: PysentryVulnerability[];
  fix_suggestions?: PysentryFix[];
  warnings?: string[];
  maintenance_issues?: PysentryMaintenance[];
  partial?: boolean;
  failed_sources?: string[];
}

function fixedVersions(value: PysentryVulnerability["fixed_versions"]): string[] {
  return (value ?? [])
    .map((item) => (typeof item === "string" ? item : item?.version))
    .filter((item): item is string => typeof item === "string" && item.length > 0);
}

function ranges(value: PysentryVulnerability["affected_versions"]): string {
  return (value ?? [])
    .map((item) => (typeof item === "string" ? item : item?.constraint))
    .filter((item): item is string => typeof item === "string" && item.length > 0)
    .join(", ");
}

export function parsePysentry(json: PysentryJson): ParsedScanner {
  const fixes = new Map<string, string>();
  for (const fix of json.fix_suggestions ?? []) {
    fixes.set(`${fix.package_name}|${fix.vulnerability_id}`, fix.suggested_version);
  }

  const findings: Finding[] = (json.vulnerabilities ?? []).map((vulnerability) => {
    const severity = normalizeSeverity(vulnerability.severity);
    const reference = (vulnerability.references ?? [])
      .map((url) => safeUrl(url))
      .find((url): url is string => url !== null) ?? null;
    const suggested = fixes.get(
      `${vulnerability.package_name}|${vulnerability.id}`,
    );
    const fixed = fixedVersions(vulnerability.fixed_versions);
    const fix = suggested
      ? `Upgrade to ${suggested}`
      : fixed.length > 0
        ? `Upgrade to ${fixed.join(" or ")}`
        : null;

    return {
      id: makeFindingId({
        tool: "PySentry",
        ruleId: vulnerability.id,
        title: vulnerability.summary,
        packageName: vulnerability.package_name,
        line: 0,
      }),
      section: "sca",
      ecosystem: "python",
      tool: "PySentry",
      severity,
      sourceSeverity: vulnerability.severity,
      ruleId: vulnerability.id,
      title: vulnerability.summary,
      detail: vulnerability.description ?? null,
      packageName: vulnerability.package_name,
      installedVersion: vulnerability.installed_version,
      vulnerableRange: ranges(vulnerability.affected_versions) || undefined,
      referenceUrl: reference,
      fix,
      suppressed: vulnerability.suppressed ?? null,
    };
  });

  const maintenance: MaintenanceIssue[] = (json.maintenance_issues ?? []).map(
    (issue) => ({
      packageName: issue.package_name,
      installedVersion: issue.installed_version,
      issueType: issue.issue_type,
      reason: issue.reason ?? null,
      isDirect: issue.is_direct ?? false,
    }),
  );

  const failedSources = json.failed_sources ?? [];
  return {
    findings,
    stats: {
      totalPackages: json.total_packages ?? 0,
      vulnerablePackages: json.vulnerable_packages ?? 0,
      totalVulnerabilities: json.total_vulnerabilities ?? findings.length,
      fixable: fixes.size,
      maintenanceIssues: maintenance.length,
    },
    warnings: json.warnings ?? [],
    errors: failedSources.map((source) => `Vulnerability source failed: ${source}`),
    partial: Boolean(json.partial) || failedSources.length > 0,
    maintenance,
  };
}

export async function scanPysentry(ctx: ScanContext): Promise<ScannerResult> {
  const dir = mkdtempSync(join(tmpdir(), "pysentry-report-"));
  const output = join(dir, "report.json");
  const command = ["uvx", "pysentry-rs", ctx.root, "--format", "json", "--output", output];

  let parsed: ParsedScanner | null = null;
  const errors: string[] = [];
  try {
    const result = await runProcess("uvx", command.slice(1), {
      cwd: ctx.root,
      timeoutMs: ctx.timeoutMs,
    });

    try {
      parsed = parsePysentry(JSON.parse(readFileSync(output, "utf8")) as PysentryJson);
    } catch (error) {
      errors.push(
        `Invalid PySentry JSON: ${error instanceof Error ? error.message : String(error)}`,
      );
      if (result.stderr.trim()) errors.push(tail(result.stderr));
    }

    const accepted =
      result.exitCode === 0 ||
      ((result.exitCode === 1 || result.exitCode === 2) && parsed !== null);
    const status = !accepted || parsed === null
      ? "failed"
      : result.exitCode === 2 || parsed.partial
        ? "partial"
        : "ok";

    return {
      tool: "PySentry",
      version: ctx.versions.pysentry ?? "unknown",
      command,
      status,
      exitCode: result.exitCode,
      durationMs: result.durationMs,
      stats: parsed?.stats ?? {},
      warnings: parsed?.warnings ?? [],
      errors: [...errors, ...(parsed?.errors ?? [])],
      findings: parsed?.findings ?? [],
      maintenance: parsed?.maintenance ?? [],
    };
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `bun run --cwd scripts/security-report test -- src/scanners/pysentry.test.ts`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/security-report/src/scanners/types.ts scripts/security-report/src/scanners/pysentry.ts scripts/security-report/src/scanners/pysentry.test.ts
git commit -m "feat(security-report): add PySentry SCA adapter"
```

---

### Task 8: Bandit SAST adapter

**Files:**
- Create: `scripts/security-report/src/scanners/bandit.ts`
- Test: `scripts/security-report/src/scanners/bandit.test.ts`

**Interfaces:**
- Produces: `BanditJson`, `parseBandit(json, root)`, `banditArgs(ctx)`, `scanBandit(ctx)`.
- Consumes: `ScanContext`, `ParsedScanner`; `Finding`, `ScannerResult`; `normalizeSeverity`; `makeFindingId`; `displayPath`, `safeUrl`; `runProcess`, `tail`.

- [ ] **Step 1: Write the failing test**

`scripts/security-report/src/scanners/bandit.test.ts`:

```ts
import { describe, expect, test } from "bun:test";
import { banditArgs, parseBandit } from "./bandit";
import type { ScanContext } from "./types";

const json = {
  results: [
    {
      filename: "/repo/packages/a/src/a.py",
      line_number: 4,
      col_offset: 0,
      issue_severity: "HIGH",
      issue_confidence: "MEDIUM",
      issue_text: "Use of eval",
      test_id: "B307",
      test_name: "blacklist",
      more_info: "https://bandit.readthedocs.io/b307",
    },
    {
      filename: "/repo/packages/a/src/b.py",
      line_number: 9,
      issue_severity: "LOW",
      issue_confidence: "HIGH",
      issue_text: "Assert used",
      test_id: "B101",
      test_name: "assert_used",
      more_info: "",
    },
  ],
  metrics: { _totals: { loc: 120, nosec: 0, skipped_tests: 0 } },
  errors: [],
};

function context(includeTests: boolean): ScanContext {
  return {
    root: "/repo",
    pythonRoots: ["/repo/packages/a"],
    jsComponents: [],
    includeTests,
    extraExcludes: [],
    timeoutMs: 1000,
    versions: {},
  };
}

describe("parseBandit", () => {
  test("normalizes findings and stats", () => {
    const parsed = parseBandit(json, "/repo");
    expect(parsed.findings).toHaveLength(2);
    expect(parsed.findings[0]?.severity).toBe("high");
    expect(parsed.findings[0]?.confidence).toBe("MEDIUM");
    expect(parsed.findings[0]?.file).toBe("packages/a/src/a.py");
    expect(parsed.findings[0]?.referenceUrl).toBe("https://bandit.readthedocs.io/b307");
    expect(parsed.findings[1]?.severity).toBe("low");
    expect(parsed.stats.filesWithFindings).toBe(2);
    expect(parsed.stats.loc).toBe(120);
  });
});

describe("banditArgs", () => {
  test("excludes tests by default", () => {
    const args = banditArgs(context(false)).join(" ");
    expect(args).toContain("run bandit -r");
    expect(args).toContain("*/tests/*");
    expect(args).toContain("-f json");
  });

  test("includes tests when asked", () => {
    const args = banditArgs(context(true)).join(" ");
    expect(args).not.toContain("*/tests/*");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `bun run --cwd scripts/security-report test -- src/scanners/bandit.test.ts`

Expected: FAIL with module-not-found for `./bandit`.

- [ ] **Step 3: Implement `bandit.ts`**

`scripts/security-report/src/scanners/bandit.ts`:

```ts
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `bun run --cwd scripts/security-report test -- src/scanners/bandit.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/security-report/src/scanners/bandit.ts scripts/security-report/src/scanners/bandit.test.ts
git commit -m "feat(security-report): add Bandit SAST adapter"
```

---

### Task 9: Bun/NPM audit SCA adapters with installed-version enrichment

**Files:**
- Create: `scripts/security-report/src/scanners/bun-audit.ts`
- Test: `scripts/security-report/src/scanners/bun-audit.test.ts`

**Interfaces:**
- Produces: `parseBunAudit(json, versions)`, `parseNpmAudit(json, versions)`, `scanJsSca(ctx)`.
- Consumes: `ScanContext`, `ParsedScanner`; `Finding`, `ScannerResult`; `normalizeSeverity`; `makeFindingId`; `safeUrl`; `runProcess`, `tail`.

- [ ] **Step 1: Write the failing test**

`scripts/security-report/src/scanners/bun-audit.test.ts`:

```ts
import { describe, expect, test } from "bun:test";
import { parseBunAudit, parseNpmAudit } from "./bun-audit";

const bunJson = {
  zod: [
    {
      id: 1243066,
      url: "https://github.com/advisories/GHSA-mrhx-c7xc-m3w5",
      title: "Zod memory exhaustion",
      severity: "high",
      vulnerable_versions: "<4.6.6",
      cwe: ["CWE-770"],
      cvss: { score: 7.5, vectorString: "CVSS:3.1/..." },
    },
  ],
};

const npmJson = {
  vulnerabilities: {
    react: {
      name: "react",
      severity: "moderate",
      isDirect: true,
      via: [
        {
          source: 123,
          name: "react",
          title: "React issue",
          url: "https://example.com/react",
          severity: "moderate",
          range: "<19.0.0",
          cvss: { vectorString: "CVSS:3.1/..." },
        },
      ],
      range: "<19.0.0",
      nodes: ["node_modules/react"],
      fixAvailable: { name: "react", version: "19.0.0", isSemVerMajor: false },
    },
  },
};

describe("parseBunAudit", () => {
  test("normalizes advisories and installed versions", () => {
    const parsed = parseBunAudit(bunJson, { zod: "4.0.0" });
    expect(parsed.findings).toHaveLength(1);
    expect(parsed.findings[0]?.severity).toBe("high");
    expect(parsed.findings[0]?.packageName).toBe("zod");
    expect(parsed.findings[0]?.installedVersion).toBe("4.0.0");
    expect(parsed.findings[0]?.vulnerableRange).toBe("<4.6.6");
    expect(parsed.stats.affectedPackages).toBe(1);
  });
});

describe("parseNpmAudit", () => {
  test("normalizes advisories and fixes", () => {
    const parsed = parseNpmAudit(npmJson, { react: "18.0.0" });
    expect(parsed.findings).toHaveLength(1);
    expect(parsed.findings[0]?.severity).toBe("medium");
    expect(parsed.findings[0]?.installedVersion).toBe("18.0.0");
    expect(parsed.findings[0]?.fix).toBe("Upgrade react to 19.0.0");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `bun run --cwd scripts/security-report test -- src/scanners/bun-audit.test.ts`

Expected: FAIL with module-not-found for `./bun-audit`.

- [ ] **Step 3: Implement `bun-audit.ts`**

`scripts/security-report/src/scanners/bun-audit.ts`:

```ts
import { makeFindingId, type Finding, type ScannerResult } from "../model";
import { safeUrl } from "../render/components";
import { normalizeSeverity } from "../severity";
import { runProcess, tail } from "./process";
import type { ParsedScanner, ScanContext } from "./types";

export interface BunAdvisory {
  id: number | string;
  url?: string;
  title?: string;
  severity?: string;
  vulnerable_versions?: string;
  cwe?: string[];
  cvss?: { score?: number; vectorString?: string | null };
}

interface NpmAdvisory {
  source?: number | string;
  title?: string;
  url?: string;
  severity?: string;
  range?: string;
  cvss?: { vectorString?: string | null };
}

interface NpmVulnerability {
  name?: string;
  severity?: string;
  range?: string;
  via?: Array<string | NpmAdvisory>;
  fixAvailable?: boolean | { name?: string; version?: string };
}

export function parseBunAudit(
  json: Record<string, BunAdvisory[]>,
  versions: Record<string, string>,
): ParsedScanner {
  const findings: Finding[] = [];
  for (const [packageName, advisories] of Object.entries(json)) {
    for (const advisory of advisories ?? []) {
      const title = advisory.title ?? `Vulnerability in ${packageName}`;
      const ruleId = String(advisory.id);
      findings.push({
        id: makeFindingId({ tool: "Bun audit", ruleId, title, packageName }),
        section: "sca",
        ecosystem: "javascript",
        tool: "Bun audit",
        severity: normalizeSeverity(advisory.severity),
        sourceSeverity: advisory.severity ?? "unknown",
        ruleId,
        title,
        detail: advisory.cwe?.length ? advisory.cwe.join(", ") : null,
        packageName,
        installedVersion: versions[packageName],
        vulnerableRange: advisory.vulnerable_versions,
        referenceUrl: safeUrl(advisory.url),
      });
    }
  }

  return {
    findings,
    stats: {
      affectedPackages: Object.keys(json).length,
      advisories: findings.length,
    },
    warnings: [],
    errors: [],
    partial: false,
    maintenance: [],
  };
}

export function parseNpmAudit(
  json: { vulnerabilities?: Record<string, NpmVulnerability> },
  versions: Record<string, string>,
): ParsedScanner {
  const findings: Finding[] = [];
  for (const [packageName, vulnerability] of Object.entries(json.vulnerabilities ?? {})) {
    const advisories = (vulnerability.via ?? []).filter(
      (item): item is NpmAdvisory => typeof item === "object" && item !== null,
    );

    const fix =
      vulnerability.fixAvailable === true
        ? "Run npm audit fix"
        : typeof vulnerability.fixAvailable === "object" &&
            vulnerability.fixAvailable?.version
          ? `Upgrade ${vulnerability.fixAvailable.name ?? packageName} to ${vulnerability.fixAvailable.version}`
          : null;

    if (advisories.length === 0) {
      const title = `Vulnerable dependency: ${packageName}`;
      findings.push({
        id: makeFindingId({ tool: "NPM audit", ruleId: null, title, packageName }),
        section: "sca",
        ecosystem: "javascript",
        tool: "NPM audit",
        severity: normalizeSeverity(vulnerability.severity),
        sourceSeverity: vulnerability.severity ?? "unknown",
        ruleId: null,
        title,
        detail: null,
        packageName,
        installedVersion: versions[packageName],
        vulnerableRange: vulnerability.range,
        fix,
      });
      continue;
    }

    for (const advisory of advisories) {
      const title = advisory.title ?? `Vulnerability in ${packageName}`;
      const ruleId = advisory.source != null ? String(advisory.source) : null;
      findings.push({
        id: makeFindingId({ tool: "NPM audit", ruleId, title, packageName }),
        section: "sca",
        ecosystem: "javascript",
        tool: "NPM audit",
        severity: normalizeSeverity(advisory.severity ?? vulnerability.severity),
        sourceSeverity: advisory.severity ?? vulnerability.severity ?? "unknown",
        ruleId,
        title,
        detail: advisory.cvss?.vectorString ?? null,
        packageName,
        installedVersion: versions[packageName],
        vulnerableRange: advisory.range ?? vulnerability.range,
        referenceUrl: safeUrl(advisory.url),
        fix,
      });
    }
  }

  return {
    findings,
    stats: {
      affectedPackages: Object.keys(json.vulnerabilities ?? {}).length,
      advisories: findings.length,
    },
    warnings: [],
    errors: [],
    partial: false,
    maintenance: [],
  };
}

export async function scanJsSca(ctx: ScanContext): Promise<ScannerResult[]> {
  const results: ScannerResult[] = [];

  for (const component of ctx.jsComponents) {
    const isBun = component.lockfileKind === "bun";
    const command = isBun ? "bun" : "npm";
    const args = ["audit", "--json"];
    const result = await runProcess(command, args, {
      cwd: component.dir,
      timeoutMs: ctx.timeoutMs,
    });

    let parsed: ParsedScanner | null = null;
    const errors: string[] = [];
    try {
      const json = JSON.parse(result.stdout) as unknown;
      parsed = isBun
        ? parseBunAudit(json as Record<string, BunAdvisory[]>, component.resolvedVersions)
        : parseNpmAudit(
            json as { vulnerabilities?: Record<string, NpmVulnerability> },
            component.resolvedVersions,
          );
    } catch (error) {
      errors.push(
        `Invalid ${isBun ? "Bun" : "NPM"} audit JSON: ${error instanceof Error ? error.message : String(error)}`,
      );
      if (result.stderr.trim()) errors.push(tail(result.stderr));
    }

    const accepted = result.exitCode === 0 || (result.exitCode === 1 && parsed !== null);
    const status = !accepted || parsed === null ? "failed" : "ok";
    const tool = isBun ? "Bun audit" : "NPM audit";

    results.push({
      tool,
      version: ctx.versions[isBun ? "bun" : "npm"] ?? "unknown",
      command: [command, ...args],
      status,
      exitCode: result.exitCode,
      durationMs: result.durationMs,
      stats: { ...(parsed?.stats ?? {}), packages: component.packageCount },
      warnings: parsed?.warnings ?? [],
      errors: [...errors, ...(parsed?.errors ?? [])],
      findings: parsed?.findings ?? [],
      maintenance: [],
    });
  }

  return results;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `bun run --cwd scripts/security-report test -- src/scanners/bun-audit.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/security-report/src/scanners/bun-audit.ts scripts/security-report/src/scanners/bun-audit.test.ts
git commit -m "feat(security-report): add Bun and NPM audit adapters"
```

---

### Task 10: JS-X-Ray SAST adapter

**Files:**
- Create: `scripts/security-report/src/scanners/jsxray.ts`
- Test: `scripts/security-report/src/scanners/jsxray.test.ts`

**Interfaces:**
- Produces: `JsxrayWarning`, `locationStart(location)`, `parseJsxrayWarnings(warnings, file, root, describe)`, `scanJsxray(ctx)`.
- Consumes: `ScanContext`, `ParsedScanner`; `Finding`, `ScannerResult`; `normalizeSeverity`; `makeFindingId`; `displayPath`; `walkSourceFiles`, `JsComponent` from Task 6.

- [ ] **Step 1: Write the failing test**

`scripts/security-report/src/scanners/jsxray.test.ts`:

```ts
import { describe, expect, test } from "bun:test";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { locationStart, parseJsxrayWarnings, scanJsxray } from "./jsxray";
import type { ScanContext } from "./types";

describe("locationStart", () => {
  test("handles both observed shapes", () => {
    expect(locationStart([[[5, 27], [5, 37]]])).toEqual({ line: 5, column: 27 });
    expect(locationStart([[3, 28], [3, 29]])).toEqual({ line: 3, column: 28 });
    expect(locationStart(undefined)).toEqual({});
  });
});

describe("parseJsxrayWarnings", () => {
  test("normalizes warnings", () => {
    const findings = parseJsxrayWarnings(
      [
        {
          kind: "unsafe-stmt",
          severity: "Warning",
          value: "eval",
          location: [[[6, 2], [6, 12]]],
          i18n: "sast_warnings.unsafe_stmt",
        },
        {
          kind: "encoded-literal",
          severity: "Information",
          value: "6576616c",
          location: [[[5, 27], [5, 37]]],
          i18n: "sast_warnings.encoded_literal",
        },
      ],
      "/repo/apps/web/src/a.ts",
      "/repo",
      () => "Usage of eval",
    );
    expect(findings).toHaveLength(2);
    expect(findings[0]?.severity).toBe("medium");
    expect(findings[0]?.file).toBe("apps/web/src/a.ts");
    expect(findings[0]?.line).toBe(6);
    expect(findings[0]?.title).toBe("Usage of eval");
    expect(findings[1]?.severity).toBe("info");
  });
});

describe("scanJsxray", () => {
  test("scans TSX with the TypeScript parser", async () => {
    const root = mkdtempSync(join(tmpdir(), "security-report-jsxray-"));
    try {
      writeFileSync(
        join(root, "sample.tsx"),
        `export function Widget({ value }: { value: string }) {\n  const run = () => eval(value);\n  return <button onClick={() => run()}>{value}</button>;\n}\n`,
      );
      const ctx: ScanContext = {
        root,
        pythonRoots: [],
        jsComponents: [
          {
            dir: root,
            sourceRoot: root,
            name: "fixture",
            version: "1.0.0",
            lockfile: join(root, "bun.lock"),
            lockfileKind: "bun",
            resolvedVersions: {},
            packageCount: 0,
          },
        ],
        includeTests: false,
        extraExcludes: [],
        timeoutMs: 10_000,
        versions: { jsxray: "16.2.0" },
      };

      const result = await scanJsxray(ctx);
      expect(result.status).toBe("ok");
      expect(result.findings.some((finding) => finding.ruleId === "unsafe-stmt")).toBe(true);
      expect(result.stats.filesScanned).toBe(1);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `bun run --cwd scripts/security-report test -- src/scanners/jsxray.test.ts`

Expected: FAIL with module-not-found for `./jsxray`.

- [ ] **Step 3: Implement `jsxray.ts`**

`scripts/security-report/src/scanners/jsxray.ts`:

```ts
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `bun run --cwd scripts/security-report test -- src/scanners/jsxray.test.ts`

Expected: PASS. The TSX smoke test must produce an `unsafe-stmt` finding.

- [ ] **Step 5: Commit**

```bash
git add scripts/security-report/src/scanners/jsxray.ts scripts/security-report/src/scanners/jsxray.test.ts
git commit -m "feat(security-report): add JS-X-Ray SAST adapter"
```

---

### Task 11: Report model assembly and exit-code gating

**Files:**
- Create: `scripts/security-report/src/report.ts`
- Create: `scripts/security-report/src/test-helpers.ts`
- Test: `scripts/security-report/src/report.test.ts`

**Interfaces:**
- Produces:
  - `DEFAULT_LIMITATIONS`
  - `buildReportModel(input)`
  - `determineExitCode(model, options, pdfFailed)`
  - `test-helpers.ts`: `makeGit()`, `makeScanner()`, `makeModel()`.
- Consumes: types from Task 1; `countSeverities`, `countAtOrAbove`, `sortFindings` from Task 1.

- [ ] **Step 1: Write the failing test**

`scripts/security-report/src/report.test.ts`:

```ts
import { describe, expect, test } from "bun:test";
import { buildReportModel, determineExitCode } from "./report";
import type { Finding, ScannerResult } from "./model";
import { makeGit, makeScanner } from "./test-helpers";

function finding(partial: Partial<Finding>): Finding {
  return {
    id: "id",
    section: "sast",
    ecosystem: "python",
    tool: "Bandit",
    severity: "low",
    sourceSeverity: "LOW",
    ruleId: "B101",
    title: "title",
    detail: null,
    ...partial,
  };
}

function build(tools: ScannerResult[]) {
  return buildReportModel({
    reportId: "agentbox-security-abc",
    classification: "Internal",
    generatedAt: new Date("2026-11-22T12:00:00Z"),
    scanStartedAt: new Date("2026-11-22T11:59:00Z"),
    scanFinishedAt: new Date("2026-11-22T12:00:00Z"),
    projectName: "demo",
    root: "/repo",
    git: makeGit(),
    components: [],
    lockfiles: [],
    tools,
  });
}

describe("buildReportModel", () => {
  test("groups findings and excludes suppressed findings from counts", () => {
    const model = build([
      makeScanner({
        findings: [
          finding({ section: "sca", severity: "critical", tool: "PySentry" }),
          finding({ section: "sast", severity: "high" }),
          finding({ section: "sast", severity: "high", suppressed: "ignored_package" }),
        ],
      }),
    ]);
    expect(model.sections.sca.findings).toHaveLength(1);
    expect(model.sections.sast.findings).toHaveLength(2);
    expect(model.sections.sast.severityCounts.high).toBe(1);
    expect(model.schemaVersion).toBe(1);
    expect(model.limitations.length).toBeGreaterThan(0);
  });
});

describe("determineExitCode", () => {
  test("returns 0 when clean", () => {
    const model = build([makeScanner()]);
    expect(determineExitCode(model, { allowPartial: false, failOn: "none" }, false)).toBe(0);
  });

  test("returns 3 when the gate is met", () => {
    const model = build([
      makeScanner({ findings: [finding({ severity: "critical", section: "sca" })] }),
    ]);
    expect(determineExitCode(model, { allowPartial: false, failOn: "high" }, false)).toBe(3);
  });

  test("returns 1 for partial scans unless allowed", () => {
    const model = build([makeScanner({ status: "partial" })]);
    expect(determineExitCode(model, { allowPartial: false, failOn: "none" }, false)).toBe(1);
    expect(determineExitCode(model, { allowPartial: true, failOn: "none" }, false)).toBe(0);
  });

  test("returns 1 when every scanner failed, even when partials are allowed", () => {
    const model = build([
      makeScanner({ status: "failed" }),
      makeScanner({ status: "failed" }),
    ]);
    expect(determineExitCode(model, { allowPartial: true, failOn: "none" }, false)).toBe(1);
  });

  test("returns 1 when PDF failed", () => {
    const model = build([makeScanner()]);
    expect(determineExitCode(model, { allowPartial: true, failOn: "none" }, true)).toBe(1);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `bun run --cwd scripts/security-report test -- src/report.test.ts`

Expected: FAIL with module-not-found for `./report`.

- [ ] **Step 3: Implement `test-helpers.ts`**

`scripts/security-report/src/test-helpers.ts`:

```ts
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
```

- [ ] **Step 4: Implement `report.ts`**

`scripts/security-report/src/report.ts`:

```ts
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
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `bun run --cwd scripts/security-report test -- src/report.test.ts`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/security-report/src/report.ts scripts/security-report/src/test-helpers.ts scripts/security-report/src/report.test.ts
git commit -m "feat(security-report): assemble report model and exit gating"
```

---

### Task 12: Fonts, print CSS, document shell, cover, and coordinates

**Files:**
- Create: `scripts/security-report/assets/fonts/` (four woff2 files + licenses)
- Create: `scripts/security-report/src/render/fonts.ts`
- Create: `scripts/security-report/src/render/styles.ts`
- Create: `scripts/security-report/src/render/html.ts`
- Test: `scripts/security-report/src/render/fonts.test.ts`
- Test: `scripts/security-report/src/render/html.test.ts`

**Interfaces:**
- Produces: `buildFontCss(fontsDir)`, `STYLES` (CSS string), `renderReport(model, options)`, `renderCover(model)`, `renderCoordinates(model)`.
- Consumes: `ReportModel`; `escapeHtml`, `displayPath`, `safeUrl`; `renderDonut`, `renderSeverityLegend`.

- [ ] **Step 1: Copy the font assets and licenses**

Run (PowerShell, from repo root):

```powershell
New-Item -ItemType Directory -Force scripts/security-report/assets/fonts | Out-Null
Copy-Item apps/web/node_modules/@fontsource/silkscreen/files/silkscreen-latin-400-normal.woff2 scripts/security-report/assets/fonts/Silkscreen-Regular.woff2
Copy-Item apps/web/node_modules/@fontsource/inter/files/inter-latin-400-normal.woff2 scripts/security-report/assets/fonts/Inter-Regular.woff2
Copy-Item apps/web/node_modules/@fontsource/inter/files/inter-latin-600-normal.woff2 scripts/security-report/assets/fonts/Inter-SemiBold.woff2
Copy-Item apps/web/node_modules/@fontsource/jetbrains-mono/files/jetbrains-mono-latin-400-normal.woff2 scripts/security-report/assets/fonts/JetBrainsMono-Regular.woff2
New-Item -ItemType Directory -Force scripts/security-report/assets/fonts/licenses | Out-Null
Copy-Item apps/web/node_modules/@fontsource/silkscreen/LICENSE scripts/security-report/assets/fonts/licenses/Silkscreen-OFL.txt
Copy-Item apps/web/node_modules/@fontsource/inter/LICENSE scripts/security-report/assets/fonts/licenses/Inter-OFL.txt
Copy-Item apps/web/node_modules/@fontsource/jetbrains-mono/LICENSE scripts/security-report/assets/fonts/licenses/JetBrainsMono-OFL.txt
```

Expected: four `.woff2` files and three license files.

- [ ] **Step 2: Write the failing fonts test**

`scripts/security-report/src/render/fonts.test.ts`:

```ts
import { describe, expect, test } from "bun:test";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { buildFontCss } from "./fonts";

describe("buildFontCss", () => {
  test("embeds all four fonts as base64", () => {
    const dir = mkdtempSync(join(tmpdir(), "security-report-fonts-"));
    try {
      for (const name of [
        "Silkscreen-Regular.woff2",
        "Inter-Regular.woff2",
        "Inter-SemiBold.woff2",
        "JetBrainsMono-Regular.woff2",
      ]) {
        writeFileSync(join(dir, name), "fake-font-bytes");
      }
      const css = buildFontCss(dir);
      expect(css.match(/@font-face/g)).toHaveLength(4);
      expect(css).toContain("data:font/woff2;base64,");
      expect(css).toContain("Silkscreen");
      expect(css).toContain("JetBrains Mono");
      expect(css).toContain("Inter");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
```

- [ ] **Step 3: Run the fonts test to verify it fails**

Run: `bun run --cwd scripts/security-report test -- src/render/fonts.test.ts`

Expected: FAIL with module-not-found for `./fonts`.

- [ ] **Step 4: Implement `fonts.ts`**

`scripts/security-report/src/render/fonts.ts`:

```ts
import { readFileSync } from "node:fs";
import { join } from "node:path";

interface FontFace {
  file: string;
  family: string;
  weight: string;
}

const FACES: FontFace[] = [
  { file: "Silkscreen-Regular.woff2", family: "Silkscreen", weight: "400" },
  { file: "Inter-Regular.woff2", family: "Inter", weight: "400" },
  { file: "Inter-SemiBold.woff2", family: "Inter", weight: "600" },
  { file: "JetBrainsMono-Regular.woff2", family: "JetBrains Mono", weight: "400" },
];

export function buildFontCss(fontsDir: string): string {
  return FACES.map((face) => {
    const base64 = readFileSync(join(fontsDir, face.file)).toString("base64");
    return `@font-face{font-family:"${face.family}";font-style:normal;font-weight:${face.weight};font-display:block;src:url(data:font/woff2;base64,${base64}) format("woff2");}`;
  }).join("\n");
}
```

- [ ] **Step 5: Run the fonts test to verify it passes**

Run: `bun run --cwd scripts/security-report test -- src/render/fonts.test.ts`

Expected: PASS.

- [ ] **Step 6: Write the failing HTML shell test**

`scripts/security-report/src/render/html.test.ts`:

```ts
import { describe, expect, test } from "bun:test";
import { makeModel } from "../test-helpers";
import { renderReport } from "./html";

describe("renderReport", () => {
  test("renders a self-contained document with cover and coordinates", () => {
    const model = makeModel();
    const html = renderReport(model, { fontCss: "@font-face{}" });

    expect(html.startsWith("<!doctype html>")).toBe(true);
    expect(html).toContain('<html lang="en">');
    expect(html).toContain("[AGENTBOX]");
    expect(html).toContain(model.reportId);
    expect(html).toContain("Security Audit Report");
    expect(html).toContain('class="cover"');
    expect(html).toContain("aaaaaaa");
    expect(html).toContain("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");
    expect(html).toContain("git@example.com:org/repo.git");
    expect(html).toContain("@font-face{}");
    expect(html).not.toContain("<script>");
  });

  test("escapes project and classification text", () => {
    const model = makeModel();
    model.project.name = "<script>alert(1)</script>";
    model.classification = "<b>x</b>";
    const html = renderReport(model, { fontCss: "" });
    expect(html).not.toContain("<script>alert(1)</script>");
    expect(html).toContain("&lt;script&gt;alert(1)&lt;/script&gt;");
    expect(html).toContain("&lt;b&gt;x&lt;/b&gt;");
  });
});
```

- [ ] **Step 7: Run the HTML test to verify it fails**

Run: `bun run --cwd scripts/security-report test -- src/render/html.test.ts`

Expected: FAIL with module-not-found for `./html`.

- [ ] **Step 8: Implement `styles.ts`**

`scripts/security-report/src/render/styles.ts`:

```ts
export const STYLES = `
:root{
  --ink:#121812;--muted:#5a6658;--canvas:#f3f6f0;--surface:#ffffff;--raised:#e9eee5;
  --border:#c8d2c4;--phosphor:#087a43;--grid:rgba(8,122,67,.07);
  --crit:#b42318;--high:#a31c8c;--med:#9a5a00;--low:#007a99;--info:#5a6658;--unknown:#8e9c8e;
}
*{box-sizing:border-box}
@page{size:A4;margin:16mm}
html{background:#fff}
body{margin:0;background:var(--canvas);color:var(--ink);font:14px/1.55 "Inter",system-ui,sans-serif;-webkit-print-color-adjust:exact;print-color-adjust:exact}
h1,h2,h3{font-family:"Silkscreen",monospace;font-weight:400;letter-spacing:.02em;margin:0}
h1{font-size:30px;line-height:1.2}
h2{font-size:20px;margin-bottom:8px}
h3{font-size:15px;margin-bottom:6px}
p{margin:0 0 10px}
a{color:var(--phosphor);text-decoration:none}
.mono{font-family:"JetBrains Mono",ui-monospace,monospace}
.muted{color:var(--muted)}
.page{background:var(--surface);border:1px solid var(--border);padding:24px;margin:0 0 18px}
.page-break{break-before:page}
.cover{min-height:240mm;display:flex;flex-direction:column;justify-content:space-between;background-image:linear-gradient(to right,var(--grid) 1px,transparent 1px),linear-gradient(to bottom,var(--grid) 1px,transparent 1px);background-size:24px 24px}
.wordmark{font-family:"Silkscreen",monospace;font-size:22px;color:var(--phosphor)}
.classification{float:right;font-family:"JetBrains Mono",monospace;font-size:11px;letter-spacing:.12em;text-transform:uppercase;border:1px solid var(--border);padding:4px 8px}
.cover-title{margin-top:64px}
.cover-subtitle{font-size:18px;color:var(--muted);margin-top:8px}
.cover-meta{display:grid;grid-template-columns:1fr 1fr;gap:8px 24px;font-size:12px;margin-top:24px}
.cover-meta div{border-top:1px solid var(--border);padding-top:6px}
.status{display:inline-block;margin-top:28px;padding:8px 14px;border:1px solid var(--phosphor);color:var(--phosphor);font-family:"JetBrains Mono",monospace;font-size:13px}
.status.clean{background:rgba(8,122,67,.08)}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}
table{width:100%;border-collapse:collapse;font-size:12px}
th,td{text-align:left;vertical-align:top;padding:6px 8px;border-bottom:1px solid var(--border)}
th{font-family:"JetBrains Mono",monospace;font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
thead{display:table-header-group}
tr{break-inside:avoid}
.kv{width:100%;font-size:12px}
.kv th{width:28%}
.badge{display:inline-block;padding:1px 6px;border-radius:2px;color:#fff;font-family:"JetBrains Mono",monospace;font-size:10px;text-transform:uppercase}
.badge-critical{background:var(--crit)}.badge-high{background:var(--high)}.badge-medium{background:var(--med)}.badge-low{background:var(--low)}.badge-info{background:var(--info)}.badge-unknown{background:var(--unknown)}
.card{border:1px solid var(--border);background:var(--surface);padding:16px}
.card h3{margin-bottom:12px}
.summary{display:grid;grid-template-columns:180px 1fr;gap:16px;align-items:center}
.donut{width:180px;height:180px}
.donut-total{font-family:"Silkscreen",monospace;font-size:24px;fill:var(--ink)}
.donut-label{font-family:"Inter",sans-serif;font-size:10px;fill:var(--muted)}
.legend{list-style:none;margin:0;padding:0;display:grid;gap:4px}
.legend li{display:grid;grid-template-columns:10px 1fr 40px 44px;gap:8px;align-items:center;font-size:12px}
.legend-dot{width:10px;height:10px;border-radius:50%}
.legend-count,.legend-pct{font-family:"JetBrains Mono",monospace;text-align:right}
.banner{border:1px solid var(--med);background:rgba(154,90,0,.08);padding:10px 12px;margin:0 0 14px;font-size:12px}
.tool-block{border-top:2px solid var(--phosphor);padding-top:12px;margin-top:18px}
.strip{display:flex;height:8px;border:1px solid var(--border);margin:8px 0 10px;overflow:hidden;background:var(--raised)}
.strip-seg{display:block;height:100%}
.strip-empty{display:block;height:100%;width:100%;background:var(--phosphor);opacity:.35}
.tool-head{display:flex;justify-content:space-between;gap:12px;align-items:baseline;margin-bottom:10px}
.stats{display:flex;flex-wrap:wrap;gap:8px 18px;font-size:12px;margin-bottom:10px}
.stats b{font-family:"JetBrains Mono",monospace}
.detail{color:var(--muted);font-size:11px}
.footer{margin-top:18px;padding-top:8px;border-top:1px solid var(--border);font-family:"JetBrains Mono",monospace;font-size:10px;color:var(--muted);display:flex;justify-content:space-between;gap:12px}
.toc{columns:2;column-gap:24px;font-size:13px}
.toc a{display:block;padding:3px 0}
.clean{color:var(--phosphor)}
`;
```

- [ ] **Step 9: Implement `html.ts` (cover + coordinates for this task)**

`scripts/security-report/src/render/html.ts`:

```ts
import type { ReportModel } from "../model";
import { SEVERITY_LABEL } from "../severity";
import { displayPath, escapeHtml } from "./components";
import { STYLES } from "./styles";

function isoTimestamp(value: string): string {
  return value;
}

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
```

- [ ] **Step 10: Remove the unused helper if the type-check complains**

If `isoTimestamp` is reported unused, delete the `isoTimestamp` function. The plan intentionally keeps the HTML helpers small.

- [ ] **Step 11: Run both tests to verify they pass**

Run: `bun run --cwd scripts/security-report test -- src/render/fonts.test.ts src/render/html.test.ts`

Expected: PASS.

- [ ] **Step 12: Commit**

```bash
git add scripts/security-report/assets/fonts scripts/security-report/src/render/fonts.ts scripts/security-report/src/render/fonts.test.ts scripts/security-report/src/render/styles.ts scripts/security-report/src/render/html.ts scripts/security-report/src/render/html.test.ts
git commit -m "feat(security-report): render brand-style cover and coordinates"
```

---

### Task 13: Executive summary, section tables, charts, and appendix

**Files:**
- Modify: `scripts/security-report/src/render/html.ts`
- Test: `scripts/security-report/src/render/html.test.ts` (extend)

**Interfaces:**
- Produces: `renderExecutiveSummary(model)`, `renderFindingsTable(findings)`, `renderSca(model)`, `renderSast(model)`, `renderAppendix(model)`.
- Consumes: `renderDonut`, `renderSeverityLegend`, `renderSeverityStrip`, `severityBadge`, `safeUrl`, `SEVERITY_LABEL`.

- [ ] **Step 1: Extend the HTML test**

Append to `scripts/security-report/src/render/html.test.ts`:

```ts
import type { Finding } from "../model";
import { makeScanner } from "../test-helpers";

function finding(partial: Partial<Finding>): Finding {
  return {
    id: "id",
    section: "sca",
    ecosystem: "python",
    tool: "PySentry",
    severity: "high",
    sourceSeverity: "high",
    ruleId: "GHSA-1",
    title: "Advisory",
    detail: "Details",
    packageName: "requests",
    installedVersion: "2.0.0",
    vulnerableRange: "<2.1.0",
    fix: "Upgrade to 2.1.0",
    ...partial,
  };
}

describe("report sections", () => {
  test("renders summary charts, finding tables, and appendix", () => {
    const model = makeModel();
    const scaFinding = finding({ id: "sca1" });
    const sastFinding = finding({
      id: "sast1",
      section: "sast",
      ecosystem: "javascript",
      tool: "JS-X-Ray",
      severity: "medium",
      ruleId: "unsafe-stmt",
      title: "<script>alert(1)</script>",
      packageName: undefined,
      file: "apps/web/src/a.ts",
      line: 4,
    });
    model.tools = [
      makeScanner({ findings: [scaFinding] }),
      makeScanner({ tool: "JS-X-Ray", findings: [sastFinding] }),
    ];
    model.sections.sca.findings = [scaFinding];
    model.sections.sca.severityCounts.high = 1;
    model.sections.sast.findings = [sastFinding];
    model.sections.sast.severityCounts.medium = 1;

    const html = renderReport(model, { fontCss: "" });
    expect(html).toContain('id="summary"');
    expect(html).toContain('id="sca"');
    expect(html).toContain('id="sast"');
    expect(html).toContain('id="appendix"');
    expect(html).toContain('data-total="1"');
    expect(html).toContain("Upgrade to 2.1.0");
    expect(html).toContain("apps/web/src/a.ts:4");
    expect(html).not.toContain("<script>alert(1)</script>");
    expect(html).toContain("&lt;script&gt;alert(1)&lt;/script&gt;");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `bun run --cwd scripts/security-report test -- src/render/html.test.ts`

Expected: FAIL because `id="summary"`, `id="sca"`, etc. are absent.

- [ ] **Step 3: Update `html.ts` with summary and section renderers**

Replace the contents of `scripts/security-report/src/render/html.ts` with:

```ts
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
```

- [ ] **Step 4: Run the HTML tests to verify they pass**

Run: `bun run --cwd scripts/security-report test -- src/render/html.test.ts`

Expected: PASS. All section IDs, escaped titles, and chart totals are present.

- [ ] **Step 5: Run the full test suite and type-check**

Run: `bun run --cwd scripts/security-report test`

Expected: PASS.

Run: `bun run --cwd scripts/security-report typecheck`

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add scripts/security-report/src/render/html.ts scripts/security-report/src/render/html.test.ts
git commit -m "feat(security-report): render summary, sections, and appendix"
```

---

### Task 14: PDF rendering with Playwright Chromium

**Files:**
- Create: `scripts/security-report/src/pdf.ts`
- Test: `scripts/security-report/src/pdf.test.ts`

**Interfaces:**
- Produces: `renderPdf(htmlPath, pdfPath)`.
- Consumes: `playwright` ``chromium``, `node:url` `pathToFileURL`.

- [ ] **Step 1: Write the gated PDF test**

`scripts/security-report/src/pdf.test.ts`:

```ts
import { describe, expect, test } from "bun:test";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { renderPdf } from "./pdf";

const runPdf = process.env.SECURITY_REPORT_PDF_TEST === "1";

describe.skipIf(!runPdf)("renderPdf", () => {
  test("writes a non-empty PDF", async () => {
    const dir = mkdtempSync(join(tmpdir(), "security-report-pdf-"));
    try {
      const htmlPath = join(dir, "report.html");
      const pdfPath = join(dir, "report.pdf");
      writeFileSync(htmlPath, "<!doctype html><html><body><h1>Report</h1></body></html>");
      await renderPdf(htmlPath, pdfPath);
      expect(existsSync(pdfPath)).toBe(true);
      const bytes = readFileSync(pdfPath);
      expect(bytes.subarray(0, 4).toString()).toBe("%PDF");
      expect(bytes.length).toBeGreaterThan(1000);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `bun run --cwd scripts/security-report test -- src/pdf.test.ts`

Expected: PASS with 0 tests (skipped by default) or FAIL module-not-found? Because `renderPdf` import fails. So it fails with module-not-found.

- [ ] **Step 3: Implement `pdf.ts`**

`scripts/security-report/src/pdf.ts`:

```ts
import { pathToFileURL } from "node:url";
import { chromium } from "playwright";

export async function renderPdf(htmlPath: string, pdfPath: string): Promise<void> {
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ javaScriptEnabled: false });
    const page = await context.newPage();
    await page.goto(pathToFileURL(htmlPath).href, { waitUntil: "load" });
    await page.pdf({
      path: pdfPath,
      format: "A4",
      printBackground: true,
      preferCSSPageSize: true,
      displayHeaderFooter: true,
      headerTemplate: "<span></span>",
      footerTemplate:
        '<div style="width:100%;padding:0 16mm;font-family:monospace;font-size:8px;color:#5a6658;display:flex;justify-content:space-between;"><span>Agentbox Security Report</span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>',
      margin: { top: "16mm", right: "12mm", bottom: "16mm", left: "12mm" },
    });
  } finally {
    await browser.close();
  }
}
```

- [ ] **Step 4: Run the test with the PDF gate enabled**

Run: `$env:SECURITY_REPORT_PDF_TEST="1"; bun run --cwd scripts/security-report test -- src/pdf.test.ts`

Expected: PASS. If Chromium is missing, run `bun run --cwd scripts/security-report playwright install chromium` and retry.

- [ ] **Step 5: Run the test without the gate**

Run: `Remove-Item Env:SECURITY_REPORT_PDF_TEST -ErrorAction SilentlyContinue; bun run --cwd scripts/security-report test -- src/pdf.test.ts`

Expected: PASS (skipped) or 0 tests, no import errors.

- [ ] **Step 6: Commit**

```bash
git add scripts/security-report/src/pdf.ts scripts/security-report/src/pdf.test.ts
git commit -m "feat(security-report): render PDF with Playwright"
```

---

### Task 15: CLI, orchestration, fixtures mode, artifacts, integration test

**Files:**
- Create: `scripts/security-report/src/cli.ts`
- Create: `scripts/security-report/src/fixtures.ts`
- Create: `scripts/security-report/src/main.ts`
- Test: `scripts/security-report/src/cli.test.ts`
- Test: `scripts/security-report/src/main.test.ts`

**Interfaces:**
- Produces:
  - `CliOptions`, `parseArgs(argv)`, `helpText()`.
  - `loadFixtureProject(dir)`, `loadFixtureResults(dir, project)`.
  - `runReport(options, deps?)`, `main(argv?)`.
- Consumes: all scanners, `collectGit`, `resolveRepoRoot`, `discoverProject`, `buildReportModel`, `determineExitCode`, `renderReport`, `buildFontCss`, `renderPdf`, `commandVersion`, `readPackageVersion`, parse functions.

- [ ] **Step 1: Write the failing CLI test**

`scripts/security-report/src/cli.test.ts`:

```ts
import { describe, expect, test } from "bun:test";
import { parseArgs } from "./cli";

describe("parseArgs", () => {
  test("parses defaults", () => {
    const options = parseArgs([]);
    expect(options.projectPath).toBeNull();
    expect(options.outDir).toBe("reports/security");
    expect(options.classification).toBe("Internal");
    expect(options.failOn).toBe("none");
    expect(options.allowPartial).toBe(false);
    expect(options.noPdf).toBe(false);
    expect(options.includeTests).toBe(false);
    expect(options.excludes).toEqual([]);
    expect(options.scannerTimeout).toBe(300);
    expect(options.fromFixtures).toBeNull();
    expect(options.help).toBe(false);
  });

  test("parses values and flags", () => {
    const options = parseArgs([
      ".",
      "--out",
      "out",
      "--classification",
      "Confidential",
      "--fail-on",
      "high",
      "--allow-partial",
      "--no-pdf",
      "--include-tests",
      "--exclude",
      "**/vendor/**",
      "--scanner-timeout",
      "60",
      "--from-fixtures",
      "fixtures",
    ]);
    expect(options.projectPath).toBe(".");
    expect(options.outDir).toBe("out");
    expect(options.classification).toBe("Confidential");
    expect(options.failOn).toBe("high");
    expect(options.allowPartial).toBe(true);
    expect(options.noPdf).toBe(true);
    expect(options.includeTests).toBe(true);
    expect(options.excludes).toEqual(["**/vendor/**"]);
    expect(options.scannerTimeout).toBe(60);
    expect(options.fromFixtures).toBe("fixtures");
  });

  test("rejects unknown options and bad values", () => {
    expect(() => parseArgs(["--nope"])).toThrow("Unknown option");
    expect(() => parseArgs(["--fail-on", "severe"])).toThrow("Invalid --fail-on");
    expect(() => parseArgs(["--scanner-timeout", "0"])).toThrow("Invalid --scanner-timeout");
    expect(() => parseArgs(["--out"])).toThrow("Missing value for --out");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `bun run --cwd scripts/security-report test -- src/cli.test.ts`

Expected: FAIL with module-not-found for `./cli`.

- [ ] **Step 3: Implement `cli.ts`**

`scripts/security-report/src/cli.ts`:

```ts
import type { Severity } from "./severity";

export interface CliOptions {
  projectPath: string | null;
  outDir: string;
  classification: string;
  failOn: Severity | "none";
  allowPartial: boolean;
  noPdf: boolean;
  includeTests: boolean;
  excludes: string[];
  scannerTimeout: number;
  fromFixtures: string | null;
  verbose: boolean;
  help: boolean;
}

const FAIL_LEVELS = new Set(["none", "low", "medium", "high", "critical"]);

function defaults(): CliOptions {
  return {
    projectPath: null,
    outDir: "reports/security",
    classification: "Internal",
    failOn: "none",
    allowPartial: false,
    noPdf: false,
    includeTests: false,
    excludes: [],
    scannerTimeout: 300,
    fromFixtures: null,
    verbose: false,
    help: false,
  };
}

function value(argv: string[], index: number, flag: string): string {
  const next = argv[index + 1];
  if (next === undefined) throw new Error(`Missing value for ${flag}`);
  return next;
}

export function parseArgs(argv: string[]): CliOptions {
  const options = defaults();

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i]!;
    switch (arg) {
      case "-h":
      case "--help":
        options.help = true;
        break;
      case "--allow-partial":
        options.allowPartial = true;
        break;
      case "--no-pdf":
        options.noPdf = true;
        break;
      case "--include-tests":
        options.includeTests = true;
        break;
      case "--verbose":
        options.verbose = true;
        break;
      case "--out":
        options.outDir = value(argv, i, "--out");
        i += 1;
        break;
      case "--classification":
        options.classification = value(argv, i, "--classification");
        i += 1;
        break;
      case "--fail-on": {
        const level = value(argv, i, "--fail-on");
        if (!FAIL_LEVELS.has(level)) {
          throw new Error(`Invalid --fail-on value: ${level}`);
        }
        options.failOn = level as Severity | "none";
        i += 1;
        break;
      }
      case "--exclude":
        options.excludes.push(value(argv, i, "--exclude"));
        i += 1;
        break;
      case "--scanner-timeout": {
        const raw = value(argv, i, "--scanner-timeout");
        const seconds = Number(raw);
        if (!Number.isInteger(seconds) || seconds <= 0) {
          throw new Error(`Invalid --scanner-timeout value: ${raw}`);
        }
        options.scannerTimeout = seconds;
        i += 1;
        break;
      }
      case "--from-fixtures":
        options.fromFixtures = value(argv, i, "--from-fixtures");
        i += 1;
        break;
      default:
        if (arg.startsWith("-")) throw new Error(`Unknown option: ${arg}`);
        if (options.projectPath !== null) throw new Error(`Unexpected argument: ${arg}`);
        options.projectPath = arg;
    }
  }

  return options;
}

export function helpText(): string {
  return `Usage: bun run scripts/security-report/src/main.ts [path] [options]

  path                       project to audit (default: git root of cwd)
  --out <dir>                output directory (default: reports/security)
  --classification <text>    label on the report (default: Internal)
  --fail-on <level>          none|low|medium|high|critical (default: none)
  --allow-partial            exit 0 when a scanner is partial or failed
  --no-pdf                   skip PDF generation
  --include-tests            include tests/fixtures/specs/stories in SAST
  --exclude <glob>           additional source exclusion (repeatable)
  --scanner-timeout <secs>   per-subprocess-scanner timeout (default: 300)
  --from-fixtures <dir>      test mode: load structured fixtures
  --verbose                  progress and diagnostics on stderr
  -h, --help`;
}
```

- [ ] **Step 4: Write `fixtures.ts`**

`scripts/security-report/src/fixtures.ts`:

```ts
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type {
  GitCoordinates,
  ScannerResult,
} from "./model";
import type { ProjectDiscovery } from "./project";
import { parseBandit, type BanditJson } from "./scanners/bandit";
import { parseBunAudit, type BunAdvisory } from "./scanners/bun-audit";
import { parseJsxrayWarnings, type JsxrayWarning } from "./scanners/jsxray";
import { parsePysentry } from "./scanners/pysentry";
import type { ParsedScanner } from "./scanners/types";

function readJson<T>(dir: string, file: string): T {
  return JSON.parse(readFileSync(join(dir, file), "utf8")) as T;
}

function wrap(
  tool: string,
  parsed: ParsedScanner,
  version: string,
): ScannerResult {
  return {
    tool,
    version,
    command: [],
    status: parsed.partial ? "partial" : "ok",
    exitCode: 0,
    durationMs: 0,
    stats: parsed.stats,
    warnings: parsed.warnings,
    errors: parsed.errors,
    findings: parsed.findings,
    maintenance: parsed.maintenance,
  };
}

export interface FixtureProject {
  git: GitCoordinates;
  project: ProjectDiscovery;
}

export function loadFixtureProject(dir: string): FixtureProject {
  return {
    git: readJson<GitCoordinates>(dir, "git.json"),
    project: readJson<ProjectDiscovery>(dir, "project.json"),
  };
}

export async function loadFixtureResults(
  dir: string,
  project: ProjectDiscovery,
): Promise<ScannerResult[]> {
  const results: ScannerResult[] = [];
  results.push(wrap("PySentry", parsePysentry(readJson(dir, "pysentry.json")), "fixture"));
  results.push(wrap("Bandit", parseBandit(readJson<BanditJson>(dir, "bandit.json"), project.root), "fixture"));
  results.push(
    wrap(
      "Bun audit",
      parseBunAudit(
        readJson<Record<string, BunAdvisory[]>>(dir, "bun-audit.json"),
        project.lockfiles[0]?.resolvedVersions ?? {},
      ),
      "fixture",
    ),
  );

  const jsxrayFixture = readJson<Array<JsxrayWarning & { file: string; description?: string | null }>>(
    dir,
    "jsxray.json",
  );
  const jsxrayFindings = jsxrayFixture.flatMap((warning) =>
    parseJsxrayWarnings([warning], warning.file, project.root, () => warning.description ?? warning.kind),
  );
  results.push({
    tool: "JS-X-Ray",
    version: "fixture",
    command: [],
    status: "ok",
    exitCode: null,
    durationMs: 0,
    stats: { filesScanned: new Set(jsxrayFixture.map((warning) => warning.file)).size },
    warnings: [],
    errors: [],
    findings: jsxrayFindings,
    maintenance: [],
  });

  return results;
}
```

- [ ] **Step 5: Write the failing integration test**

`scripts/security-report/src/main.test.ts`:

```ts
import { afterEach, describe, expect, test } from "bun:test";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { parseArgs } from "./cli";
import { runReport } from "./main";

const dirs: string[] = [];

function fixtureDir(): string {
  const dir = mkdtempSync(join(tmpdir(), "security-report-fixtures-"));
  dirs.push(dir);
  mkdirSync(join(dir, "fixtures"), { recursive: true });
  mkdirSync(join(dir, "project"), { recursive: true });
  return dir;
}

afterEach(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

describe("runReport with fixtures", () => {
  test("writes HTML, JSON, and latest artifacts", async () => {
    const dir = fixtureDir();
    const fixtures = join(dir, "fixtures");
    const project = join(dir, "project");
    const out = join(dir, "out");

    writeFileSync(
      join(fixtures, "project.json"),
      JSON.stringify({
        name: "<script>alert(1)</script>",
        root: project,
        components: [],
        lockfiles: [],
        pythonRoots: [],
        jsComponents: [],
      }),
    );
    writeFileSync(
      join(fixtures, "git.json"),
      JSON.stringify({
        root: project,
        remoteUrl: null,
        branch: "main",
        headSha: "a".repeat(40),
        headShortSha: "aaaaaaa",
        treeSha: "b".repeat(40),
        describe: null,
        latestTag: null,
        authorName: "Ada",
        authorEmail: "ada@example.com",
        authoredAt: "2026-11-22T10:00:00Z",
        subject: "Test",
        dirty: false,
        dirtyFiles: 0,
        statusCounts: { added: 0, modified: 0, deleted: 0, renamed: 0, untracked: 0, unmerged: 0 },
      }),
    );
    writeFileSync(
      join(fixtures, "pysentry.json"),
      JSON.stringify({
        total_packages: 1,
        vulnerable_packages: 1,
        total_vulnerabilities: 1,
        vulnerabilities: [
          {
            package_name: "requests",
            installed_version: "2.0.0",
            id: "GHSA-1",
            summary: "Bad package <script>alert(1)</script>",
            description: null,
            severity: "critical",
            affected_versions: [],
            fixed_versions: [],
            references: [],
          },
        ],
        fix_suggestions: [],
        warnings: [],
        maintenance_issues: [],
        partial: false,
        failed_sources: [],
      }),
    );
    writeFileSync(join(fixtures, "bandit.json"), JSON.stringify({ results: [], metrics: {}, errors: [] }));
    writeFileSync(join(fixtures, "bun-audit.json"), JSON.stringify({}));
    writeFileSync(join(fixtures, "jsxray.json"), JSON.stringify([]));

    const options = parseArgs([
      "--from-fixtures",
      fixtures,
      "--out",
      out,
      "--no-pdf",
    ]);
    const result = await runReport(options, { now: () => new Date("2026-11-22T12:00:00Z") });

    expect(result.exitCode).toBe(0);
    expect(existsSync(result.artifacts.html)).toBe(true);
    expect(existsSync(result.artifacts.json)).toBe(true);
    expect(existsSync(join(out, "latest.html"))).toBe(true);
    expect(existsSync(result.artifacts.pdf ?? "")).toBe(false);

    const html = readFileSync(result.artifacts.html, "utf8");
    expect(html).toContain('id="sca"');
    expect(html).toContain("Critical");
    expect(html).not.toContain("<script>alert(1)</script>");
    expect(html).toContain("&lt;script&gt;alert(1)&lt;/script&gt;");

    const json = JSON.parse(readFileSync(result.artifacts.json, "utf8")) as {
      sections: { sca: { severityCounts: { critical: number } } };
    };
    expect(json.sections.sca.severityCounts.critical).toBe(1);
  });
});
```

- [ ] **Step 6: Run the test to verify it fails**

Run: `bun run --cwd scripts/security-report test -- src/main.test.ts`

Expected: FAIL with module-not-found for `./main`.

- [ ] **Step 7: Implement `main.ts`**

`scripts/security-report/src/main.ts`:

```ts
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

async function collectVersions(root: string, toolRoot: string): Promise<Record<string, string>> {
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

  const versions = options.fromFixtures
    ? {}
    : await collectVersions(root, toolRoot);

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
      console.error("Run `bun run --cwd scripts/security-report playwright install chromium` and retry.");
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
    console.error(`  ${tool.tool}: ${tool.status}${tool.errors.length > 0 ? ` (${tool.errors[0]})` : ""}`);
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
```

- [ ] **Step 8: Run the integration test to verify it passes**

Run: `bun run --cwd scripts/security-report test -- src/main.test.ts`

Expected: PASS. The fixture project name is escaped and the critical SCA count is 1.

- [ ] **Step 9: Run the full suite and type-check**

Run: `bun run --cwd scripts/security-report test`

Expected: PASS (PDF test skipped unless gated).

Run: `bun run --cwd scripts/security-report typecheck`

Expected: no errors.

- [ ] **Step 10: Commit**

```bash
git add scripts/security-report/src/cli.ts scripts/security-report/src/cli.test.ts scripts/security-report/src/fixtures.ts scripts/security-report/src/main.ts scripts/security-report/src/main.test.ts
git commit -m "feat(security-report): add CLI orchestration and fixture mode"
```

---

### Task 16: Repository integration, documentation, and end-to-end verification

**Files:**
- Modify: `justfile`
- Modify: `.gitignore`
- Modify: `AGENTS.md`
- Create: `scripts/security-report/README.md`

**Interfaces:**
- Produces: `just security-report`, `just test-security-report`; `reports/` ignored; setup/check integration.

- [ ] **Step 1: Add the just recipes**

Modify `justfile` after the `e2e:` recipe:

```make
# Generate the security audit report (HTML + PDF + JSON).
_security-report-deps:
    bun install --cwd scripts/security-report --frozen-lockfile

security-report *args: _security-report-deps
    bun run scripts/security-report/src/main.ts {{args}}

# Run security-report unit tests and type-check.
test-security-report: _security-report-deps
    bun run --cwd scripts/security-report test
    bun run --cwd scripts/security-report typecheck
```

Add `bun install --cwd scripts/security-report` to the `setup` recipe after `cd apps/web && bun install`:

```make
setup:
    uv sync
    cd apps/web && bun install
    bun install --cwd scripts/security-report
```

Change the `check` recipe:

```make
check: lint test test-security-report
```

- [ ] **Step 2: Ignore report artifacts**

Append to `.gitignore`:

```
/reports/
```

- [ ] **Step 3: Write the tool README**

`scripts/security-report/README.md`:

```markdown
# Agentbox Security Report

Generates a light, print-first HTML security audit report with severity charts, a machine-readable
JSON snapshot, and an A4 PDF.

## Usage

From the repository root:

```powershell
just security-report
just security-report --no-pdf
just security-report --fail-on high
just security-report ../another-project --out reports/security/other
```

Artifacts are written to `reports/security/` (gitignored):

- `agentbox-security-<shortsha>-<timestamp>.html`
- `agentbox-security-<shortsha>-<timestamp>.pdf`
- `agentbox-security-<shortsha>-<timestamp>.json`
- `latest.html`, `latest.pdf`, `latest.json`

## Scanners

| Section | Ecosystem | Tool | Structured input |
| --- | --- | --- | --- |
| SCA | Python | PySentry | `--format json` |
| SCA | JavaScript | Bun audit / NPM audit | `--json` |
| SAST | Python | Bandit | `-f json` |
| SAST | JavaScript/TypeScript | JS-X-Ray | in-process warning objects |

Tests, fixtures, specs, and stories are excluded from SAST by default; pass `--include-tests` to
include them. Dependency and generated directories (`.venv`, `node_modules`, `dist`, `build`,
`coverage`, caches) are always excluded.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | A scanner is partial/failed, or PDF generation failed |
| 2 | Usage/configuration error |
| 3 | `--fail-on` threshold met |

Findings do not fail the run unless `--fail-on` is set.

## Development

```powershell
bun install --cwd scripts/security-report
bun run --cwd scripts/security-report test
bun run --cwd scripts/security-report typecheck
$env:SECURITY_REPORT_PDF_TEST="1"; bun run --cwd scripts/security-report test -- src/pdf.test.ts
```
```

- [ ] **Step 4: Update AGENTS.md**

Add under "Setup and local dev":

```markdown
- `just security-report` writes `reports/security/latest.{html,pdf,json}` (gitignored). It runs PySentry, Bandit, Bun audit, and JS-X-Ray and degrades gracefully when a scanner is unavailable.
```

Add under "Checks":

```markdown
- `just test-security-report` runs the security-report Bun tests and TypeScript type-check.
```

- [ ] **Step 5: Run the tool test suite and type-check**

Run: `just test-security-report`

Expected: PASS and no TypeScript errors.

- [ ] **Step 6: Generate a real report without PDF**

Run: `just security-report --no-pdf`

Expected: exit 0, `reports/security/latest.html` and `latest.json` created, summary printed to stderr. Expected approximate findings: SCA 3 JS advisories (1 high, 2 medium), SAST 6 low Bandit findings plus 4 medium JS-X-Ray `shady-link` warnings, 0 Python SCA findings.

- [ ] **Step 7: Generate the PDF**

Run: `just security-report`

Expected: exit 0, `reports/security/latest.pdf` created. If Chromium is missing:

```powershell
bun run --cwd scripts/security-report playwright install chromium
```

- [ ] **Step 8: Verify the PDF header and artifacts**

Run:

```powershell
Get-ChildItem reports/security
$bytes = [System.IO.File]::ReadAllBytes("reports/security/latest.pdf")
[System.Text.Encoding]::ASCII.GetString($bytes[0..3])
```

Expected: artifact list includes timestamped HTML/JSON/PDF plus `latest.*`; header output is `%PDF`.

- [ ] **Step 9: Verify reports are ignored**

Run: `git status --short`

Expected: no entries under `reports/`.

- [ ] **Step 10: Verify the HTML is self-contained and escaped**

Run:

```powershell
Select-String -Path reports/security/latest.html -Pattern "<script","data:font/woff2;base64","id=\"sca\"","id=\"sast\"","id=\"appendix\""
```

Expected: matches for the font data, section IDs, and no `<script` tags from report data. If `<script` appears, inspect the match; it must only be the literal text in an escaped title.

- [ ] **Step 11: Commit the integration**

```bash
git add justfile .gitignore AGENTS.md scripts/security-report/README.md
git commit -m "feat(security-report): wire just recipes and docs"
```

- [ ] **Step 12: Final verification**

Run:

```powershell
just test-security-report
just security-report --no-pdf
git status --short
git log --oneline -3
```

Expected: tests pass, report regenerates, working tree clean (apart from ignored reports), recent commits show the feature.

---

## Self-Review Notes

- Spec coverage: architecture, structured-only parsing, discovery/exclusions, all four scanners, severity normalization, JSON snapshot, HTML/PDF layout, CLI/artifacts, failure/exit codes, security, testing, dependencies, repo integration, and limitations all map to tasks above.
- No placeholders: every task includes concrete code, commands, and expected results.
- Type consistency: `Severity`, `Finding`, `ScannerResult`, `ScanContext`, `ParsedScanner`, `ProjectDiscovery`, `CliOptions`, and `RunArtifacts` are defined once and reused with the same names.
- Known implementation caveat: `AstAnalyser.analyseFile` throws on paths containing `d.ts`; the plan uses `analyse` with explicit file reads and skips `.d.ts`.
- Known implementation caveat: `TsSourceParser` requires the `typescript` package; it is pinned in `package.json`.
