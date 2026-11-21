import { expect, test } from "@playwright/test";

import { setupSession } from "./helpers";

test("wide mermaid diagrams fill the block width and stay legible", async ({
  page,
  request,
}) => {
  const sessionId = await setupSession(page, request, "test_long");
  await page.goto(`/sessions/${sessionId}`);
  await page.waitForLoadState("networkidle");

  await page.getByLabel("Message").fill("diagram please");
  await page.getByRole("button", { name: "Send" }).click();

  const block = page.locator(".mermaid-block").last();
  await expect(block.locator(".mermaid-canvas svg")).toBeVisible({
    timeout: 30000,
  });

  await expect
    .poll(async () => {
      const blockBox = await block.boundingBox();
      const svgBox = await block.locator(".mermaid-canvas svg").boundingBox();
      if (!blockBox || !svgBox) return 0;
      return svgBox.width / blockBox.width;
    })
    .toBeGreaterThan(0.8);

  const svgBox = await block.locator(".mermaid-canvas svg").boundingBox();
  expect(svgBox).not.toBeNull();
  expect(svgBox!.height).toBeGreaterThan(40);

  await expect(page.getByRole("button", { name: "Zoom in" }).last()).toBeVisible();
  await expect(page.getByRole("button", { name: "Zoom out" }).last()).toBeVisible();
  await expect(page.getByRole("button", { name: "Reset zoom" }).last()).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Enter fullscreen" }).last(),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Copy diagram" }).last()).toBeVisible();

  await page.getByRole("button", { name: "Enter fullscreen" }).last().click();
  await expect
    .poll(() => page.evaluate(() => document.fullscreenElement !== null))
    .toBe(true);
  await expect(
    page.getByRole("button", { name: "Exit fullscreen" }).last(),
  ).toBeVisible();
  await page.getByRole("button", { name: "Exit fullscreen" }).last().click();
  await expect
    .poll(() => page.evaluate(() => document.fullscreenElement === null))
    .toBe(true);
});

test("vertical mermaid diagrams keep their natural width", async ({
  page,
  request,
}) => {
  const sessionId = await setupSession(page, request, "test_markdown");
  await page.goto(`/sessions/${sessionId}`);
  await page.waitForLoadState("networkidle");

  await page.getByLabel("Message").fill("markdown please");
  await page.getByRole("button", { name: "Send" }).click();

  const block = page.locator(".mermaid-block").first();
  await expect(block.locator(".mermaid-canvas svg")).toBeVisible({
    timeout: 30000,
  });

  await expect
    .poll(async () => {
      const blockBox = await block.boundingBox();
      const svgBox = await block.locator(".mermaid-canvas svg").boundingBox();
      if (!blockBox || !svgBox) return 1;
      return svgBox.width / blockBox.width;
    })
    .toBeLessThan(0.6);

  const svgBox = await block.locator(".mermaid-canvas svg").boundingBox();
  expect(svgBox).not.toBeNull();
  expect(svgBox!.height).toBeLessThan(1200);
});
