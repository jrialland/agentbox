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
