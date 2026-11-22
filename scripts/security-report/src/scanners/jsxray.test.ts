import { describe, expect, test } from "bun:test";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
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
