import { expect, type Page, test } from "@playwright/test";

const API = "http://localhost:8000";

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByRole("textbox", { name: "Password" }).fill("admin");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();
}

test("A2A structured edits, JSON errors, presets, and scope warning", async ({
  page,
  request,
}) => {
  await login(page);
  const token = await page.evaluate(() => {
    const raw = sessionStorage.getItem("agentbox-auth");
    return JSON.parse(raw as string).state.token as string;
  });
  const headers = { Authorization: `Bearer ${token}` };
  const suffix = Date.now();
  const provider = await request.post(`${API}/providers`, {
    headers,
    data: {
      name: `e2e-ux3-card-provider-${suffix}`,
      kind: "test",
      models_url: "http://localhost:9999/models",
    },
  });
  const providerId = (await provider.json()).id;
  await request.post(`${API}/providers/${providerId}/models/refresh`, { headers });
  const agentName = `e2e-ux3-card-${suffix}`;
  await request.post(`${API}/agents`, {
    headers,
    data: {
      name: agentName,
      description: "d",
      instructions: "i",
      model: "e2e-model",
      tool_bindings: [],
      mode_definitions: [{ name: "agent", flags: { write: true } }],
      sub_agent_ids: [],
    },
  });

  await page.goto("/agents");
  const row = page.getByRole("row").filter({ hasText: agentName });
  await row.getByRole("button", { name: "A2A" }).click();
  const card = page.getByRole("dialog", { name: `A2A card: ${agentName}` });
  await card.getByLabel("Agent card name").fill("Reviewer");
  await card.getByRole("button", { name: "Add skill" }).click();
  await card.getByLabel("Skill 1 id").fill("review");
  await card.getByLabel("Skill 1 name").fill("Review");
  await card.getByRole("button", { name: "Save" }).click();
  await expect(card).toBeHidden();
  await row.getByRole("button", { name: "A2A" }).click();
  await expect(card.getByLabel("Agent card name")).toHaveValue("Reviewer");
  await expect(card.getByLabel("Skill 1 name")).toHaveValue("Review");

  await card.getByRole("tab", { name: "JSON" }).click();
  await card.getByLabel("Agent card JSON").fill("{bad");
  await card.getByRole("button", { name: "Save" }).click();
  await expect(card.getByRole("alert")).toContainText(/JSON|property name/i);
  await expect(card).toBeVisible();
  await page.keyboard.press("Escape");

  await page.goto("/providers");
  await page.getByRole("button", { name: "New provider" }).click();
  const providerForm = page.getByRole("dialog", { name: "New provider" });
  await providerForm.getByRole("combobox", { name: "Kind" }).click();
  await page.getByRole("option", { name: "DeepSeek" }).click();
  await expect(providerForm.getByLabel("Base URL")).toHaveValue(
    "https://api.deepseek.com/v1",
  );
  await providerForm.getByRole("button", { name: "Help: Provider kind" }).click();
  await expect(page.getByText(/OpenAI-compatible APIs/i)).toBeVisible();

  await page.goto("/api-keys");
  await page.getByRole("button", { name: "Use recommended" }).click();
  await expect(page.getByText("2 selected")).toBeVisible();
  await page.getByRole("button", { name: "Clear scopes" }).click();
  await expect(page.getByText(/unusable/i)).toBeVisible();
});
