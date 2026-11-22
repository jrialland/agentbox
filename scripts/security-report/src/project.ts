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
