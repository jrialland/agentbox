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
