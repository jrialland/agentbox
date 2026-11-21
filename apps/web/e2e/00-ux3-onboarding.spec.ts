import { expect, test } from "@playwright/test";

test.use({ storageState: { cookies: [], origins: [] } });

test("first-run wizard tests a provider and completes setup", async ({ page }) => {
  const suffix = Date.now();
  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByRole("textbox", { name: "Password" }).fill("admin");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();

  const wizard = page.getByRole("dialog", { name: "Set up Agentbox" });
  await expect(wizard).toBeVisible();
  await wizard.getByRole("button", { name: "Get started" }).click();

  await wizard.getByLabel("Name").fill(`e2e-ux3-provider-${suffix}`);
  await wizard.getByLabel("Models URL").fill("not-a-url");
  await wizard.getByRole("button", { name: "Test connection" }).click();
  await expect(wizard.getByText(/http\/https/i)).toBeVisible();

  await wizard.getByLabel("Models URL").fill("http://localhost:9999/models");
  await wizard.getByRole("button", { name: "Test connection" }).click();
  await expect(wizard.getByText(/Connected —/)).toBeVisible({ timeout: 15000 });
  await wizard.getByRole("button", { name: "Create provider" }).click();

  await wizard.getByLabel("Agent name").fill(`e2e-ux3-agent-${suffix}`);
  await wizard.getByLabel("Model").click();
  await page.getByRole("option", { name: /e2e-model/ }).click();
  await wizard.getByRole("button", { name: "Create agent" }).click();

  await wizard.getByLabel("Project name").fill(`e2e-ux3-project-${suffix}`);
  await wizard.getByLabel("Project path").fill(".");
  await wizard.getByRole("button", { name: "Create project and start session" }).click();

  await expect(page).toHaveURL(/\/sessions\//, { timeout: 15000 });
  await expect(page.getByTestId("composer")).toBeVisible();
  await page.goto("/");
  await expect(page.getByText("4 of 4 complete")).toBeVisible();
});
