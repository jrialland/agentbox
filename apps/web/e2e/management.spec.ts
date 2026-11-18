import { expect, test } from "@playwright/test";

test("manage provider and agent end-to-end", async ({ page }) => {
  const suffix = Date.now();
  const providerName = `e2e-provider-${suffix}`;
  const agentName = `e2e-agent-${suffix}`;

  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password").fill("admin");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();

  // Provider
  await page.getByRole("link", { name: "Providers" }).click();
  await page.getByLabel("Name").fill(providerName);
  await page.getByRole("combobox", { name: "Kind" }).click();
  await page.getByRole("option", { name: "generic" }).click();
  await page.getByLabel("Models URL").fill("http://localhost:9999/models");
  await page.getByRole("button", { name: "Create provider" }).click();
  await expect(page.getByRole("cell", { name: providerName })).toBeVisible();

  await page
    .getByRole("row", { name: new RegExp(providerName) })
    .getByRole("button", { name: "Refresh models" })
    .click();

  // Agent
  await page.getByRole("link", { name: "Agents" }).click();
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Name").fill(agentName);
  await page.getByRole("combobox", { name: "Model" }).click();
  await page.getByRole("option", { name: "e2e-model" }).click();
  await page.getByLabel("write_file").check();
  await page.getByRole("button", { name: "Create agent" }).click();
  await expect(page.getByRole("cell", { name: agentName })).toBeVisible();

  await page
    .getByRole("row", { name: new RegExp(agentName) })
    .getByRole("button", { name: "Delete" })
    .click();
  await expect(page.getByRole("cell", { name: agentName })).toHaveCount(0);
});
