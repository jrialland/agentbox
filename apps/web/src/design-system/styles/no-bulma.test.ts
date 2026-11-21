import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const root = join(process.cwd(), "src");
const bannedTokens = new Set([
  "is-align-items-center",
  "is-block",
  "has-text-weight-semibold",
  "has-text-grey",
  "tag",
  "is-light",
  "is-danger",
  "box",
  "title",
  "button",
  "navbar",
  "columns",
  "column",
  "menu-list",
  "notification",
  "is-flex",
  "is-justify-content-space-between",
]);
const classAttribute = /className=(?:"([^"]*)"|\{`([^`]*)`\})/g;

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return files(path);
    return path.endsWith(".tsx") || path.endsWith(".ts") ? [path] : [];
  });
}

function hasBulmaClass(source: string): boolean {
  for (const line of source.split(/\r?\n/)) {
    for (const match of line.matchAll(classAttribute)) {
      const value = match[1] ?? match[2] ?? "";
      if (value.split(/\s+/).some((token) => bannedTokens.has(token))) {
        return true;
      }
    }
  }
  return false;
}

describe("no Bulma classes", () => {
  it("keeps components free of Bulma class names", () => {
    const offenders = files(root)
      .filter((path) => !path.includes(".test."))
      .filter((path) => hasBulmaClass(readFileSync(path, "utf8")));
    expect(offenders).toEqual([]);
  });
});


