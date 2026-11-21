// apps/web/scripts/screenshots-ux4.mjs
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const here = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.resolve(here, "../../../docs/reviews/2026-11-21-ux-4");
const base = "http://localhost:6006/iframe.html";
const desktop = { width: 1280, height: 900 };

const shots = [
  ["error-state", "patterns-errorstates--error", desktop],
  ["confirm-standard", "overlays-overview--standard-confirm", desktop],
  ["confirm-typed", "overlays-overview--type-to-confirm", desktop],
  ["form-validation", "forms-validation--errors", desktop],
];

await mkdir(outDir, { recursive: true });
const browser = await chromium.launch();
for (const [name, id, viewport] of shots) {
  const page = await browser.newPage({ viewport, colorScheme: "dark" });
  await page.goto(`${base}?id=${id}&globals=theme:dark&viewMode=story`);
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
