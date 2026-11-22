import { describe, expect, test } from "bun:test";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { renderPdf } from "./pdf";

const runPdf = process.env.SECURITY_REPORT_PDF_TEST === "1";

describe.skipIf(!runPdf)("renderPdf", () => {
  test("writes a non-empty PDF", async () => {
    const dir = mkdtempSync(join(tmpdir(), "security-report-pdf-"));
    try {
      const htmlPath = join(dir, "report.html");
      const pdfPath = join(dir, "report.pdf");
      writeFileSync(htmlPath, "<!doctype html><html><body><h1>Report</h1></body></html>");
      await renderPdf(htmlPath, pdfPath);
      expect(existsSync(pdfPath)).toBe(true);
      const bytes = readFileSync(pdfPath);
      expect(bytes.subarray(0, 4).toString()).toBe("%PDF");
      expect(bytes.length).toBeGreaterThan(1000);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
