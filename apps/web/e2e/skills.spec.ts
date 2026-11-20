import { expect, test } from "@playwright/test";

const API = "http://localhost:8000";

test("skills page + slash activation", async ({ page, request }) => {
  const suffix = Date.now();
  const skillName = `e2e-skill-${suffix}`;
  const agentName = `e2e-sk-agent-${suffix}`;

  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByRole("textbox", { name: "Password" }).fill("admin");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();

  const raw = await page.evaluate(() => sessionStorage.getItem("agentbox-auth"));
  const token = JSON.parse(raw as string).state.token as string;
  const h = { Authorization: `Bearer ${token}` };
  const prov = await request.post(`${API}/providers`, {
    headers: h,
    data: { name: `e2e-sk-${suffix}`, kind: "test", models_url: "http://localhost:9999/models" },
  });
  const provId = (await prov.json()).id;
  await request.post(`${API}/providers/${provId}/models/refresh`, { headers: h });
  await request.post(`${API}/agents`, {
    headers: h,
    data: { name: agentName, model: "e2e-model", tool_bindings: [] },
  });
  const proj = await request.post(`${API}/projects`, {
    headers: h,
    data: { name: `e2e-sk-proj-${suffix}`, path: "." },
  });
  const sess = await request.post(`${API}/sessions`, {
    headers: h,
    data: { project_id: (await proj.json()).id, agent_id: agentName },
  });
  const sessionId = (await sess.json()).id;

  await page.getByRole("link", { name: "Skills" }).click();
  await page.getByLabel("Name").fill(skillName);
  await page.getByLabel("Description").fill("d");
  await page.getByLabel("Body (Markdown)").fill("# Demo\nbody");
  await page.getByRole("button", { name: "Create skill" }).click();
  await expect(page.getByRole("cell", { name: skillName })).toBeVisible();

  await page.goto(`/sessions/${sessionId}`);
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Message").fill(`/${skillName}`);
  const menu = page.getByTestId("skill-menu");
  await expect(menu).toBeVisible();
  await menu.getByRole("button", { name: new RegExp(skillName) }).click();
  await expect(page.getByLabel("Message")).toHaveValue(`/${skillName} `);
});

