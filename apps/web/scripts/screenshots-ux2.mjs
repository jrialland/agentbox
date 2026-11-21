import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const here = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.resolve(here, "../../../docs/reviews/2026-11-21-ux-2");
const base = "http://localhost:6006/iframe.html";

const desktop = { width: 1280, height: 900 };
const mobile = { width: 390, height: 844 };

const shots = [
  ["markdown-dark", "chat-states--markdown", desktop, "dark"],
  ["markdown-light", "chat-states--markdown", desktop, "light"],
  ["mermaid-success", "chat-states--mermaid-success", desktop, "dark"],
  ["mermaid-fallback", "chat-states--mermaid-fallback", desktop, "dark"],
  ["live-segments", "chat-states--live-segment-order", desktop, "dark"],
  ["activity-collapsed", "chat-states--activity-collapsed", desktop, "dark"],
  ["activity-expanded", "chat-states--activity-expanded", desktop, "dark"],
  ["running-status", "chat-states--running-status", desktop, "dark"],
  ["composer-desktop", "chat-states--composer-state", desktop, "dark"],
  ["composer-mobile", "chat-states--composer-state", mobile, "dark"],
  ["fork-banner", "chat-states--fork-state", desktop, "dark"],
  ["attachments", "chat-states--attachments", desktop, "dark"],
  ["error-state", "chat-states--error-state", desktop, "dark"],
  ["split-desktop", "chat-states--split-view", desktop, "dark"],
  ["split-mobile", "chat-states--split-view", mobile, "dark"],
];

await mkdir(outDir, { recursive: true });
const browser = await chromium.launch();

for (const [name, id, viewport, theme] of shots) {
  const page = await browser.newPage({
    viewport,
    colorScheme: theme,
  });
  await page.goto(`${base}?id=${id}&globals=theme:${theme}&viewMode=story`);
  await page.waitForSelector("#storybook-root", { timeout: 30000 });
  await page.waitForTimeout(id.includes("mermaid") ? 1800 : 500);
  await page.screenshot({
    path: path.join(outDir, `${name}.png`),
    fullPage: true,
    animations: "disabled",
  });
  await page.close();
  console.log(`saved ${name}.png`);
}

await browser.close();

