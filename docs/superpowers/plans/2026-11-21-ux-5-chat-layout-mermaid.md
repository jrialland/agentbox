# UX-5 Wave 1 - Chat Layout and Mermaid Sizing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **This repo forbids commits without an explicit user request: do not run `git commit`; leave every change in the working tree.**

**Goal:** Make the session chat viewport-bound with a pinned composer and working auto-follow, and make wide Mermaid diagrams render at a legible size, with deterministic Playwright regressions.

**Architecture:** The shell becomes a fixed-height grid whose workspace only scrolls on ordinary pages. Session routes get a non-scrolling workspace, the messages pane becomes the single scroll container, and the composer sits at the bottom of the flow. The Mermaid SVG is allowed to fill its canvas width instead of collapsing to the replaced-element default. A new `test_long` pydantic-ai fixture produces a long Markdown answer with a wide `flowchart LR` diagram so both fixes can be asserted without a real model.

**Tech Stack:** React 19, Vite, Vitest, Playwright, Bun, pydantic-ai `TestModel`.

**Source:** [UX-5 live review](../../reviews/2026-11-21-ux-5/report.md), findings L1 and L2;
roadmap items UX-5.1 through UX-5.5. The rest of the UX-5 roadmap (UX-5.6 through UX-5.31) is
tracked separately and is intentionally out of scope for this wave.

## Global Constraints

- **Never commit.** The repository rule is "do not commit unless explicitly asked"; every task ends with tests run and the working tree left dirty.
- Work happens in the isolated worktree `.worktrees/ux5-wave1`; apply the final diff back to the main checkout only after all verification passes.
- Use Bun, not npm/pnpm. Frontend commands run from `apps/web`; Python commands run from the repo root.
- Run backend tests one package per invocation: `uv run pytest packages/agentbox-providers -q`.
- Do not hand-edit `apps/web/openapi.json` or `apps/web/src/api/schema.d.ts`.
- No comments in production code unless the surrounding file already uses them.
- Ruff line length 100. TypeScript is strict; `bun run build` must pass.
- E2E needs ports 5173, 8000, 9000, and 9999 free.
- Do not add API keys to files, tests, logs, or screenshots.
- Existing tests and visual-shell overflow checks must keep passing.

---

## Task 1: Deterministic `test_long` provider fixture

**Files:**
- Modify: `packages/agentbox-providers/src/agentbox_providers/resolver.py`
- Test: `packages/agentbox-providers/tests/test_resolver.py`

**Interfaces:**
- Produces: provider kind `test_long`, which resolves to a `TestModel` whose
  `custom_output_text` is a long Markdown document containing `# Long fixture` and a
  `flowchart LR` Mermaid fence. Tasks 2 and 3 consume this kind through the real backend.

- [ ] **Step 1: Write the failing test**

Append to `packages/agentbox-providers/tests/test_resolver.py`:

```python
def test_resolve_long_fixture():
    m = resolve_model(Provider(id="p", name="long", kind="test_long"), "long-model")
    assert isinstance(m, TestModel)
    text = m.custom_output_text
    assert text is not None
    assert text.startswith("# Long fixture")
    assert "flowchart LR" in text
    assert "Composer --> Agent" in text
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest packages/agentbox-providers/tests/test_resolver.py::test_resolve_long_fixture -q`

Expected: FAIL with `ValueError: Unknown provider kind: test_long`.

- [ ] **Step 3: Add the fixture branch**

In `packages/agentbox-providers/src/agentbox_providers/resolver.py`, add a module-level
constant immediately after `_flaky_attempts: dict[str, int] = {}`:

```python
_LONG_FIXTURE_TEXT = (
    "# Long fixture\n\n"
    + (
        "Agentbox streams a message through the harness, the model, and the tool layer, "
        "then renders the answer as Markdown with headings, lists, tables, and diagrams. "
    )
    * 30
    + "\n\n## Wide diagram\n\n"
    "```mermaid\nflowchart LR\n  Composer --> Agent\n  Agent --> Model\n"
    "  Model --> Tools\n  Tools --> Reply\n```\n\n"
    "## Table\n\n| Step | Owner |\n| --- | --- |\n| Compose | User |\n"
    "| Stream | Harness |\n| Answer | Model |\n"
)
```

Then add this branch inside `resolve_model`, next to the other `test_*` kinds and before the
final `raise ValueError`:

```python
    if kind == "test_long":
        from pydantic_ai.models.test import TestModel

        return TestModel(call_tools=[], custom_output_text=_LONG_FIXTURE_TEXT, profile=profile)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest packages/agentbox-providers/tests/test_resolver.py -q`

Expected: PASS (all resolver tests).

- [ ] **Step 5: Leave the change uncommitted**

Run: `git status --short packages/agentbox-providers`

Expected: modified resolver and test files, no commit.

---

## Task 2: Viewport-bound session shell, pinned composer, auto-follow

**Files:**
- Modify: `apps/web/src/design-system/shell/shell.module.css`
- Modify: `apps/web/src/design-system/shell/Workspace.tsx`
- Modify: `apps/web/src/pages/session.module.css`
- Modify: `apps/web/src/pages/SessionPage.tsx`
- Modify: `apps/web/src/chat/Composer.tsx`
- Modify: `apps/web/src/chat/composer.module.css`
- Modify: `apps/web/src/chat/chat-split.module.css`
- Test: Create `apps/web/src/design-system/shell/Workspace.test.tsx`
- Test: Create `apps/web/e2e/helpers.ts`
- Test: Create `apps/web/e2e/chat-ux5.spec.ts`

**Interfaces:**
- Consumes: provider kind `test_long` from Task 1.
- Produces: `Workspace` applies `styles.workspaceFullHeight` on `/sessions/:id`; the session
  root is exactly the workspace content height; `[data-testid="messages"]` is the scroll
  container; `[data-testid="composer"]` is the composer root. Task 3 reuses
  `apps/web/e2e/helpers.ts`.

- [ ] **Step 1: Write the failing unit test for the route-aware workspace**

Create `apps/web/src/design-system/shell/Workspace.test.tsx`:

```tsx
import { render } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { Workspace } from "./Workspace";
import styles from "./shell.module.css";

function renderWorkspace(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="*"
          element={
            <Workspace>
              <div>content</div>
            </Workspace>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Workspace", () => {
  it("locks scrolling for full-height session routes", () => {
    const { container } = renderWorkspace("/sessions/s1");
    const main = container.querySelector("main");
    expect(main?.className).toContain(styles.workspaceFullHeight);
  });

  it("keeps ordinary pages scrollable", () => {
    const { container } = renderWorkspace("/agents");
    const main = container.querySelector("main");
    expect(main?.className).not.toContain(styles.workspaceFullHeight);
  });
});
```

- [ ] **Step 2: Write the failing e2e layout regression**

Create `apps/web/e2e/helpers.ts`:

```ts
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
): Promise<string> {
  const h = await login(page);
  const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
  const provider = await request.post(`${API}/providers`, {
    headers: h,
    data: {
      name: `e2e-ux5-${suffix}`,
      kind,
      models_url: "http://localhost:9999/models",
    },
  });
  const providerId = (await provider.json()).id;
  await request.post(`${API}/providers/${providerId}/models/refresh`, { headers: h });
  const modelName = `e2e-ux5-model-${suffix}`;
  await request.post(`${API}/models`, {
    headers: h,
    data: { provider_id: providerId, name: modelName, labels: [] },
  });
  const agentName = `e2e-ux5-agent-${suffix}`;
  await request.post(`${API}/agents`, {
    headers: h,
    data: {
      name: agentName,
      description: "d",
      instructions: "i",
      model: modelName,
      tool_bindings: [],
      mode_definitions: [
        { name: "ask", flags: { write: false } },
        { name: "agent", flags: { write: true } },
      ],
      sub_agent_ids: [],
    },
  });
  const project = await request.post(`${API}/projects`, {
    headers: h,
    data: { name: `e2e-ux5-proj-${suffix}`, path: "." },
  });
  const projectId = (await project.json()).id;
  const session = await request.post(`${API}/sessions`, {
    headers: h,
    data: { project_id: projectId, agent_id: agentName },
  });
  return (await session.json()).id;
}
```

Create `apps/web/e2e/chat-ux5.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

import { setupSession } from "./helpers";

test("session is viewport-bound with a pinned composer and follows the stream", async ({
  page,
  request,
}) => {
  const sessionId = await setupSession(page, request, "test_long");
  await page.goto(`/sessions/${sessionId}`);
  await page.waitForLoadState("networkidle");

  const viewport = page.viewportSize();
  expect(viewport).not.toBeNull();
  const composer = page.getByTestId("composer");
  await expect(composer).toBeVisible();
  const initial = await composer.boundingBox();
  expect(initial).not.toBeNull();
  expect(initial!.y).toBeGreaterThan(viewport!.height * 0.6);
  expect(initial!.y + initial!.height).toBeLessThanOrEqual(viewport!.height + 1);

  const messages = page.getByTestId("messages");
  expect(
    await messages.evaluate((el) => getComputedStyle(el).overflowY),
  ).toBe("auto");

  await page.getByLabel("Message").fill("long please");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(
    page.getByRole("heading", { name: "Long fixture" }).last(),
  ).toBeVisible({ timeout: 20000 });

  await expect
    .poll(() =>
      messages.evaluate(
        (el) => el.scrollHeight - el.scrollTop - el.clientHeight,
      ),
    )
    .toBeLessThanOrEqual(64);
  const after = await messages.evaluate((el) => ({
    scrollHeight: el.scrollHeight,
    clientHeight: el.clientHeight,
  }));
  expect(after.scrollHeight).toBeGreaterThan(after.clientHeight);

  const afterComposer = await composer.boundingBox();
  expect(afterComposer!.y + afterComposer!.height).toBeLessThanOrEqual(
    viewport!.height + 1,
  );

  await page.getByLabel("Message").fill("again");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(
    page.getByRole("heading", { name: "Long fixture" }).last(),
  ).toBeVisible({ timeout: 20000 });

  const userBox = await page
    .locator('article[data-role="user"]')
    .last()
    .boundingBox();
  const assistantBox = await page
    .locator('article[data-role="assistant"]')
    .last()
    .boundingBox();
  expect(userBox).not.toBeNull();
  expect(assistantBox).not.toBeNull();
  expect(userBox!.y).toBeLessThan(assistantBox!.y);
  const lastAssistantVisible = await page
    .locator('article[data-role="assistant"]')
    .last()
    .evaluate((el) => {
      const rect = el.getBoundingClientRect();
      return rect.bottom > 0 && rect.top < window.innerHeight;
    });
  expect(lastAssistantVisible).toBe(true);
});
```

- [ ] **Step 3: Run the failing tests**

Run: `cd apps/web; bun run test src/design-system/shell/Workspace.test.tsx`

Expected: FAIL because `Workspace` does not apply the full-height class yet.

Run: `cd apps/web; bun run e2e/prepare.ts; bunx playwright test e2e/chat-ux5.spec.ts`

Expected: FAIL on the composer position assertion (the composer is near the top, and the
messages pane does not scroll).

- [ ] **Step 4: Implement the route-aware workspace**

Replace `apps/web/src/design-system/shell/Workspace.tsx` with:

```tsx
import type { ReactNode } from "react";
import { useMatch } from "react-router-dom";

import styles from "./shell.module.css";

export function Workspace({ children }: { children: ReactNode }) {
  const fullHeight = useMatch("/sessions/:id") !== null;
  return (
    <main
      className={`${styles.workspace}${fullHeight ? ` ${styles.workspaceFullHeight}` : ""}`}
    >
      {children}
    </main>
  );
}
```

- [ ] **Step 5: Make the shell and workspace height-bound**

In `apps/web/src/design-system/shell/shell.module.css`, change `.shell`, `.workspace`,
`.fullBleed`, and `.mobileShell` to:

```css
.shell {
  display: grid;
  grid-template-columns: var(--ab-rail-width) var(--ab-panel-width) minmax(0, 1fr);
  grid-template-rows: minmax(0, 1fr);
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
  background: var(--ab-canvas);
}

.workspace {
  min-width: 0;
  min-height: 0;
  overflow: auto;
  padding: var(--ab-space-5);
}

.workspaceFullHeight {
  overflow: hidden;
}

.fullBleed {
  width: 100%;
  height: 100%;
  min-height: 0;
}

.mobileShell {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  height: 100vh;
  height: 100dvh;
  background: var(--ab-canvas);
}
```

Leave the rest of the file unchanged.

- [ ] **Step 6: Make the messages pane the only scroller**

In `apps/web/src/pages/session.module.css`, add `overscroll-behavior: contain;` to
`.messages` (keep the existing `flex`, `min-height`, `overflow-y`, `padding`, and `position`
declarations).

In `apps/web/src/chat/chat-split.module.css`, replace the combined rule with:

```css
.split {
  grid-template-rows: minmax(0, 1fr);
}

.chat,
.app {
  min-height: 0;
  min-width: 0;
}

.chat {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding-right: var(--ab-space-2);
}

.app {
  overflow: auto;
  padding-left: var(--ab-space-2);
}
```

In `apps/web/src/design-system/shell/shell.module.css`, change `.projectPane` to use
`overflow-y: auto;` so long project/session trees remain reachable under the fixed-height shell.

- [ ] **Step 7: Pin the composer in flow and add test ids**

In `apps/web/src/chat/composer.module.css`, remove `position: sticky;` and `bottom:` from
`.composer`, and add `flex: 0 0 auto;`.

In `apps/web/src/chat/Composer.tsx`, add `data-testid="composer"` to the outer
`<div className={...}>` that has the drag handlers.

In `apps/web/src/pages/SessionPage.tsx`, add `data-testid="messages"` to the
`<div className={styles.messages} ref={messagesRef}>` element, and call `scrollToBottom()`
inside `handleSend` immediately before `await chat.send(...)`:

```tsx
    setInput("");
    setForkMode(false);
    setForkFromTurnId(null);
    scrollToBottom();
    await chat.send(content, {
```

- [ ] **Step 8: Run the unit test and build**

Run: `cd apps/web; bun run test src/design-system/shell/Workspace.test.tsx`

Expected: PASS (2 tests).

Run: `cd apps/web; bun run test`

Expected: PASS (all Vitest tests, including `useAutoScroll` and `SessionPage`).

Run: `cd apps/web; bun run build`

Expected: PASS (`tsc --noEmit` and Vite build).

- [ ] **Step 9: Run the e2e layout regression**

Run: `cd apps/web; bun run e2e/prepare.ts; bunx playwright test e2e/chat-ux5.spec.ts`

Expected: PASS (1 test). If it fails on the messages auto-scroll assertion, confirm the
smooth-scroll poll retries for at least 5 seconds before changing anything.

- [ ] **Step 10: Leave the changes uncommitted**

Run: `git status --short apps/web`

Expected: modified and new frontend files, no commit.

---

## Task 3: Wide Mermaid diagrams fill the block

**Files:**
- Modify: `apps/web/src/chat/markdown.css`
- Test: Create `apps/web/e2e/mermaid-ux5.spec.ts`

**Interfaces:**
- Consumes: provider kind `test_long` and `apps/web/e2e/helpers.ts` from Tasks 1-2.
- Produces: rendered Mermaid SVGs fill their block when the diagram is wide enough; the
  existing invalid-diagram fallback is unchanged.

- [ ] **Step 1: Write the failing e2e regression**

Create `apps/web/e2e/mermaid-ux5.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

import { setupSession } from "./helpers";

test("wide mermaid diagrams fill the block width and stay legible", async ({
  page,
  request,
}) => {
  const sessionId = await setupSession(page, request, "test_long");
  await page.goto(`/sessions/${sessionId}`);
  await page.waitForLoadState("networkidle");

  await page.getByLabel("Message").fill("diagram please");
  await page.getByRole("button", { name: "Send" }).click();

  const block = page.locator(".mermaid-block").last();
  await expect(block.locator("svg")).toBeVisible({ timeout: 20000 });

  const blockBox = await block.boundingBox();
  const svgBox = await block.locator("svg").boundingBox();
  expect(blockBox).not.toBeNull();
  expect(svgBox).not.toBeNull();
  expect(svgBox!.width).toBeGreaterThan(blockBox!.width * 0.8);
  expect(svgBox!.height).toBeGreaterThan(40);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/web; bun run e2e/prepare.ts; bunx playwright test e2e/mermaid-ux5.spec.ts`

Expected: FAIL because the SVG is about 300px wide in a ~900px block (ratio ~0.33).

- [ ] **Step 3: Fix the canvas and SVG sizing**

In `apps/web/src/chat/markdown.css`, replace `.mermaid-canvas` with:

```css
.mermaid-canvas {
  display: flex;
  justify-content: center;
  min-width: min-content;
  width: 100%;
}

.mermaid-canvas svg {
  height: auto;
  width: 100%;
}
```

Do not override Mermaid's inline `max-width`: it is the diagram's natural width cap and prevents
small or vertical diagrams from being upscaled to the full block.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/web; bun run e2e/prepare.ts; bunx playwright test e2e/mermaid-ux5.spec.ts`

Expected: PASS. If the SVG still resolves to 300px, inspect the computed width of
`.mermaid-block > div` and add `width: 100%;` to that wrapper in `markdown.css` before
re-running (the `react-transform-wrapper` element).

- [ ] **Step 5: Keep the safe fallback green**

Run: `cd apps/web; bunx playwright test e2e/chat-ux2.spec.ts -g "mermaid"`

Expected: PASS (`Diagram could not be rendered` fallback still works).

- [ ] **Step 6: Leave the changes uncommitted**

Run: `git status --short apps/web`

Expected: modified `markdown.css` and new e2e spec, no commit.

---

## Task 4: Whole-wave verification and live screenshot confirmation

**Files:**
- Verify: all Task 1-3 files
- Update after verification: `docs/reviews/2026-11-21-ux-5/report.md`,
  `docs/reviews/2026-11-21-ux-5/README.md`

- [ ] **Step 1: Run the full automated checks**

Run: `uv run pytest packages/agentbox-providers -q`

Run: `cd apps/web; bun run test`

Run: `cd apps/web; bun run build`

Run: `cd apps/web; bun run e2e/prepare.ts; bunx playwright test e2e/chat-ux5.spec.ts e2e/mermaid-ux5.spec.ts`

Expected: all pass.

- [ ] **Step 2: Confirm the diff is scoped**

Run: `git diff --stat HEAD` and `git status --short`

Expected: only the planned provider, shell, session, composer, chat-split, markdown, e2e, and
review files.

- [ ] **Step 3: Apply the worktree diff to the main checkout**

From the worktree, run: `git diff HEAD > wave1.patch` and `git status --short`; confirm new
files are included (if not, copy them explicitly). From the main checkout, apply the patch with
`git apply --3way wave1.patch`, then run the same checks from Step 1. Do not commit.

- [ ] **Step 4: Live screenshot confirmation with the real provider**

Start the backend and Vite app from the main checkout with a temporary database and the real
DeepSeek key supplied only through the process environment (never written to a file). Log in as
`admin`/`admin`, open a session, and capture replacement evidence for:

- an empty session (composer at the bottom),
- a long 400+ word answer with the composer still visible,
- a second question with its answer in view (the L1 turn-boundary image), and
- a horizontal Mermaid flowchart that is legible.

Save the images under `docs/reviews/2026-11-21-ux-5/assets/` with a `post-fix-` prefix, delete the
temporary DB and logs, and redact any key that appears in generated logs.

- [ ] **Step 5: Update the review and roadmap**

Add a "Remediation verification" section to the report listing the post-fix screenshots and the
commands that passed. Change `UX-5.1` and `UX-5.2` in `docs/ROADMAP.md` from `PLANNED` to
`DONE` only after the live screenshots confirm both fixes.

- [ ] **Step 6: Leave everything uncommitted**

Run: `git status --short`

Expected: the planned source/test changes, the new post-fix screenshots, and the roadmap/report
edits; no commit.

## Self-review

- **Spec coverage:** L1 (height-bound shell, pinned composer, auto-follow, new-turn scroll) is
  covered by Task 2; L2 (Mermaid width) by Task 3. Both have a failing e2e test before the fix.
- **No placeholders:** every step names exact files, commands, selectors, and code.
- **Type consistency:** `Workspace` imports `useMatch` from the project's `react-router-dom`
  version; `data-testid` names match between production and tests; `test_long` is referenced
  consistently.
- **Known risk:** the TransformWrapper may keep a shrink-wrapped content box; Task 3 Step 4
  includes the explicit next action rather than a vague retry.
- **No commits:** the plan deliberately omits commit steps per repository policy.

## Amendments after the wave-1 code review

The first implementation passed the original tests but review found four gaps; these were fixed
and covered before declaring wave 1 done:

- `.split` now has `grid-template-rows: minmax(0, 1fr)` and `.chat` is a column flex container,
  so the composer cannot be clipped when the MCP app panel is open.
- `.projectPane` scrolls vertically instead of clipping long project/session trees.
- The Mermaid `max-width: 100% !important` override was removed so tall/small diagrams keep their
  natural width; a vertical-diagram Playwright test guards it.
- The follow-up e2e was rewritten to wait for two user and two assistant articles before asserting
  the new Q/A pair; the original wait on a repeated heading could pass on turn 1.
- Added mobile (390x844), split-view composer, and jump-to-latest tests.
- Normalized the EOL of touched files so `git diff --check` is clean.

Final verification for the amended wave: Vitest 184/184, Playwright 37/37, agentbox-api 179/179,
providers 18/18, `bun run build`, Ruff, and Ty all pass; the live DeepSeek post-fix screenshots
are listed in the report.
