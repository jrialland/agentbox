import { expect, test } from "@playwright/test";

const API = "http://localhost:8000";

test("admin grants a non-admin user a permission", async ({ page, request }) => {
  const suffix = Date.now();
  const roleName = `e2e-role-${suffix}`;
  const userName = `e2e-user-${suffix}`;
  const probe = `e2e:probe-${suffix}`;

  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByRole("textbox", { name: "Password" }).fill("admin");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();

  await page.getByRole("link", { name: "Admin" }).click();

  // Permissions tab: create a probe permission (projects:read is pre-seeded by dev_seed)
  await page.getByRole("tab", { name: "Permissions" }).click();
  await page.getByLabel("Permission name").fill(probe);
  await page.getByRole("button", { name: "Create permission" }).click();
  await expect(page.getByText(probe)).toBeVisible();

  // Roles tab: create a role and grant it the pre-seeded projects:read permission
  await page.getByRole("tab", { name: "Roles" }).click();
  await page.getByLabel("Role name").fill(roleName);
  await page.getByRole("button", { name: "Create role" }).click();
  const roleRow = page.getByRole("row", { name: new RegExp(roleName) });
  await expect(roleRow).toBeVisible();
  await roleRow.getByRole("button", { name: "Permissions" }).click();
  await page.getByRole("dialog").locator(".mantine-MultiSelect-input").click();
  await page.getByRole("option", { name: "projects:read" }).click();
  await expect(
    page
      .getByRole("dialog")
      .locator(".mantine-MultiSelect-pill", { hasText: "projects:read" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("dialog")).toBeHidden();

  // Users tab: create a user and assign the role
  await page.getByRole("tab", { name: "Users" }).click();
  await page.getByLabel("Username").fill(userName);
  await page.getByLabel("Email").fill(`${userName}@x`);
  await page.getByLabel("Password", { exact: true }).fill("pw");
  await page.getByRole("button", { name: "Create user" }).click();
  const userRow = page.getByRole("row", { name: new RegExp(userName) });
  await expect(userRow).toBeVisible();
  await userRow.getByRole("button", { name: "Roles" }).click();
  await page.getByRole("dialog").locator(".mantine-MultiSelect-input").click();
  await page.getByRole("option", { name: roleName }).click();
  await expect(
    page.getByRole("dialog").locator(".mantine-MultiSelect-pill", { hasText: roleName }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("dialog")).toBeHidden();

  // The non-admin user can read projects but cannot create agents.
  const login = await request.post(`${API}/auth/login`, {
    data: { username: userName, password: "pw" },
  });
  const token = (await login.json()).access_token;
  const h = { Authorization: `Bearer ${token}` };
  expect((await request.get(`${API}/projects`, { headers: h })).status()).toBe(200);
  const denied = await request.post(`${API}/agents`, {
    headers: h,
    data: { name: "x", model: "test-model" },
  });
  expect(denied.status()).toBe(403);
});

