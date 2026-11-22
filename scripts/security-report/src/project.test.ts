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
      expect(
        files.map((file) => file.replace(root, "").split("\\").join("/")).sort(),
      ).toEqual(["/src/a.ts", "/src/b.js"]);
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
      expect(project.root).toBe(root);
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
