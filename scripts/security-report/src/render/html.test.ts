import { describe, expect, test } from "bun:test";
import { makeModel } from "../test-helpers";
import { renderReport } from "./html";

describe("renderReport", () => {
  test("renders a self-contained document with cover and coordinates", () => {
    const model = makeModel();
    const html = renderReport(model, { fontCss: "@font-face{}" });

    expect(html.startsWith("<!doctype html>")).toBe(true);
    expect(html).toContain('<html lang="en">');
    expect(html).toContain("[AGENTBOX]");
    expect(html).toContain(model.reportId);
    expect(html).toContain("Security Audit Report");
    expect(html).toContain('class="page cover"');
    expect(html).toContain("aaaaaaa");
    expect(html).toContain("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");
    expect(html).toContain("git@example.com:org/repo.git");
    expect(html).toContain("@font-face{}");
    expect(html).not.toContain("<script>");
  });

  test("escapes project and classification text", () => {
    const model = makeModel();
    model.project.name = "<script>alert(1)</script>";
    model.classification = "<b>x</b>";
    const html = renderReport(model, { fontCss: "" });
    expect(html).not.toContain("<script>alert(1)</script>");
    expect(html).toContain("&lt;script&gt;alert(1)&lt;/script&gt;");
    expect(html).toContain("&lt;b&gt;x&lt;/b&gt;");
  });
});

import type { Finding } from "../model";
import { makeScanner } from "../test-helpers";

function finding(partial: Partial<Finding>): Finding {
  return {
    id: "id",
    section: "sca",
    ecosystem: "python",
    tool: "PySentry",
    severity: "high",
    sourceSeverity: "high",
    ruleId: "GHSA-1",
    title: "Advisory",
    detail: "Details",
    packageName: "requests",
    installedVersion: "2.0.0",
    vulnerableRange: "<2.1.0",
    fix: "Upgrade to 2.1.0",
    ...partial,
  };
}

describe("report sections", () => {
  test("renders summary charts, finding tables, and appendix", () => {
    const model = makeModel();
    const scaFinding = finding({ id: "sca1" });
    const sastFinding = finding({
      id: "sast1",
      section: "sast",
      ecosystem: "javascript",
      tool: "JS-X-Ray",
      severity: "medium",
      ruleId: "unsafe-stmt",
      title: "<script>alert(1)</script>",
      packageName: undefined,
      file: "apps/web/src/a.ts",
      line: 4,
    });
    model.tools = [
      makeScanner({ findings: [scaFinding] }),
      makeScanner({ tool: "JS-X-Ray", findings: [sastFinding] }),
    ];
    model.sections.sca.findings = [scaFinding];
    model.sections.sca.severityCounts.high = 1;
    model.sections.sast.findings = [sastFinding];
    model.sections.sast.severityCounts.medium = 1;

    const html = renderReport(model, { fontCss: "" });
    expect(html).toContain('id="summary"');
    expect(html).toContain('id="sca"');
    expect(html).toContain('id="sast"');
    expect(html).toContain('id="appendix"');
    expect(html).toContain('data-total="1"');
    expect(html).toContain("Upgrade to 2.1.0");
    expect(html).toContain("apps/web/src/a.ts:4");
    expect(html).not.toContain("<script>alert(1)</script>");
    expect(html).toContain("&lt;script&gt;alert(1)&lt;/script&gt;");
  });
});
