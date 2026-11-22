import type { Severity } from "../severity";
import {
  SEVERITIES,
  SEVERITY_COLOR,
  SEVERITY_LABEL,
} from "../severity";
import { escapeHtml } from "./components";

export interface SeveritySlice {
  severity: Severity;
  count: number;
}

export function renderDonut(
  slices: SeveritySlice[],
  options: { size?: number; label?: string } = {},
): string {
  const size = options.size ?? 180;
  const stroke = Math.round(size * 0.16);
  const radius = (size - stroke) / 2;
  const center = size / 2;
  const circumference = 2 * Math.PI * radius;
  const total = slices.reduce((sum, slice) => sum + slice.count, 0);
  const label = escapeHtml(options.label ?? "findings");

  if (total === 0) {
    return `<svg class="donut" viewBox="0 0 ${size} ${size}" role="img" aria-label="No findings" data-empty="true" data-total="0"><circle cx="${center}" cy="${center}" r="${radius}" fill="none" stroke="#087a43" stroke-width="${stroke}" /><text x="${center}" y="${center}" dominant-baseline="central" text-anchor="middle" class="donut-total">0</text><text x="${center}" y="${center + 22}" dominant-baseline="central" text-anchor="middle" class="donut-label">${label}</text></svg>`;
  }

  let offset = 0;
  const segments = slices
    .filter((slice) => slice.count > 0)
    .map((slice) => {
      const length = (slice.count / total) * circumference;
      const segment = `<circle class="pie-slice" data-severity="${slice.severity}" cx="${center}" cy="${center}" r="${radius}" fill="none" stroke="${SEVERITY_COLOR[slice.severity]}" stroke-width="${stroke}" stroke-dasharray="${length} ${circumference - length}" stroke-dashoffset="${-offset}" transform="rotate(-90 ${center} ${center})"><title>${SEVERITY_LABEL[slice.severity]}: ${slice.count}</title></circle>`;
      offset += length;
      return segment;
    })
    .join("");

  return `<svg class="donut" viewBox="0 0 ${size} ${size}" role="img" aria-label="${total} ${label}" data-empty="false" data-total="${total}">${segments}<text x="${center}" y="${center}" dominant-baseline="central" text-anchor="middle" class="donut-total">${total}</text><text x="${center}" y="${center + 22}" dominant-baseline="central" text-anchor="middle" class="donut-label">${label}</text></svg>`;
}

export function renderSeverityLegend(counts: Record<Severity, number>): string {
  const total = SEVERITIES.reduce((sum, severity) => sum + counts[severity], 0);
  const rows = SEVERITIES.map((severity) => {
    const percent = total === 0 ? 0 : Math.round((counts[severity] / total) * 100);
    return `<li><span class="legend-dot" style="background:${SEVERITY_COLOR[severity]}"></span><span class="legend-label">${SEVERITY_LABEL[severity]}</span><span class="legend-count">${counts[severity]}</span><span class="legend-pct">${percent}%</span></li>`;
  }).join("");
  return `<ul class="legend">${rows}</ul>`;
}

export function renderSeverityStrip(counts: Record<Severity, number>): string {
  const total = SEVERITIES.reduce((sum, severity) => sum + counts[severity], 0);
  if (total === 0) {
    return `<div class="strip" data-total="0"><span class="strip-empty"></span></div>`;
  }
  const segments = SEVERITIES.filter((severity) => counts[severity] > 0)
    .map(
      (severity) =>
        `<span class="strip-seg" style="width:${(counts[severity] / total) * 100}%;background:${SEVERITY_COLOR[severity]}" title="${SEVERITY_LABEL[severity]}: ${counts[severity]}"></span>`,
    )
    .join("");
  return `<div class="strip" data-total="${total}">${segments}</div>`;
}
