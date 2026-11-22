import { describe, expect, test } from "bun:test";
import { emptySeverityCounts } from "../severity";
import {
  renderDonut,
  renderSeverityLegend,
  renderSeverityStrip,
} from "./charts";

describe("renderDonut", () => {
  test("renders one segment per non-zero bucket", () => {
    const svg = renderDonut([
      { severity: "critical", count: 1 },
      { severity: "high", count: 1 },
      { severity: "low", count: 0 },
    ]);
    expect(svg).toContain('data-total="2"');
    expect(svg.match(/class="pie-slice"/g)).toHaveLength(2);
    expect(svg).toContain('data-severity="critical"');
    expect(svg).toContain('data-severity="high"');
    expect(svg).not.toContain('data-severity="low"');
  });

  test("renders a clean ring when there are no findings", () => {
    const svg = renderDonut([{ severity: "critical", count: 0 }]);
    expect(svg).toContain('data-empty="true"');
    expect(svg).toContain("0");
  });
});

describe("renderSeverityLegend", () => {
  test("shows every bucket with counts and percentages", () => {
    const counts = emptySeverityCounts();
    counts.critical = 1;
    counts.high = 1;
    const html = renderSeverityLegend(counts);
    expect(html).toContain("Critical");
    expect(html).toContain(">1<");
    expect(html).toContain("50%");
    expect(html).toContain("Unknown");
  });
});

describe("renderSeverityStrip", () => {
  test("renders one segment per non-zero bucket", () => {
    const counts = emptySeverityCounts();
    counts.high = 1;
    counts.low = 1;
    const html = renderSeverityStrip(counts);
    expect(html).toContain('data-total="2"');
    expect(html.match(/strip-seg/g)).toHaveLength(2);
  });
});
