import { expect, test } from "@playwright/test";

const API = "http://localhost:8000";

test("manage providers/models and delete a session", async ({ page, request }) => {
  const suffix = Date.now();
  const provName = `e2e-prov-${suffix}`;
  const editedName = `e2e-prov-edit-${suffix}`;
  const extraModel = `e2e-extra-${suffix}`;
  const labelModel = `e2e-labelled-${suffix}`;
  const labelAgent = `e2e-label-ag-${suffix}`;
  const agentName = `e2e-ag-${suffix}`;

  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password").fill("admin");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();

  await page.getByRole("link", { name: "Providers" }).click();
  await page.getByLabel("Name").fill(provName);
  await page.getByLabel("Models URL").fill("http://localhost:9999/models");
  await page.getByRole("button", { name: "Create provider" }).click();
  await expect(page.getByRole("cell", { name: provName })).toBeVisible();

  const row = page.getByRole("row", { name: new RegExp(provName) });
  await row.getByRole("button", { name: "Refresh models" }).click();

  // Edit provider name.
  await row.getByRole("button", { name: "Edit" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Name").fill(editedName);
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("cell", { name: editedName })).toBeVisible();

  // Models tab: add + delete a throwaway model.
  await page.getByRole("tab", { name: "Models" }).click();
  await expect(page.getByLabel("Model name")).toBeVisible();
  await page.getByRole("combobox", { name: "Provider" }).click();
  await page.getByRole("option", { name: editedName }).click();
  await page.getByLabel("Model name").fill(extraModel);
  await page.getByRole("button", { name: "Create model" }).click();
  const modelRow = page.getByRole("row", { name: new RegExp(extraModel) });
  await expect(modelRow).toBeVisible();
  await modelRow.getByRole("button", { name: "Delete" }).click();
  await expect(page.getByRole("cell", { name: extraModel })).toHaveCount(0);

  // Labels: create a model, tag it, filter, then create a label-bound agent.
  await page.getByLabel("Model name").fill(labelModel);
  await page.getByRole("button", { name: "Create model" }).click();
  const labelledRow = page.getByRole("row", { name: new RegExp(labelModel) });
  await expect(labelledRow).toBeVisible();

  await labelledRow.getByRole("button", { name: "Edit labels" }).click();
  const labelsDialog = page.getByRole("dialog", {
    name: new RegExp(`Labels — ${labelModel}`),
  });
  await labelsDialog.getByRole("button", { name: "Add label" }).click();
  await labelsDialog.getByLabel("Label", { exact: true }).fill("fast");
  await labelsDialog.getByRole("button", { name: "Save" }).click();
  await expect(labelledRow.getByText("fast")).toBeVisible();

  await page.getByRole("combobox", { name: "Filter by label" }).click();
  await page.getByRole("option", { name: "fast" }).click();
  await expect(labelledRow).toBeVisible();

  await page.getByRole("link", { name: "Agents" }).click();
  await expect(page.getByRole("heading", { name: "Agents" })).toBeVisible();
  await page.getByLabel("Name", { exact: true }).fill(labelAgent);
  await page.getByRole("combobox", { name: "Model", exact: true }).click();
  await page.getByRole("option", { name: "label: fast" }).click();
  await page.getByRole("button", { name: "Create agent" }).click();
  const labelAgentRow = page.getByRole("row", { name: new RegExp(labelAgent) });
  await expect(labelAgentRow.getByText("fast")).toBeVisible();

  // Seed a project/agent/session via the API, then delete the session in the tree.
  const raw = await page.evaluate(() => sessionStorage.getItem("agentbox-auth"));
  const token = JSON.parse(raw as string).state.token as string;
  const h = { Authorization: `Bearer ${token}` };
  const proj = await request.post(`${API}/projects`, {
    headers: h,
    data: { name: `e2e-proj-${suffix}`, path: "." },
  });
  const projId = (await proj.json()).id;
  const agent = await request.post(`${API}/agents`, {
    headers: h,
    data: { name: agentName, model: "e2e-model", tool_bindings: [] },
  });
  expect(agent.status()).toBe(200);
  const sess = await request.post(`${API}/sessions`, {
    headers: h,
    data: { project_id: projId, agent_id: agentName },
  });
  const sessionId = (await sess.json()).id;

  await page.reload();
  await page.waitForLoadState("networkidle");
  const delBtn = page.getByLabel(`Delete session ${sessionId}`);
  await expect(delBtn).toBeVisible({ timeout: 15000 });
  await delBtn.click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "Delete" }).click();
  await expect(delBtn).toHaveCount(0);
});

