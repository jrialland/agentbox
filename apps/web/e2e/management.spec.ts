import { expect, test } from "@playwright/test";

test("manage provider and agent end-to-end", async ({ page }) => {
  const suffix = Date.now();
  const providerName = `e2e-provider-${suffix}`;
  const agentName = `e2e-agent-${suffix}`;

  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByRole("textbox", { name: "Password" }).fill("admin");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();

  // Provider
  await page.getByRole("link", { name: "Providers" }).click();
  await page.getByRole("button", { name: "New provider" }).click();
  const providerDialog = page.getByRole("dialog");
  await providerDialog.getByLabel("Name").fill(providerName);
  await providerDialog.getByRole("combobox", { name: "Kind" }).click();
  await page.getByRole("option", { name: "Generic OpenAI-compatible" }).click();
  await providerDialog.getByLabel("Models URL").fill("http://localhost:9999/models");
  await providerDialog.getByRole("button", { name: "Create provider" }).click();
  await expect(page.getByRole("cell", { name: providerName })).toBeVisible();

  await page
    .getByRole("row", { name: new RegExp(providerName) })
    .getByRole("button", { name: "Refresh models" })
    .click();

  // Agent
  await page.getByRole("link", { name: "Agents" }).click();
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: "New agent" }).click();
  const agentDialog = page.getByRole("dialog");
  await agentDialog.getByLabel(/^Name/).fill(agentName);
  await agentDialog.getByRole("combobox", { name: "Model" }).click();
  await page.getByRole("option", { name: new RegExp(providerName) }).click();
  await agentDialog.getByLabel("write_file").check();
  await agentDialog.getByRole("button", { name: "Create agent" }).click();
  await expect(
    page.getByRole("row", { name: new RegExp(agentName) }),
  ).toBeVisible();

  await page
    .getByRole("row", { name: new RegExp(agentName) })
    .getByRole("button", { name: "Delete" })
    .click();
  const deleteDialog = page.getByRole("dialog");
  await deleteDialog
    .getByLabel(`Type ${agentName} to confirm`)
    .fill(agentName);
  await deleteDialog
    .getByRole("button", { name: "Delete", exact: true })
    .click();
  await expect(page.getByRole("cell", { name: agentName })).toHaveCount(0);
});
