import { expect, test } from "@playwright/test";

const API = "http://localhost:8000";

test("A2A agent card editor", async ({ page, request }) => {
  const suffix = Date.now();
  const agentName = `e2e-a2a-agent-${suffix}`;

  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password").fill("admin");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();

  const raw = await page.evaluate(() => sessionStorage.getItem("agentbox-auth"));
  const token = JSON.parse(raw as string).state.token as string;
  const h = { Authorization: `Bearer ${token}` };
  const prov = await request.post(`${API}/providers`, {
    headers: h,
    data: { name: `e2e-a2a-${suffix}`, kind: "test", models_url: "http://localhost:9999/models" },
  });
  const provId = (await prov.json()).id;
  await request.post(`${API}/providers/${provId}/models/refresh`, { headers: h });
  await request.post(`${API}/agents`, {
    headers: h,
    data: { name: agentName, model: "e2e-model", tool_bindings: [] },
  });

  await page.goto("/agents");
  await page.waitForLoadState("networkidle");
  const row = page.getByRole("row", { name: new RegExp(agentName) });
  await row.getByRole("button", { name: "A2A" }).click();

  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Agent card (JSON)").fill(
    JSON.stringify(
      { name: "E2E A2A", description: "d", version: "1.0.0", skills: [] },
      null,
      2,
    ),
  );
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("dialog")).toBeHidden();

  await row.getByRole("button", { name: "A2A" }).click();
  await expect(
    page.getByRole("dialog").getByLabel("Agent card (JSON)"),
  ).toHaveValue(/E2E A2A/);
});
