import { expect, type APIRequestContext, type Page, test } from "@playwright/test";

import { login } from "./helpers";

const API = "http://localhost:8000";

async function createSessionFixture(page: Page, request: APIRequestContext) {
  const token = await page.evaluate(() => {
    const raw = sessionStorage.getItem("agentbox-auth");
    return JSON.parse(raw as string).state.token as string;
  });
  const headers = { Authorization: `Bearer ${token}` };
  const suffix = Date.now();
  const project = await request.post(`${API}/projects`, {
    headers,
    data: { name: `e2e-ux4-project-${suffix}`, path: "." },
  });
  const projectBody = await project.json();
  const provider = await request.post(`${API}/providers`, {
    headers,
    data: {
      name: `e2e-ux4-provider-${suffix}`,
      kind: "test",
      models_url: "http://localhost:9999/models",
    },
  });
  const providerBody = await provider.json();
  await request.post(`${API}/providers/${providerBody.id}/models/refresh`, {
    headers,
  });
  const agent = await request.post(`${API}/agents`, {
    headers,
    data: {
      name: `e2e-ux4-agent-${suffix}`,
      model: "e2e-model",
      tool_bindings: [],
    },
  });
  const agentBody = await agent.json();
  const session = await request.post(`${API}/sessions`, {
    headers,
    data: { project_id: projectBody.id, agent_id: agentBody.name },
  });
  const sessionBody = await session.json();
  return { projectName: projectBody.name, sessionId: sessionBody.id };
}

async function createChatFixture(page: Page, request: APIRequestContext) {
  const token = await page.evaluate(() => {
    const raw = sessionStorage.getItem("agentbox-auth");
    return JSON.parse(raw as string).state.token as string;
  });
  const headers = { Authorization: `Bearer ${token}` };
  const suffix = Date.now();
  const projectName = `e2e-ux4-chat-project-${suffix}`;
  const project = await request.post(`${API}/projects`, {
    headers,
    data: { name: projectName, path: "." },
  });
  const projectBody = await project.json();
  const provider = await request.post(`${API}/providers`, {
    headers,
    data: {
      name: `e2e-ux4-chat-provider-${suffix}`,
      kind: "test",
      models_url: "http://localhost:9999/models",
    },
  });
  const providerBody = await provider.json();
  await request.post(`${API}/providers/${providerBody.id}/models/refresh`, {
    headers,
  });
  const modelName = `e2e-chat-model-${suffix}`;
  await request.post(`${API}/models`, {
    headers,
    data: { provider_id: providerBody.id, name: modelName, labels: [] },
  });
  const agentName = `e2e-ux4-chat-agent-${suffix}`;
  await request.post(`${API}/agents`, {
    headers,
    data: {
      name: agentName,
      description: "e2e",
      instructions: "e2e",
      model: modelName,
      tool_bindings: [],
      mode_definitions: [
        { name: "ask", flags: { write: false } },
        { name: "agent", flags: { write: true } },
      ],
      sub_agent_ids: [],
    },
  });
  const session = await request.post(`${API}/sessions`, {
    headers,
    data: { project_id: projectBody.id, agent_id: agentName },
  });
  const sessionBody = await session.json();
  return {
    headers,
    projectName,
    agentName,
    sessionId: sessionBody.id as string,
  };
}

test("keeps active navigation on a direct route", async ({ page }) => {
  await login(page);
  await page.goto("/providers");
  await expect(
    page.getByRole("link", { name: "Providers" }),
  ).toHaveAttribute("aria-current", "page");
});

test("keeps active navigation after navigating", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Providers" }).click();
  await expect(
    page.getByRole("link", { name: "Providers" }),
  ).toHaveAttribute("aria-current", "page");
  await page.getByRole("link", { name: "Agents" }).click();
  await expect(
    page.getByRole("link", { name: "Agents" }),
  ).toHaveAttribute("aria-current", "page");
});

test("shows 404 and session-not-found states", async ({ page }) => {
  await login(page);
  await page.goto("/missing-route");
  await expect(
    page.getByRole("heading", { name: /page not found/i }),
  ).toBeVisible();
  await page.goto("/sessions/deadbeef");
  await expect(
    page.getByRole("heading", { name: /session not found/i }),
  ).toBeVisible();
  await expect(page.getByLabel("Message")).toHaveCount(0);
});

test("shows a retryable list error", async ({ page }) => {
  let calls = 0;
  await page.route("**/api/projects", async (route) => {
    calls += 1;
    // The query client retries a 5xx once, so exhaust both attempts first.
    if (calls <= 2) {
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "database unavailable" }),
      });
    } else {
      await route.continue();
    }
  });
  await login(page);
  const errorText = page.getByText("Could not load projects").first();
  await expect(errorText).toBeVisible();
  await page.getByRole("button", { name: "Retry" }).first().click();
  await expect(errorText).toBeHidden();
});

test("blocks blank project submission", async ({ page }) => {
  await login(page);
  await page.getByRole("button", { name: "New project" }).first().click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Create", exact: true })
    .click();
  await expect(page.getByText("Name is required.")).toBeVisible();
  await expect(page.getByText("Path is required.")).toBeVisible();
});

test("blocks blank provider submission", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Providers" }).click();
  await page.getByRole("button", { name: "New provider" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Create provider" }).click();
  await expect(dialog.getByText("Name is required.")).toBeVisible();
});

test("blocks blank agent submission", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Agents" }).click();
  await page.getByRole("button", { name: "New agent" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Create agent" }).click();
  await expect(dialog.getByText("Name is required.")).toBeVisible();
  await expect(dialog.getByText("Choose a model.")).toBeVisible();
});

test("blocks an empty session submission", async ({ page, request }) => {
  await login(page);
  const token = await page.evaluate(() => {
    const raw = sessionStorage.getItem("agentbox-auth");
    return JSON.parse(raw as string).state.token as string;
  });
  const project = await request.post(`${API}/projects`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { name: `e2e-ux4-empty-session-${Date.now()}`, path: "." },
  });
  const projectName = (await project.json()).name;
  await page.goto("/");
  await page.getByLabel(`New session in ${projectName}`).click();
  const dialog = page.getByRole("dialog");
  await expect(
    dialog.getByRole("button", { name: "Create", exact: true }),
  ).toBeDisabled();
  await expect(
    dialog.getByText("Choose an agent to create a session."),
  ).toBeVisible();
});

test("requires a typed project confirmation and removes its sessions", async ({
  page,
  request,
}) => {
  await login(page);
  const { headers, projectName, sessionId } = await createChatFixture(
    page,
    request,
  );
  const title = `deleted project session ${Date.now()}`;
  await request.patch(`${API}/sessions/${sessionId}`, {
    headers,
    data: { title },
  });

  await page.goto("/");
  await expect(page.getByText(projectName).first()).toBeVisible();
  await expect(page.getByText(title).first()).toBeVisible();

  await page.getByLabel(`Delete ${projectName}`).click();
  const confirm = page
    .getByRole("dialog")
    .getByRole("button", { name: "Delete", exact: true });
  await expect(confirm).toBeDisabled();
  await page.getByLabel(`Type ${projectName} to confirm`).fill(projectName);
  await expect(confirm).toBeEnabled();
  await confirm.click();

  await expect(page.getByText(projectName).first()).toBeHidden();
  await expect(page.getByText(title).first()).toBeHidden();
});

test("uses a standard session confirmation", async ({ page, request }) => {
  await login(page);
  const { sessionId } = await createSessionFixture(page, request);
  await page.goto("/");
  const deleteButton = page.getByLabel(`Delete session ${sessionId}`);
  await deleteButton.click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Delete", exact: true })
    .click();
  await expect(deleteButton).toHaveCount(0);
});

test("renames a session title", async ({ page, request }) => {
  await login(page);
  const { sessionId } = await createSessionFixture(page, request);
  await page.goto(`/sessions/${sessionId}`);
  await page.getByRole("button", { name: "Rename", exact: true }).click();
  await page.getByLabel("Session title").fill("Release plan");
  await page.getByRole("button", { name: "Save title" }).click();
  await expect(
    page.getByRole("heading", { name: "Release plan" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Release plan" }),
  ).toBeVisible();
  await page.goto("/");
  await expect(page.getByText("Release plan").first()).toBeVisible();
});

test("auto-titles a session from the first message", async ({
  page,
  request,
}) => {
  await login(page);
  const { sessionId } = await createChatFixture(page, request);
  await page.goto(`/sessions/${sessionId}`);
  await page.waitForLoadState("networkidle");

  await page.getByLabel("Message").fill("Plan the release");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(
    page.getByText("Hello from the test provider").first(),
  ).toBeVisible({ timeout: 15000 });

  await expect(
    page.getByRole("heading", { name: "Plan the release" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Plan the release" }),
  ).toBeVisible();
});
