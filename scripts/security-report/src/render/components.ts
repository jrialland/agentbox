import { relative, sep } from "node:path";
import type { Severity } from "../severity";
import { SEVERITY_LABEL } from "../severity";

const ESCAPES: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

export function escapeHtml(value: unknown): string {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ESCAPES[char] ?? char);
}

export function safeUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}

export function toPosix(value: string): string {
  return value.split(sep).join("/");
}

export function displayPath(root: string, file: string | null | undefined): string | null {
  if (!file) return null;
  const rel = relative(root, file);
  return toPosix(rel.startsWith("..") ? file : rel);
}

export function truncate(value: string, max: number): string {
  return value.length <= max ? value : `${value.slice(0, Math.max(0, max - 1))}…`;
}

export function severityBadge(severity: Severity): string {
  return `<span class="badge badge-${severity}">${SEVERITY_LABEL[severity]}</span>`;
}
