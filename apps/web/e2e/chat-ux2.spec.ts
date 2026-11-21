import { expect, type Page, test } from "@playwright/test";

import { setupSession } from "./helpers";

async function openSession(page: Page, sessionId: string) {
  await page.goto(`/sessions/${sessionId}`);
  await page.waitForLoadState("networkidle");
}

test("renders a live tool card before the final assistant text and splits the app", async ({
  page,
  request,
}) => {
  const sessionId = await setupSession(page, request, "test_tool_slow", {
    withMcp: true,
  });
  await openSession(page, sessionId);

  await page.getByLabel("Message").fill("show the app");
  await page.getByRole("button", { name: "Send" }).click();

  const live = page.getByTestId("live-turn");
  const tool = live.locator('[data-segment="tool"]').first();
  const text = live.locator('[data-segment="text"]').first();
  await expect(tool).toBeVisible({ timeout: 30000 });
  await expect(text).toContainText("Tool", { timeout: 30000 });
  const toolBox = await tool.boundingBox();
  const textBox = await text.boundingBox();
  expect(toolBox && textBox && toolBox.y).toBeLessThan(textBox?.y ?? 0);

  await expect(page.getByTestId("app-panel")).toBeVisible({ timeout: 30000 });
  await expect(
    page.getByRole("separator", { name: "Resize app panel" }),
  ).toBeVisible();

  const composer = page.getByTestId("composer");
  await expect(composer).toBeVisible();
  const composerBox = await composer.boundingBox();
  const viewport = page.viewportSize();
  expect(composerBox).not.toBeNull();
  expect(viewport).not.toBeNull();
  expect(composerBox!.y + composerBox!.height).toBeLessThanOrEqual(
    viewport!.height + 1,
  );
});

test("stops a slow run, keeps partial output, and offers retry", async ({
  page,
  request,
}) => {
  const sessionId = await setupSession(page, request, "test_slow");
  await openSession(page, sessionId);

  await page.getByLabel("Message").fill("slow please");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("Partial")).toBeVisible({ timeout: 15000 });

  await page.getByRole("button", { name: "Stop" }).first().click();
  await expect(page.getByText("cancelled").first()).toBeVisible({
    timeout: 15000,
  });
  await expect(page.getByRole("button", { name: "Retry" }).first()).toBeVisible();
});

test("shows a per-turn provider error and retries successfully", async ({
  page,
  request,
}) => {
  const sessionId = await setupSession(page, request, "test_flaky");
  await openSession(page, sessionId);

  await page.getByLabel("Message").fill("try once");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByTestId("error-card").first()).toBeVisible({ timeout: 15000 });
  await expect(page.getByText(/provider exploded once/).first()).toBeVisible();

  await page.getByRole("button", { name: "Retry" }).first().click();
  await expect(page.getByText("Recovered answer").last()).toBeVisible({
    timeout: 15000,
  });
});

test("renders markdown, mermaid fallback, and downloadable attachment history", async ({
  page,
  request,
}) => {
  const sessionId = await setupSession(page, request, "test_markdown");
  await openSession(page, sessionId);

  await page.getByLabel("Attach files").setInputFiles({
    name: "note.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("attachment body"),
  });
  await expect(page.getByText("note.txt")).toBeVisible();

  await page.getByLabel("Message").fill("markdown please");
  await page.getByRole("button", { name: "Send" }).click();

  await expect(
    page.getByRole("heading", { name: "Chat UX" }).last(),
  ).toBeVisible({ timeout: 15000 });
  await expect(page.getByRole("table").last()).toBeVisible();
  await expect(page.locator(".md-code").first()).toContainText("print");
  await expect(page.locator(".mermaid-canvas svg").first()).toBeVisible({

    timeout: 20000,
  });
  await expect(page.getByText("Diagram could not be rendered").last()).toBeVisible();

  await page.reload();
  await page.waitForLoadState("networkidle");
  const chip = page.getByRole("link", { name: /note\.txt/ });
  await expect(chip).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await chip.click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("note.txt");
});






