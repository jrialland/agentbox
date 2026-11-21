import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const here = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.resolve(here, "../../../docs/reviews/2026-11-21-ux-3");
const base = "http://localhost:6006/iframe.html";
const desktop = { width: 1280, height: 900 };
const mobile = { width: 390, height: 844 };

const shots = [
  ["help-overview", "help-states--overview", desktop, "dark"],
  ["provider-form", "providers-setup--form", desktop, "dark"],
  ["tools-editor", "agents-editors--tools", desktop, "dark"],
  ["modes-editor", "agents-editors--modes", desktop, "dark"],
  ["a2a-structured", "agents-editors--a-2-a-structured", desktop, "dark"],
  ["a2a-json", "agents-editors--a-2-a-json", desktop, "dark"],
  ["onboarding-checklist", "onboarding-states--checklist", desktop, "dark"],
  ["onboarding-welcome", "onboarding-states--welcome", mobile, "dark"],
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
  await page.waitForTimeout(600);
  await page.screenshot({
    path: path.join(outDir, `${name}.png`),
    fullPage: true,
    animations: "disabled",
  });
  await page.close();
  console.log(`saved ${name}.png`);
}

await browser.close();
