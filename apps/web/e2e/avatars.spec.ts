import { type APIRequestContext, expect, type Page, test } from "@playwright/test";

const API = "http://localhost:8000";
const TINY_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC",
  "base64",
);

async function setup(page: Page, request: APIRequestContext) {
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
      name: `e2e-av-${suffix}`,
      kind: "test",
      models_url: "http://localhost:9999/models",
    },
  });
  const provId = (await prov.json()).id;
  await request.post(`${API}/providers/${provId}/models/refresh`, { headers: h });

  const agentName = `e2e-av-agent-${suffix}`;
  await request.post(`${API}/agents`, {
    headers: h,
    data: {
      name: agentName,
      description: "d",
      instructions: "i",
      model: "e2e-model",
      tool_bindings: [],
      mode_definitions: [],
      sub_agent_ids: [],
    },
  });

  const proj = await request.post(`${API}/projects`, {
    headers: h,
    data: { name: `e2e-av-proj-${suffix}`, path: "." },
  });
  const projId = (await proj.json()).id;
  const sess = await request.post(`${API}/sessions`, {
    headers: h,
    data: { project_id: projId, agent_id: agentName },
  });
  return { agentName, sessionId: (await sess.json()).id };
}

test("agent avatars: default, upload, reset, chat header", async ({ page, request }) => {
  const { agentName, sessionId } = await setup(page, request);

  await page.goto("/agents");
  await page.waitForLoadState("networkidle");
  const row = page.getByRole("row", { name: new RegExp(agentName) });
  const img = row.locator("img");
  await expect(img).toBeVisible();
  await expect(img).toHaveAttribute("src", /v=0/);

  await row
    .getByLabel(`Change photo ${agentName}`)
    .setInputFiles({ name: "a.png", mimeType: "image/png", buffer: TINY_PNG });
  await expect(row.locator("img")).toHaveAttribute("src", /v=1/);

  await row.getByRole("button", { name: "Remove photo" }).click();
  await expect(row.locator("img")).toHaveAttribute("src", /v=2/);

  await page.goto(`/sessions/${sessionId}`);
  await page.waitForLoadState("networkidle");
  await expect(page.getByTestId("session-agent")).toContainText(agentName);
  await expect(
    page.getByTestId("session-agent").getByRole("img", { name: agentName }),
  ).toBeVisible();
});
