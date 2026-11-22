import { describe, expect, test } from "bun:test";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { buildFontCss } from "./fonts";

describe("buildFontCss", () => {
  test("embeds all four fonts as base64", () => {
    const dir = mkdtempSync(join(tmpdir(), "security-report-fonts-"));
    try {
      for (const name of [
        "Silkscreen-Regular.woff2",
        "Inter-Regular.woff2",
        "Inter-SemiBold.woff2",
        "JetBrainsMono-Regular.woff2",
      ]) {
        writeFileSync(join(dir, name), "fake-font-bytes");
      }
      const css = buildFontCss(dir);
      expect(css.match(/@font-face/g)).toHaveLength(4);
      expect(css).toContain("data:font/woff2;base64,");
      expect(css).toContain("Silkscreen");
      expect(css).toContain("JetBrains Mono");
      expect(css).toContain("Inter");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
