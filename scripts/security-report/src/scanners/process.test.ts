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
