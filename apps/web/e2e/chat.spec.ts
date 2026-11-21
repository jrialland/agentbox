import { expect, test } from "@playwright/test";

import { setupSession } from "./helpers";

test("chat streams, attaches, and forks", async ({ page, request }) => {
  const sessionId = await setupSession(page, request, "test");
  await page.goto(`/sessions/${sessionId}`);
  await page.waitForLoadState("networkidle");

  await page.getByRole("button", { name: "About" }).click();
  const about = page.getByRole("dialog", { name: "About this session" });
  await expect(about.getByText("python")).toBeVisible();
  await page.keyboard.press("Escape");

  await page.getByLabel("Message").fill("hi");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(
    page.getByText("Hello from the test provider").first(),
  ).toBeVisible({ timeout: 15000 });

  await page.getByLabel("Attach files").setInputFiles({
    name: "note.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("x"),
  });
  await expect(page.getByText("note.txt")).toBeVisible();

  await page.getByRole("button", { name: "Edit" }).first().click();
  await page.getByLabel("Message").fill("edited question");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(
    page.getByText("Hello from the test provider").first(),
  ).toBeVisible({ timeout: 15000 });
});
