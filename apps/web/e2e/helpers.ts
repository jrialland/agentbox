import { type APIRequestContext, expect, type Page } from "@playwright/test";

export const API = "http://localhost:8000";

export async function login(page: Page): Promise<{ Authorization: string }> {
  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByRole("textbox", { name: "Password" }).fill("admin");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();
  const raw = await page.evaluate(() => sessionStorage.getItem("agentbox-auth"));
  const token = JSON.parse(raw as string).state.token as string;
  return { Authorization: `Bearer ${token}` };
}

export async function setupSession(
  page: Page,
  request: APIRequestContext,
  kind: string,
  options: { withMcp?: boolean; prefix?: string } = {},
): Promise<string> {
  const h = await login(page);
  const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
  const prefix = options.prefix ?? "e2e";
  const provider = await request.post(`${API}/providers`, {
    headers: h,
    data: {
      name: `${prefix}-${suffix}`,
      kind,
      models_url: "http://localhost:9999/models",
    },
  });
  const providerId = (await provider.json()).id;
  await request.post(`${API}/providers/${providerId}/models/refresh`, {
    headers: h,
  });
  const modelName = `${prefix}-model-${suffix}`;
  await request.post(`${API}/models`, {
    headers: h,
    data: { provider_id: providerId, name: modelName, labels: [] },
  });
  const agentName = `${prefix}-agent-${suffix}`;
  await request.post(`${API}/agents`, {
    headers: h,
    data: {
      name: agentName,
      description: "d",
      instructions: "i",
      model: modelName,
      tool_bindings: options.withMcp
        ? [{ server_url: "http://localhost:9000/mcp", id: "test-app" }]
        : [],
      mode_definitions: [
        { name: "ask", flags: { write: false } },
        { name: "agent", flags: { write: true } },
      ],
      sub_agent_ids: [],
    },
  });
  const project = await request.post(`${API}/projects`, {
    headers: h,
    data: { name: `${prefix}-proj-${suffix}`, path: "." },
  });
  const projectId = (await project.json()).id;
  const session = await request.post(`${API}/sessions`, {
    headers: h,
    data: { project_id: projectId, agent_id: agentName },
  });
  return (await session.json()).id;
}
