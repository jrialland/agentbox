import { type APIRequestContext, expect, type Page, test } from "@playwright/test";

const API = "http://localhost:8000";

async function setupAppSession(
  page: Page,
  request: APIRequestContext,
): Promise<string> {
  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByRole("textbox", { name: "Password" }).fill("admin");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();

  const raw = await page.evaluate(() => sessionStorage.getItem("agentbox-auth"));
  const token = JSON.parse(raw as string).state.token as string;
  const h = { Authorization: `Bearer ${token}` };

  const suffix = Date.now();
  const prov = await request.post(`${API}/providers`, {
    headers: h,
    data: {
      name: `e2e-app-${suffix}`,
      kind: "test_tool",
      models_url: "http://localhost:9999/models",
    },
  });
  const provId = (await prov.json()).id;
  await request.post(`${API}/providers/${provId}/models/refresh`, { headers: h });
  const modelName = `e2e-app-model-${suffix}`;
  await request.post(`${API}/models`, {
    headers: h,
    data: { provider_id: provId, name: modelName, labels: [] },
  });

  const agentName = `e2e-app-agent-${suffix}`;
  await request.post(`${API}/agents`, {
    headers: h,
    data: {
      name: agentName,
      description: "d",
      instructions: "i",
      model: modelName,
      tool_bindings: [{ server_url: "http://localhost:9000/mcp", id: "test-app" }],
      mode_definitions: [
        { name: "ask", flags: { write: false } },
        { name: "agent", flags: { write: true } },
      ],
      sub_agent_ids: [],
    },
  });

  const proj = await request.post(`${API}/projects`, {
    headers: h,
    data: { name: `e2e-app-proj-${suffix}`, path: "." },
  });
  const projId = (await proj.json()).id;
  const sess = await request.post(`${API}/sessions`, {
    headers: h,
    data: { project_id: projId, agent_id: agentName },
  });
  return (await sess.json()).id;
}

test("opens a right-side MCP App tab and renders it", async ({ page, request }) => {
  const sessionId = await setupAppSession(page, request);
  await page.goto(`/sessions/${sessionId}`);
  await page.waitForLoadState("networkidle");

  await page.getByLabel("Message").fill("show the app");
  await page.getByRole("button", { name: "Send" }).click();

  const panel = page.getByTestId("app-panel");
  await expect(panel).toBeVisible({ timeout: 30000 });
  await expect(panel.getByRole("tab", { name: /App 1/ })).toBeVisible();
  await expect(panel.locator("iframe").first()).toBeVisible({ timeout: 30000 });

  const app = panel.frameLocator("iframe").first().frameLocator("iframe");
  await expect(app.getByText("Hello MCP App")).toBeVisible({ timeout: 30000 });
});


