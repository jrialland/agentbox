import { describe, expect, test } from "bun:test";
import {
  displayPath,
  escapeHtml,
  safeUrl,
  severityBadge,
  truncate,
} from "./components";

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
