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
