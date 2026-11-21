import { expect, test } from "@playwright/test";

import { setupSession } from "./helpers";

async function bottomGap(page: import("@playwright/test").Page) {
  return page
    .getByTestId("messages")
    .evaluate((el) => el.scrollHeight - el.scrollTop - el.clientHeight);
}

test("session is viewport-bound with a pinned composer and follows a long stream", async ({
  page,
  request,
}) => {
  const sessionId = await setupSession(page, request, "test_long");
  await page.goto(`/sessions/${sessionId}`);
  await page.waitForLoadState("networkidle");

  const viewport = page.viewportSize();
  expect(viewport).not.toBeNull();
  const composer = page.getByTestId("composer");
  await expect(composer).toBeVisible();
  const initial = await composer.boundingBox();
  expect(initial).not.toBeNull();
  expect(initial!.y).toBeGreaterThan(viewport!.height * 0.6);
  expect(initial!.y + initial!.height).toBeLessThanOrEqual(viewport!.height + 1);

  const messages = page.getByTestId("messages");
  expect(
    await messages.evaluate((el) => getComputedStyle(el).overflowY),
  ).toBe("auto");

  await page.getByLabel("Message").fill("long please");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(
    page.getByRole("heading", { name: "Long fixture" }).last(),
  ).toBeVisible({ timeout: 20000 });

  await expect
    .poll(() =>
      messages.evaluate((el) => el.scrollHeight - el.clientHeight),
    )
    .toBeGreaterThan(0);
  await expect.poll(() => bottomGap(page)).toBeLessThanOrEqual(64);

  const afterComposer = await composer.boundingBox();
  expect(afterComposer!.y + afterComposer!.height).toBeLessThanOrEqual(
    viewport!.height + 1,
  );
});

test("jump to latest appears after scrolling up and returns to the bottom", async ({
  page,
  request,
}) => {
  const sessionId = await setupSession(page, request, "test_long");
  await page.goto(`/sessions/${sessionId}`);
  await page.waitForLoadState("networkidle");

  await page.getByLabel("Message").fill("long please");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(
    page.getByRole("heading", { name: "Long fixture" }).last(),
  ).toBeVisible({ timeout: 20000 });
  await expect
    .poll(() =>
      page
        .getByTestId("messages")
        .evaluate((el) => el.scrollHeight - el.clientHeight),
    )
    .toBeGreaterThan(0);

  await page.getByTestId("messages").evaluate((el) => {
    el.scrollTop = 0;
    el.dispatchEvent(new Event("scroll"));
  });
  const jump = page.getByRole("button", { name: "Jump to latest" });
  await expect(jump).toBeVisible();
  await jump.click();
  await expect.poll(() => bottomGap(page)).toBeLessThanOrEqual(64);
});

test("a follow-up question stays with its answer", async ({ page, request }) => {
  const sessionId = await setupSession(page, request, "test");
  await page.goto(`/sessions/${sessionId}`);
  await page.waitForLoadState("networkidle");

  await page.getByLabel("Message").fill("first question");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(
    page.getByText("Hello from the test provider").last(),
  ).toBeVisible({ timeout: 15000 });

  await page.getByLabel("Message").fill("second question");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.locator('article[data-role="user"]')).toHaveCount(2, {
    timeout: 20000,
  });
  await expect(page.locator('article[data-role="assistant"]')).toHaveCount(2, {
    timeout: 20000,
  });
  await expect.poll(() => bottomGap(page)).toBeLessThanOrEqual(64);

  const messages = page.getByTestId("messages");
  const messagesBox = await messages.boundingBox();
  const lastUser = page.locator('article[data-role="user"]').last();
  const lastAssistant = page.locator('article[data-role="assistant"]').last();
  const userBox = await lastUser.boundingBox();
  const assistantBox = await lastAssistant.boundingBox();
  expect(messagesBox).not.toBeNull();
  expect(userBox).not.toBeNull();
  expect(assistantBox).not.toBeNull();
  expect(userBox!.y).toBeLessThan(assistantBox!.y);
  expect(userBox!.y).toBeGreaterThanOrEqual(messagesBox!.y - 1);
  expect(userBox!.y + userBox!.height).toBeLessThanOrEqual(
    messagesBox!.y + messagesBox!.height + 1,
  );
  expect(assistantBox!.y + assistantBox!.height).toBeLessThanOrEqual(
    messagesBox!.y + messagesBox!.height + 1,
  );

  const viewport = page.viewportSize();
  const composer = page.getByTestId("composer");
  const composerBox = await composer.boundingBox();
  expect(viewport).not.toBeNull();
  expect(composerBox).not.toBeNull();
  expect(composerBox!.y + composerBox!.height).toBeLessThanOrEqual(
    viewport!.height + 1,
  );
});

test("mobile session pins the composer and scrolls messages", async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const sessionId = await setupSession(page, request, "test_long");
  await page.goto(`/sessions/${sessionId}`);
  await page.waitForLoadState("networkidle");

  const composer = page.getByTestId("composer");
  await expect(composer).toBeVisible();
  const initial = await composer.boundingBox();
  expect(initial).not.toBeNull();
  expect(initial!.y + initial!.height).toBeLessThanOrEqual(845);
  expect(initial!.y).toBeGreaterThan(844 * 0.5);

  await page.getByLabel("Message").fill("long please");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(
    page.getByRole("heading", { name: "Long fixture" }).last(),
  ).toBeVisible({ timeout: 20000 });
  await expect
    .poll(() =>
      page
        .getByTestId("messages")
        .evaluate((el) => el.scrollHeight - el.clientHeight),
    )
    .toBeGreaterThan(0);
  await expect.poll(() => bottomGap(page)).toBeLessThanOrEqual(64);

  const after = await composer.boundingBox();
  expect(after!.y + after!.height).toBeLessThanOrEqual(845);
});
