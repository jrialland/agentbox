import { expect, test } from "@playwright/test";

test("manage provider and agent end-to-end", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password").fill("admin");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();

  // Provider
  await page.getByRole("link", { name: "Providers" }).click();
  await page.getByLabel("Name").fill("e2e-provider");
  await page.getByRole("combobox", { name: "Kind" }).click();
  await page.getByRole("option", { name: "generic" }).click();
  await page.getByLabel("Models URL").fill("http://localhost:9999/models");
  await page.getByRole("button", { name: "Create provider" }).click();
  await expect(page.getByRole("cell", { name: "e2e-provider" })).toBeVisible();

  await page
    .getByRole("row", { name: /e2e-provider/ })
    .getByRole("button", { name: "Refresh models" })
    .click();

  // Agent
  await page.getByRole("link", { name: "Agents" }).click();
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Name").fill("e2e-agent");
  await page.getByRole("combobox", { name: "Model" }).click();
  await page.getByRole("option", { name: "e2e-model" }).click();
  await page.getByLabel("write_file").check();
  await page.getByRole("button", { name: "Create agent" }).click();
  await expect(page.getByRole("cell", { name: "e2e-agent" })).toBeVisible();

  await page
    .getByRole("row", { name: /e2e-agent/ })
    .getByRole("button", { name: "Delete" })
    .click();
  await expect(page.getByRole("cell", { name: "e2e-agent" })).toHaveCount(0);
});
