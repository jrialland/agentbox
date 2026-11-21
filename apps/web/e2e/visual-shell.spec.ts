import { expect, test } from "@playwright/test";

const pages = [
  ["home", "/"],
  ["agents", "/agents"],
  ["providers", "/providers"],
  ["admin", "/admin"],
  ["api-keys", "/api-keys"],
  ["skills", "/skills"],
] as const;

test("login renders without overflow at all breakpoints", async ({ page }) => {
  await page.goto("/login");
  for (const width of [390, 1280, 1920]) {
    await page.setViewportSize({ width, height: 844 });
    const overflow = await page.evaluate(
      () =>
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
    await expect(page).toHaveScreenshot(`login-${width}.png`, {
      fullPage: true,
    });
  }
});

test("authenticated pages avoid horizontal overflow", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByRole("textbox", { name: "Password" }).fill("admin");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();

  for (const width of [390, 1280, 1920]) {
    await page.setViewportSize({ width, height: 844 });
    for (const [, path] of pages) {
      await page.goto(path);
      const overflow = await page.evaluate(
        () =>
          document.documentElement.scrollWidth -
          document.documentElement.clientWidth,
      );
      expect(overflow).toBeLessThanOrEqual(1);
    }
  }
});

test("mobile navigation exposes every destination", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByRole("textbox", { name: "Password" }).fill("admin");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();

  const nav = page.getByRole("navigation", { name: "Primary navigation" });
  for (const name of [
    "Home",
    "Agents",
    "Providers",
    "Skills",
    "API keys",
    "Admin",
  ]) {
    await expect(nav.getByRole("link", { name })).toBeVisible();
  }
  expect(
    await nav.evaluate((el) => el.scrollWidth - el.clientWidth),
  ).toBeLessThanOrEqual(1);
});
