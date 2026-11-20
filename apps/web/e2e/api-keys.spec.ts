import { expect, test } from "@playwright/test";

const API = "http://localhost:8000";

test("API key: scope-limited, then revoked", async ({ page, request }) => {
  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByRole("textbox", { name: "Password" }).fill("admin");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();

  await page.getByRole("link", { name: "API keys" }).click();

  // Create a key scoped to projects:read for 7 days.
  await page.locator(".mantine-MultiSelect-input").click();
  await page.getByRole("option", { name: "projects:read" }).click();
  await expect(
    page.locator(".mantine-MultiSelect-pill", { hasText: "projects:read" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await page.locator(".mantine-Select-input").click();
  await page.getByRole("option", { name: "7 days" }).click();
  await page.getByRole("button", { name: "Create key" }).click();

  const raw = await page.getByTestId("created-key").inputValue();
  expect(raw.length).toBeGreaterThan(10);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();

  const keyH = { Authorization: `Bearer ${raw}` };
  expect((await request.get(`${API}/projects`, { headers: keyH })).status()).toBe(200);
  expect(
    (
      await request.post(`${API}/agents`, {
        headers: keyH,
        data: { name: "x", model: "test-model" },
      })
    ).status(),
  ).toBe(403);

  // Revoke via the UI, then the key is rejected.
  await page.getByRole("button", { name: "Revoke" }).first().click();
  await expect(page.getByRole("cell", { name: "revoked" }).first()).toBeVisible();
  expect((await request.get(`${API}/projects`, { headers: keyH })).status()).toBe(401);
});

