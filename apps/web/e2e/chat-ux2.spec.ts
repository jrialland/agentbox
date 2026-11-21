import { type APIRequestContext, expect, type Page, test } from "@playwright/test";

const API = "http://localhost:8000";

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByRole("textbox", { name: "Password" }).fill("admin");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();
  const raw = await page.evaluate(() => sessionStorage.getItem("agentbox-auth"));
  const token = JSON.parse(raw as string).state.token as string;
  return { Authorization: `Bearer ${token}` };
}

async function setupSession(
  page: Page,
  request: APIRequestContext,
  kind: string,
  withMcp = false,
): Promise<string> {
  const h = await login(page);
  const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
  const provider = await request.post(`${API}/providers`, {
    headers: h,
    data: {
      name: `e2e-ux2-${suffix}`,
      kind,
      models_url: "http://localhost:9999/models",
    },
  });
  const providerId = (await provider.json()).id;
  await request.post(`${API}/providers/${providerId}/models/refresh`, {
    headers: h,
  });
  const modelName = `e2e-ux2-model-${suffix}`;
  await request.post(`${API}/models`, {
    headers: h,
    data: { provider_id: providerId, name: modelName, labels: [] },
  });

  const agentName = `e2e-ux2-agent-${suffix}`;
  await request.post(`${API}/agents`, {
    headers: h,
    data: {
      name: agentName,
      description: "d",
      instructions: "i",
      model: modelName,
      tool_bindings: withMcp
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
    data: { name: `e2e-ux2-proj-${suffix}`, path: "." },
  });
  const projectId = (await project.json()).id;
  const session = await request.post(`${API}/sessions`, {
    headers: h,
    data: { project_id: projectId, agent_id: agentName },
  });
  return (await session.json()).id;
}

async function openSession(page: Page, sessionId: string) {
  await page.goto(`/sessions/${sessionId}`);
  await page.waitForLoadState("networkidle");
}

test("renders a live tool card before the final assistant text and splits the app", async ({
  page,
  request,
}) => {
  const sessionId = await setupSession(page, request, "test_tool_slow", true);
  await openSession(page, sessionId);

  await page.getByLabel("Message").fill("show the app");
  await page.getByRole("button", { name: "Send" }).click();

  const live = page.getByTestId("live-turn");
  const tool = live.locator('[data-segment="tool"]').first();
  const text = live.locator('[data-segment="text"]').first();
  await expect(tool).toBeVisible({ timeout: 30000 });
  await expect(text).toContainText("Tool", { timeout: 30000 });
  const toolBox = await tool.boundingBox();
  const textBox = await text.boundingBox();
  expect(toolBox && textBox && toolBox.y).toBeLessThan(textBox?.y ?? 0);

  await expect(page.getByTestId("app-panel")).toBeVisible({ timeout: 30000 });
  await expect(
    page.getByRole("separator", { name: "Resize app panel" }),
  ).toBeVisible();
});

test("stops a slow run, keeps partial output, and offers retry", async ({
  page,
  request,
}) => {
  const sessionId = await setupSession(page, request, "test_slow");
  await openSession(page, sessionId);

  await page.getByLabel("Message").fill("slow please");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("Partial")).toBeVisible({ timeout: 15000 });

  await page.getByRole("button", { name: "Stop" }).first().click();
  await expect(page.getByText("cancelled").first()).toBeVisible({
    timeout: 15000,
  });
  await expect(page.getByRole("button", { name: "Retry" }).first()).toBeVisible();
});

test("shows a per-turn provider error and retries successfully", async ({
  page,
  request,
}) => {
  const sessionId = await setupSession(page, request, "test_flaky");
  await openSession(page, sessionId);

  await page.getByLabel("Message").fill("try once");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByTestId("error-card").first()).toBeVisible({ timeout: 15000 });
  await expect(page.getByText(/provider exploded once/).first()).toBeVisible();

  await page.getByRole("button", { name: "Retry" }).first().click();
  await expect(page.getByText("Recovered answer").last()).toBeVisible({
    timeout: 15000,
  });
});

test("renders markdown, mermaid fallback, and downloadable attachment history", async ({
  page,
  request,
}) => {
  const sessionId = await setupSession(page, request, "test_markdown");
  await openSession(page, sessionId);

  await page.getByLabel("Attach files").setInputFiles({
    name: "note.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("attachment body"),
  });
  await expect(page.getByText("note.txt")).toBeVisible();

  await page.getByLabel("Message").fill("markdown please");
  await page.getByRole("button", { name: "Send" }).click();

  await expect(
    page.getByRole("heading", { name: "Chat UX" }).last(),
  ).toBeVisible({ timeout: 15000 });
  await expect(page.getByRole("table").last()).toBeVisible();
  await expect(page.locator(".md-code").first()).toContainText("print");
  await expect(page.locator(".mermaid-block svg").first()).toBeVisible({
    timeout: 20000,
  });
  await expect(page.getByText("Diagram could not be rendered").last()).toBeVisible();

  await page.reload();
  await page.waitForLoadState("networkidle");
  const chip = page.getByRole("link", { name: /note\.txt/ });
  await expect(chip).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await chip.click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("note.txt");
});






