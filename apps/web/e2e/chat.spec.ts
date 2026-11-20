import { type APIRequestContext, expect, type Page, test } from "@playwright/test";

const API = "http://localhost:8000";

async function setupChat(page: Page, request: APIRequestContext): Promise<string> {
  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password").fill("admin");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();

  const raw = await page.evaluate(() => sessionStorage.getItem("agentbox-auth"));
  const token = JSON.parse(raw as string).state.token as string;
  const h = { Authorization: `Bearer ${token}` };

  const suffix = Date.now();
  const prov = await request.post(`${API}/providers`, {
    headers: h,
    data: {
      name: `e2e-test-${suffix}`,
      kind: "test",
      models_url: "http://localhost:9999/models",
    },
  });
  const provId = (await prov.json()).id;
  await request.post(`${API}/providers/${provId}/models/refresh`, { headers: h });

  await request.post(`${API}/agents`, {
    headers: h,
    data: {
      name: `e2e-agent-${suffix}`,
      description: "d",
      instructions: "i",
      model: "e2e-model",
      tool_bindings: [],
      mode_definitions: [
        { name: "ask", flags: { write: false } },
        { name: "agent", flags: { write: true } },
      ],
      sub_agent_ids: [],
    },
  });

  const proj = await request.post(`${API}/projects`, {
    headers: h,
    data: { name: `e2e-proj-${suffix}`, path: "." },
  });
  const projId = (await proj.json()).id;
  const sess = await request.post(`${API}/sessions`, {
    headers: h,
    data: { project_id: projId, agent_id: `e2e-agent-${suffix}` },
  });
  return (await sess.json()).id;
}

test("chat streams, attaches, and forks", async ({ page, request }) => {
  const sessionId = await setupChat(page, request);
  await page.goto(`/sessions/${sessionId}`);
  await page.waitForLoadState("networkidle");

  await page.getByRole("button", { name: "About" }).click();
  const about = page.getByRole("dialog", { name: "About this session" });
  await expect(about.getByText("python")).toBeVisible();
  await page.keyboard.press("Escape");

  await page.getByLabel("Message").fill("hi");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("Hello from the test provider")).toBeVisible({ timeout: 15000 });

  await page.getByLabel("Attach files").setInputFiles({
    name: "note.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("x"),
  });
  await expect(page.getByText("note.txt")).toBeVisible();

  await page.getByRole("button", { name: "Edit" }).first().click();
  await page.getByLabel("Message").fill("edited question");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("Hello from the test provider")).toBeVisible({ timeout: 15000 });
});
