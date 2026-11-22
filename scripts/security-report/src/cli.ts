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
