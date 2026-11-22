import { afterEach, describe, expect, test } from "bun:test";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
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
        statusCounts: {
          added: 0,
          modified: 0,
          deleted: 0,
          renamed: 0,
          untracked: 0,
          unmerged: 0,
        },
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
    writeFileSync(
      join(fixtures, "bandit.json"),
      JSON.stringify({ results: [], metrics: {}, errors: [] }),
    );
    writeFileSync(join(fixtures, "bun-audit.json"), JSON.stringify({}));
    writeFileSync(join(fixtures, "jsxray.json"), JSON.stringify([]));

    const options = parseArgs([
      "--from-fixtures",
      fixtures,
      "--out",
      out,
      "--no-pdf",
    ]);
    const result = await runReport(options, {
      now: () => new Date("2026-11-22T12:00:00Z"),
    });

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
