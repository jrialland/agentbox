# UX-3 Contextual Help and Structured Editors Implementation Plan

**Status:** COMPLETE

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Agentbox setup learnable in place by adding shared in-app help, provider connection testing/presets, structured A2A and agent editors, scope guidance, guided empty states, and a first-run onboarding wizard.

**Architecture:** Add a typed help registry and reusable help primitives, then build small controlled editors around existing API mutations. Add one backend provider-test endpoint that validates form values without persistence. Onboarding is a frontend orchestrator over existing provider/agent/project/session mutations, with progress derived from real resources.

**Tech Stack:** React 19, TypeScript, Vite 8, Mantine 9, TanStack Query, RemixIcon, pydantic-ai provider model listing, FastAPI, SQLModel, Playwright, Vitest, Storybook 10.6.8.

## Global Constraints

- Full UX-3 is one spec/cycle; do not defer structured editors or onboarding.
- Help opens in-app only. Do not add external documentation dependencies.
- Provider presets fill only untouched fields; never overwrite custom values.
- Provider connection tests never persist providers or models and never log/return API keys.
- A2A validation is frontend-only; keep the existing `PUT /agents/{name}/card` contract.
- Preserve unknown A2A JSON fields during structured edits.
- No UX-4 work: do not add destructive-confirmation systems, 404/session states, global API error propagation, or active-nav changes.
- Use design-system components; no Bulma or legacy chat classes.
- Frontend commands run from `apps/web`; Python commands run from the repo root.
- Do not pass multiple package test directories to one pytest invocation.
- Regenerate `apps/web/openapi.json` and `apps/web/src/api/schema.d.ts` after backend route changes.

---

### Task 1: Provider connection-test endpoint

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/routers/providers.py`
- Create: `packages/agentbox-api/tests/test_provider_test.py`

**Interfaces:**
- Produces `POST /providers/test` with `ProviderTestRequest` and `ProviderTestResult`.
- Produces response codes: `invalid_url`, `unauthorized`, `not_found`, `timeout`, `connection_failed`, `no_models_url`, `unknown`.
- Consumes `agentbox_providers.models.list_models`.

- [ ] **Step 1: Write the failing backend tests**

```python
import httpx
import pytest
from sqlmodel import func, select

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.security import hash_password
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import (
    Permission,
    Role,
    RolePermissionLink,
    User,
    UserRoleLink,
)
from agentbox_models.tables.core import Provider


async def _app_with_provider_create():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as session:
        session.add(
            User(
                id="u1",
                username="alice",
                email="a@x",
                password_hash=hash_password("pw"),
            )
        )
        session.add(Role(id="r1", name="role"))
        session.add(Permission(id="p1", name="providers:create"))
        session.add(RolePermissionLink(role_id="r1", permission_id="p1"))
        session.add(UserRoleLink(user_id="u1", role_id="r1"))
        await session.commit()
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    token = (
        await client.post("/auth/login", json={"username": "alice", "password": "pw"})
    ).json()["access_token"]
    return engine, factory, client, {"Authorization": f"Bearer {token}"}


async def test_provider_test_returns_models_without_persisting(monkeypatch):
    captured = {}

    async def fake_list_models(provider):
        captured["kind"] = provider.kind
        captured["key"] = provider.api_key
        return ["alpha", "beta", "gamma"]

    monkeypatch.setattr("agentbox_api.routers.providers.list_models", fake_list_models)
    engine, factory, client, headers = await _app_with_provider_create()
    try:
        r = await client.post(
            "/providers/test",
            headers=headers,
            json={
                "kind": "deepseek",
                "base_url": "https://api.deepseek.com/v1",
                "models_url": "https://api.deepseek.com/v1/models",
                "api_key": "sk-test",
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["model_count"] == 3
        assert body["sample_models"] == ["alpha", "beta", "gamma"]
        assert captured == {"kind": "deepseek", "key": "sk-test"}
        async with factory() as session:
            count = (await session.execute(select(func.count()).select_from(Provider))).scalar()
        assert count == 0
    finally:
        await client.aclose()
        await engine.dispose()


async def test_provider_test_reuses_stored_key(monkeypatch):
    captured = {}

    async def fake_list_models(provider):
        captured["key"] = provider.api_key
        return ["m"]

    monkeypatch.setattr("agentbox_api.routers.providers.list_models", fake_list_models)
    engine, factory, client, headers = await _app_with_provider_create()
    try:
        async with factory() as session:
            session.add(
                Provider(
                    id="p1",
                    name="stored",
                    kind="generic",
                    api_key="sk-stored",
                    models_url="https://example.test/models",
                )
            )
            await session.commit()
        r = await client.post(
            "/providers/test",
            headers=headers,
            json={"kind": "generic", "provider_id": "p1", "api_key": ""},
        )
        assert r.json()["ok"] is True
        assert captured["key"] == "sk-stored"
    finally:
        await client.aclose()
        await engine.dispose()


async def test_provider_test_normalizes_failures(monkeypatch):
    engine, factory, client, headers = await _app_with_provider_create()
    try:
        async def unauthorized(_provider):
            raise httpx.HTTPStatusError(
                "unauthorized",
                request=httpx.Request("GET", "https://example.test/models"),
                response=httpx.Response(401),
            )

        monkeypatch.setattr("agentbox_api.routers.providers.list_models", unauthorized)
        r = await client.post(
            "/providers/test",
            headers=headers,
            json={"kind": "generic", "models_url": "https://example.test/models"},
        )
        assert r.status_code == 200
        assert r.json()["ok"] is False
        assert r.json()["error"]["code"] == "unauthorized"

        monkeypatch.setattr(
            "agentbox_api.routers.providers.list_models",
            lambda _provider: (_ for _ in ()).throw(ValueError("no models_url")),
        )
        r = await client.post("/providers/test", headers=headers, json={"kind": "generic"})
        assert r.json()["error"]["code"] == "no_models_url"
    finally:
        await client.aclose()
        await engine.dispose()
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest packages/agentbox-api/tests/test_provider_test.py -q`
Expected: FAIL with 404 because `/providers/test` does not exist.

- [ ] **Step 3: Implement the endpoint**

Add to `providers.py`:

```python
import asyncio
import time
from urllib.parse import urlparse

import httpx

class ProviderTestRequest(BaseModel):
    kind: str
    base_url: str | None = None
    models_url: str | None = None
    api_key: str | None = None
    provider_id: str | None = None


class ProviderTestError(BaseModel):
    code: str
    message: str


class ProviderTestResult(BaseModel):
    ok: bool
    latency_ms: int
    model_count: int | None = None
    sample_models: list[str] = []
    error: ProviderTestError | None = None


def _checked_url(value: str | None, field: str) -> str | None:
    if value is None or value == "":
        return None
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(status_code=422, detail=f"{field} must be an http/https URL")
    return value


def _failure(code: str, message: str, latency_ms: int) -> ProviderTestResult:
    return ProviderTestResult(
        ok=False,
        latency_ms=latency_ms,
        error=ProviderTestError(code=code, message=message),
    )


@router.post("/test", response_model=ProviderTestResult)
async def test_provider(
    body: ProviderTestRequest,
    request: Request,
    _=Depends(require_permission("providers:create")),
):
    stored = None
    if body.provider_id:
        stored = await ProviderRepository(request.app.state.session_factory).get(
            body.provider_id
        )
        if stored is None:
            raise HTTPException(status_code=404, detail="Not found")
    base_url = _checked_url(body.base_url, "base_url")
    models_url = _checked_url(body.models_url, "models_url")
    provider = Provider(
        id=body.provider_id or "test",
        name=stored.name if stored else "test",
        kind=body.kind,
        base_url=base_url or (stored.base_url if stored else None),
        models_url=models_url or (stored.models_url if stored else None),
        api_key=body.api_key or (stored.api_key if stored else None),
    )
    if not provider.models_url:
        return _failure(
            "no_models_url",
            "Enter the endpoint that returns the provider model list.",
            0,
        )
    started = time.perf_counter()
    try:
        names = await asyncio.wait_for(list_models(provider), timeout=10)
    except TimeoutError:
        return _failure(
            "timeout",
            "The provider did not answer within 10 seconds. Check the URL and network.",
            int((time.perf_counter() - started) * 1000),
        )
    except ValueError:
        return _failure(
            "no_models_url",
            "Enter the endpoint that returns the provider model list.",
            int((time.perf_counter() - started) * 1000),
        )
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        code = "unauthorized" if status in (401, 403) else "not_found" if status == 404 else "connection_failed"
        message = {
            "unauthorized": "Authentication failed. Check the API key.",
            "not_found": "The models URL was not found. Check the path.",
            "connection_failed": f"The provider returned HTTP {status}.",
        }[code]
        return _failure(code, message, int((time.perf_counter() - started) * 1000))
    except httpx.RequestError:
        return _failure(
            "connection_failed",
            "Could not reach the provider. Check the URL and network.",
            int((time.perf_counter() - started) * 1000),
        )
    except Exception:
        return _failure(
            "unknown",
            "The connection test failed unexpectedly.",
            int((time.perf_counter() - started) * 1000),
        )
    latency = int((time.perf_counter() - started) * 1000)
    logger.info(
        "provider test ok provider={} kind={} count={}",
        body.provider_id,
        body.kind,
        len(names),
    )
    return ProviderTestResult(
        ok=True,
        latency_ms=latency,
        model_count=len(names),
        sample_models=names[:5],
    )
```

- [ ] **Step 4: Run tests and checks**

Run:
```powershell
uv run pytest packages/agentbox-api/tests/test_provider_test.py -q
uv run ruff check packages/agentbox-api
uv run ty check packages/agentbox-api
```
Expected: PASS; ruff and ty clean.

- [ ] **Step 5: Commit**

```powershell
git add packages/agentbox-api/src/agentbox_api/routers/providers.py packages/agentbox-api/tests/test_provider_test.py
git commit -m "feat(api): add provider connection test endpoint"
```

---

### Task 2: Frontend provider-test API and hook

**Files:**
- Modify: `apps/web/src/api/endpoints.ts`
- Modify: `apps/web/src/api/queries.ts`
- Test: `apps/web/src/api/queries.test.tsx`
- Generated: `apps/web/openapi.json`, `apps/web/src/api/schema.d.ts`

**Interfaces:**
- Produces `ProviderTestInput`, `ProviderTestResult`, `testProvider(body)`, `useTestProvider()`.
- Consumes `POST /providers/test`.

- [ ] **Step 1: Regenerate API artifacts**

Run:
```powershell
uv run python apps/web/scripts/gen-openapi.py
cd apps/web
bun run codegen
```

- [ ] **Step 2: Write the failing hook test**

Extend the existing `@testing-library/react` import with `act` and add `useTestProvider` to the `./queries` import. Then append:

```tsx
test("useTestProvider returns the test result", async () => {
  vi.spyOn(endpoints, "testProvider").mockResolvedValue({
    ok: true,
    latency_ms: 12,
    model_count: 2,
    sample_models: ["a", "b"],
    error: null,
  } as never);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => useTestProvider(), { wrapper });
  await act(async () => {
    const value = await result.current.mutateAsync({
      kind: "generic",
      models_url: "https://example.test/models",
    });
    expect(value.model_count).toBe(2);
  });
});
```

- [ ] **Step 3: Run to verify failure**

Run: `cd apps/web && bun run test -- src/api/queries.test.tsx`
Expected: FAIL because `testProvider`/`useTestProvider` do not exist.

- [ ] **Step 4: Implement API and hook**

In `endpoints.ts`:

```ts
export type ProviderTestResult = components["schemas"]["ProviderTestResult"];

export type ProviderTestInput = {
  kind: string;
  base_url?: string | null;
  models_url?: string | null;
  api_key?: string | null;
  provider_id?: string | null;
};

export async function testProvider(
  body: ProviderTestInput,
): Promise<ProviderTestResult> {
  const { data, error } = await api.POST("/providers/test", { body });
  if (error) throw new Error("Failed to test provider");
  return data as ProviderTestResult;
}
```

In `queries.ts`, import `testProvider` and add:

```ts
export function useTestProvider() {
  return useMutation({ mutationFn: testProvider });
}
```

- [ ] **Step 5: Run test and build**

Run:
```powershell
cd apps/web
bun run test -- src/api/queries.test.tsx
bun run build
```
Expected: PASS and build clean.

- [ ] **Step 6: Commit**

```powershell
git add apps/web/openapi.json apps/web/src/api/schema.d.ts apps/web/src/api/endpoints.ts apps/web/src/api/queries.ts apps/web/src/api/queries.test.tsx
git commit -m "feat(web): add provider test client"
```

---

### Task 3: Shared help system

**Files:**
- Create: `apps/web/src/help/types.ts`
- Create: `apps/web/src/help/content.ts`
- Create: `apps/web/src/help/HelpProvider.tsx`
- Create: `apps/web/src/help/HelpDrawer.tsx`
- Create: `apps/web/src/help/HelpTip.tsx`
- Create: `apps/web/src/help/HelpLink.tsx`
- Create: `apps/web/src/help/help.test.tsx`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/design-system/forms/FormField.tsx`

**Interfaces:**
- Produces `HelpId`, `HelpEntry`, `HELP_ENTRIES`, `getHelpEntry(id)`.
- Produces `HelpProvider`, `useHelp()`, `HelpDrawer`, `HelpTip({id})`, `HelpLink({id,children})`.
- `FormField` gains optional `help?: ReactNode` rendered beside the label.

- [ ] **Step 1: Write failing help tests**

Create `help.test.tsx`:

```tsx
import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithTheme } from "../test/render";
import { getHelpEntry } from "./content";
import { HelpProvider } from "./HelpProvider";
import { HelpTip } from "./HelpTip";

function Harness() {
  return (
    <HelpProvider>
      <HelpTip id="provider.kind" />
    </HelpProvider>
  );
}

describe("help system", () => {
  it("exposes a complete provider kind entry", () => {
    const entry = getHelpEntry("provider.kind");
    expect(entry.title).toBe("Provider kind");
    expect(entry.summary.length).toBeGreaterThan(20);
    expect(entry.sections.length).toBeGreaterThan(0);
  });

  it("opens the help drawer from a tip", () => {
    renderWithTheme(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Help: Provider kind" }));
    expect(screen.getByText(/OpenAI-compatible APIs/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Learn more" }));
    expect(screen.getByRole("dialog", { name: "Provider kind" })).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/web && bun run test -- src/help/help.test.tsx`
Expected: FAIL because the help module does not exist.

- [ ] **Step 3: Implement types and content**

`types.ts`:

```ts
export type HelpId =
  | "provider.kind"
  | "provider.urls"
  | "provider.api-key"
  | "provider.models"
  | "agent.modes"
  | "agent.tools"
  | "agent.mcp"
  | "agent.subagents"
  | "a2a.card"
  | "a2a.skills"
  | "api.scopes"
  | "skills.overview"
  | "onboarding.provider"
  | "onboarding.agent"
  | "onboarding.session";

export type HelpSection = {
  heading: string;
  paragraphs?: string[];
  bullets?: string[];
  code?: string;
};

export type HelpEntry = {
  id: HelpId;
  title: string;
  summary: string;
  sections: HelpSection[];
};
```

`content.ts` exports `HELP_ENTRIES: Record<HelpId, HelpEntry>` and:

```ts
export function getHelpEntry(id: HelpId): HelpEntry {
  return HELP_ENTRIES[id];
}
```

Use these titles/summaries:

| ID | Title | Summary |
|---|---|---|
| `provider.kind` | Provider kind | Choose the API style your provider exposes. Most hosted services are OpenAI-compatible. |
| `provider.urls` | Provider URLs | Base URL is the API root; Models URL must return a JSON model list. |
| `provider.api-key` | Provider API key | The key is stored by Agentbox and reused when you leave the field blank while editing. |
| `provider.models` | Model discovery | Agentbox reads an OpenAI-style `data[].id` list and adds new models on refresh. |
| `agent.modes` | Agent modes | Modes let the same agent offer read-only Ask and write-enabled Agent behavior. |
| `agent.tools` | Agent tools | Tools are grouped by risk. Write tools can modify files or run commands. |
| `agent.mcp` | MCP servers | MCP servers add tools and apps over a remote MCP endpoint. |
| `agent.subagents` | Sub-agents | Sub-agents run delegated work and add latency and token cost. |
| `a2a.card` | A2A agent card | The card publishes your agent’s identity, capabilities, and skills to A2A clients. |
| `a2a.skills` | A2A skills | Each skill describes one capability the agent can perform. |
| `api.scopes` | API scopes | Scopes limit what an API key can do. A key with no scopes cannot authenticate useful work. |
| `skills.overview` | Skills | Skills are reusable Markdown instruction packs invoked from the composer with `/`. |
| `onboarding.provider` | Connect a provider | Start with one model endpoint so Agentbox can discover models. |
| `onboarding.agent` | Create an agent | Pick a discovered model and keep write tools disabled until needed. |
| `onboarding.session` | Start a session | A session pairs a project folder with an agent. |

Each entry must contain at least one section with a concrete example. For example `provider.urls` includes:
```ts
{
  heading: "Example",
  code: "Base URL: https://api.deepseek.com/v1\nModels URL: https://api.deepseek.com/v1/models",
}
```

- [ ] **Step 4: Implement provider, drawer, tip, and link**

`HelpProvider.tsx`:

```tsx
import { createContext, useContext, useState, type ReactNode } from "react";

import type { HelpId } from "./types";
import { HelpDrawer } from "./HelpDrawer";

const HelpContext = createContext<{ openHelp: (id: HelpId) => void } | null>(null);

export function HelpProvider({ children }: { children: ReactNode }) {
  const [active, setActive] = useState<HelpId | null>(null);
  return (
    <HelpContext.Provider value={{ openHelp: setActive }}>
      {children}
      <HelpDrawer active={active} onClose={() => setActive(null)} />
    </HelpContext.Provider>
  );
}

export function useHelp() {
  const context = useContext(HelpContext);
  if (!context) throw new Error("useHelp must be used inside HelpProvider");
  return context;
}
```

`HelpDrawer.tsx` renders the design-system `Drawer` with `title={entry.title}` when active, then the summary, sections, lists, code blocks, and related links using `HelpLink`. Keep the drawer accessible: `Drawer` supplies the dialog role; add `aria-label={entry.title}` when active.

`HelpTip.tsx` uses `Popover` from Mantine with `trigger="hover"`, `position="top"`, and an icon button:

```tsx
<Popover position="top" withArrow shadow="md" trigger="hover">
  <Popover.Target>
    <IconButton
      label={`Help: ${entry.title}`}
      icon={RiQuestionLine}
      size={16}
      variant="subtle"
    />
  </Popover.Target>
  <Popover.Dropdown>
    <p>{entry.summary}</p>
    <Button size="compact-xs" onClick={() => openHelp(id)}>Learn more</Button>
  </Popover.Dropdown>
</Popover>
```

`HelpLink.tsx` is a button styled as a link that calls `openHelp(id)`.

Mount `HelpProvider` in `App.tsx` inside `ThemeProvider` and around `Notifications`/routes so every page can use it.

- [ ] **Step 5: Extend FormField**

Add `help?: ReactNode` to `FormField` props and render it next to the label in both label branches. Do not wrap it inside the label when `htmlFor` is used in a way that nests interactive controls; place it adjacent in a flex row.

- [ ] **Step 6: Run tests and build**

Run:
```powershell
cd apps/web
bun run test -- src/help/help.test.tsx
bun run build
```
Expected: PASS and build clean.

- [ ] **Step 7: Commit**

```powershell
git add apps/web/src/help apps/web/src/App.tsx apps/web/src/design-system/forms/FormField.tsx
git commit -m "feat(web): add shared in-app help system"
```

---

### Task 4: Provider presets and shared provider form

**Files:**
- Create: `apps/web/src/pages/providers/providerPresets.ts`
- Create: `apps/web/src/pages/providers/ProviderForm.tsx`
- Create: `apps/web/src/pages/providers/ProviderTestResult.tsx`
- Test: `apps/web/src/pages/providers/providerPresets.test.ts`
- Modify: `apps/web/src/pages/ProvidersPage.tsx`
- Modify: `apps/web/src/pages/providers.module.css`

**Interfaces:**
- Produces `ProviderDraft`, `EMPTY_PROVIDER_DRAFT`, `applyProviderPreset(current, nextKind)`, `PROVIDER_PRESETS`.
- Produces `ProviderForm({ value, onChange, providerId })` including connection test UI.
- Produces `ProviderTestResultView({ result })`.

- [ ] **Step 1: Write failing preset tests**

```ts
import { describe, expect, it } from "vitest";

import {
  EMPTY_PROVIDER_DRAFT,
  applyProviderPreset,
} from "./providerPresets";

describe("applyProviderPreset", () => {
  it("fills untouched URLs", () => {
    const next = applyProviderPreset(
      { ...EMPTY_PROVIDER_DRAFT, kind: "generic" },
      "deepseek",
    );
    expect(next.baseUrl).toBe("https://api.deepseek.com/v1");
    expect(next.modelsUrl).toBe("https://api.deepseek.com/v1/models");
  });

  it("preserves custom URLs", () => {
    const current = {
      ...EMPTY_PROVIDER_DRAFT,
      kind: "generic",
      baseUrl: "https://custom.test/v1",
    };
    const next = applyProviderPreset(current, "openai_legacy");
    expect(next.baseUrl).toBe("https://custom.test/v1");
    expect(next.modelsUrl).toBe("https://api.openai.com/v1/models");
  });

  it("replaces a previous preset URL when switching kinds", () => {
    const current = applyProviderPreset(
      { ...EMPTY_PROVIDER_DRAFT, kind: "generic" },
      "deepseek",
    );
    const next = applyProviderPreset(current, "moonshot");
    expect(next.baseUrl).toBe("https://api.moonshot.cn/v1");
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/web && bun run test -- src/pages/providers/providerPresets.test.ts`
Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement presets**

```ts
export type ProviderDraft = {
  name: string;
  kind: string;
  baseUrl: string;
  modelsUrl: string;
  apiKey: string;
};

export const EMPTY_PROVIDER_DRAFT: ProviderDraft = {
  name: "",
  kind: "generic",
  baseUrl: "",
  modelsUrl: "",
  apiKey: "",
};

type Preset = { label: string; baseUrl: string; modelsUrl: string };

export const PROVIDER_PRESETS: Record<string, Preset> = {
  generic: { label: "Generic OpenAI-compatible", baseUrl: "", modelsUrl: "" },
  openai_legacy: {
    label: "OpenAI (Chat Completions)",
    baseUrl: "https://api.openai.com/v1",
    modelsUrl: "https://api.openai.com/v1/models",
  },
  openai_responses: {
    label: "OpenAI (Responses)",
    baseUrl: "https://api.openai.com/v1",
    modelsUrl: "https://api.openai.com/v1/models",
  },
  anthropic: {
    label: "Anthropic",
    baseUrl: "https://api.anthropic.com/v1",
    modelsUrl: "",
  },
  moonshot: {
    label: "Moonshot",
    baseUrl: "https://api.moonshot.cn/v1",
    modelsUrl: "https://api.moonshot.cn/v1/models",
  },
  deepseek: {
    label: "DeepSeek",
    baseUrl: "https://api.deepseek.com/v1",
    modelsUrl: "https://api.deepseek.com/v1/models",
  },
  ollama: {
    label: "Ollama",
    baseUrl: "http://localhost:11434",
    modelsUrl: "http://localhost:11434/v1/models",
  },
};

export function applyProviderPreset(
  current: ProviderDraft,
  nextKind: string,
): ProviderDraft {
  const previous = PROVIDER_PRESETS[current.kind];
  const next = PROVIDER_PRESETS[nextKind];
  const untouched = (value: string, previousValue: string | undefined) =>
    !value || value === previousValue;
  return {
    ...current,
    kind: nextKind,
    baseUrl: untouched(current.baseUrl, previous?.baseUrl)
      ? next?.baseUrl ?? ""
      : current.baseUrl,
    modelsUrl: untouched(current.modelsUrl, previous?.modelsUrl)
      ? next?.modelsUrl ?? ""
      : current.modelsUrl,
  };
}
```

- [ ] **Step 4: Implement ProviderForm and test result**

`ProviderForm` renders:
- Name field.
- Kind `Select` using `Object.entries(PROVIDER_PRESETS).map(([value, preset]) => ({ value, label: preset.label }))`; `onChange` calls `applyProviderPreset`.
- `HelpTip` on Kind, Base URL, API key, Models URL via `FormField help`.
- Base URL, API Key (`PasswordInput`), Models URL.
- A guidance paragraph for the current kind, sourced from `getHelpEntry`.
- `Test connection` button that calls `useTestProvider().mutateAsync({ kind: value.kind, base_url: value.baseUrl, models_url: value.modelsUrl, api_key: value.apiKey, provider_id: providerId })`.
- `ProviderTestResultView` below the button.

`ProviderTestResultView` renders:
- success: `Connected — 12 models in 420ms` plus a compact list of sample models.
- failure: `StatusChip tone="danger"` with the message and a help link to `provider.kind`.
- loading: the button `loading` state only.

Use `FormField error` for field-level URL issues from the test (`invalid_url`).

- [ ] **Step 5: Integrate ProvidersPage**

Refactor `ProviderFormDrawer` to keep `ProviderDraft` state and delegate field rendering/test UI to `ProviderForm`. `onSave` maps the draft to the existing `createProvider`/`updateProvider` payload. Remove the five individual `useState` fields.

Add `ProviderForm` guidance to `providers.module.css`:
```css
.guidance {
  color: var(--ab-text-muted);
  font-size: var(--ab-text-sm);
  margin: 0 0 var(--ab-space-3);
}
```

- [ ] **Step 6: Run tests and build**

Run:
```powershell
cd apps/web
bun run test -- src/pages/providers/providerPresets.test.ts
bun run build
```
Expected: PASS and build clean.

- [ ] **Step 7: Commit**

```powershell
git add apps/web/src/pages/providers apps/web/src/pages/ProvidersPage.tsx apps/web/src/pages/providers.module.css
git commit -m "feat(web): add provider presets and connection testing"
```

---

### Task 5: A2A card model, validation, and merge logic

**Files:**
- Create: `apps/web/src/pages/agents/a2aCard.ts`
- Test: `apps/web/src/pages/agents/a2aCard.test.ts`

**Interfaces:**
- Produces `A2ASkill`, `StructuredA2ACard`, `EMPTY_A2A_CARD`.
- Produces `toStructuredCard(raw, fallbackName)`, `mergeStructuredCard(raw, structured)`, `validateStructuredCard(card)`, `parseCardJson(text)`.

- [ ] **Step 1: Write failing tests**

```ts
import { describe, expect, it } from "vitest";

import {
  EMPTY_A2A_CARD,
  mergeStructuredCard,
  parseCardJson,
  toStructuredCard,
  validateStructuredCard,
} from "./a2aCard";

describe("a2aCard", () => {
  it("preserves unknown fields when merging", () => {
    const raw = { name: "Old", version: "1.0.0", securitySchemes: { api: {} } };
    const merged = mergeStructuredCard(raw, {
      ...EMPTY_A2A_CARD,
      name: "Reviewer",
      version: "1.2.0",
      skills: [{ id: "review", name: "Review", description: "", tags: [], examples: [] }],
    });
    expect(merged.name).toBe("Reviewer");
    expect(merged.securitySchemes).toEqual({ api: {} });
  });

  it("reads core fields from a raw card", () => {
    const card = toStructuredCard(
      {
        name: "Reviewer",
        description: "Reviews code",
        version: "1.0.0",
        capabilities: { streaming: true },
        skills: [{ id: "review", name: "Review" }],
      },
      "Fallback",
    );
    expect(card.name).toBe("Reviewer");
    expect(card.capabilities.streaming).toBe(true);
    expect(card.skills[0].id).toBe("review");
  });

  it("rejects duplicate skill ids and invalid URLs", () => {
    const errors = validateStructuredCard({
      ...EMPTY_A2A_CARD,
      name: "A",
      version: "1.0.0",
      documentationUrl: "not-a-url",
      skills: [
        { id: "x", name: "One", description: "", tags: [], examples: [] },
        { id: "x", name: "Two", description: "", tags: [], examples: [] },
      ],
    });
    expect(errors.documentationUrl).toBeTruthy();
    expect(errors.skills).toContain("unique");
  });

  it("parses valid JSON and rejects malformed JSON", () => {
    expect(parseCardJson('{"name":"A"}').card).toEqual({ name: "A" });
    expect(parseCardJson("{bad").error).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/web && bun run test -- src/pages/agents/a2aCard.test.ts`
Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement the pure module**

```ts
export type A2ASkill = {
  id: string;
  name: string;
  description: string;
  tags: string[];
  examples: string[];
};

export type StructuredA2ACard = {
  name: string;
  description: string;
  version: string;
  providerOrganization: string;
  providerUrl: string;
  documentationUrl: string;
  capabilities: {
    streaming: boolean;
    pushNotifications: boolean;
    stateTransitionHistory: boolean;
  };
  defaultInputModes: string[];
  defaultOutputModes: string[];
  skills: A2ASkill[];
};

export const EMPTY_A2A_CARD: StructuredA2ACard = {
  name: "",
  description: "",
  version: "1.0.0",
  providerOrganization: "",
  providerUrl: "",
  documentationUrl: "",
  capabilities: {
    streaming: true,
    pushNotifications: false,
    stateTransitionHistory: false,
  },
  defaultInputModes: ["text/plain"],
  defaultOutputModes: ["text/plain"],
  skills: [],
};

type RawCard = Record<string, unknown>;
const str = (value: unknown, fallback = "") =>
  typeof value === "string" ? value : fallback;
const strArray = (value: unknown) =>
  Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];

export function toStructuredCard(raw: RawCard | null, fallbackName: string): StructuredA2ACard {
  const r = raw ?? {};
  const capabilities =
    r.capabilities && typeof r.capabilities === "object"
      ? (r.capabilities as Record<string, unknown>)
      : {};
  const provider =
    r.provider && typeof r.provider === "object"
      ? (r.provider as Record<string, unknown>)
      : {};
  const skills = Array.isArray(r.skills) ? r.skills : [];
  return {
    name: str(r.name, fallbackName),
    description: str(r.description),
    version: str(r.version, "1.0.0"),
    providerOrganization: str(provider.organization),
    providerUrl: str(provider.url),
    documentationUrl: str(r.documentationUrl),
    capabilities: {
      streaming: capabilities.streaming === true,
      pushNotifications: capabilities.pushNotifications === true,
      stateTransitionHistory: capabilities.stateTransitionHistory === true,
    },
    defaultInputModes: strArray(r.defaultInputModes),
    defaultOutputModes: strArray(r.defaultOutputModes),
    skills: skills.map((skill) => {
      const s = (skill ?? {}) as Record<string, unknown>;
      return {
        id: str(s.id),
        name: str(s.name),
        description: str(s.description),
        tags: strArray(s.tags),
        examples: strArray(s.examples),
      };
    }),
  };
}

export function mergeStructuredCard(
  raw: RawCard | null,
  card: StructuredA2ACard,
): RawCard {
  const next: RawCard = { ...(raw ?? {}) };
  next.name = card.name.trim();
  next.description = card.description.trim();
  next.version = card.version.trim();
  if (card.providerOrganization || card.providerUrl) {
    next.provider = {
      organization: card.providerOrganization.trim(),
      url: card.providerUrl.trim(),
    };
  }
  if (card.documentationUrl) next.documentationUrl = card.documentationUrl.trim();
  next.capabilities = { ...card.capabilities };
  next.defaultInputModes = card.defaultInputModes;
  next.defaultOutputModes = card.defaultOutputModes;
  next.skills = card.skills.map((skill) => ({
    id: skill.id.trim(),
    name: skill.name.trim(),
    description: skill.description.trim(),
    tags: skill.tags,
    examples: skill.examples,
  }));
  return next;
}

export function validateStructuredCard(card: StructuredA2ACard) {
  const errors: Record<string, string> = {};
  if (!card.name.trim()) errors.name = "Name is required.";
  if (!/^\d+\.\d+\.\d+/.test(card.version.trim())) {
    errors.version = "Use a version such as 1.0.0.";
  }
  const url = (value: string) => !value || /^https?:\/\/\S+$/i.test(value);
  if (!url(card.providerUrl)) errors.providerUrl = "Use an http/https URL.";
  if (!url(card.documentationUrl)) {
    errors.documentationUrl = "Use an http/https URL.";
  }
  const ids = card.skills.map((skill) => skill.id.trim());
  if (ids.some((id) => !id)) errors.skills = "Every skill needs an id.";
  else if (new Set(ids).size !== ids.length) {
    errors.skills = "Skill ids must be unique.";
  }
  if (card.skills.some((skill) => !skill.name.trim())) {
    errors.skills = "Every skill needs a name.";
  }
  return errors;
}

export function parseCardJson(text: string):
  | { card: RawCard; error?: undefined }
  | { card?: undefined; error: string } {
  try {
    const parsed = JSON.parse(text);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { error: "The card must be a JSON object." };
    }
    return { card: parsed as RawCard };
  } catch (error) {
    return { error: error instanceof Error ? error.message : "Invalid JSON." };
  }
}
```

- [ ] **Step 4: Run tests**

Run: `cd apps/web && bun run test -- src/pages/agents/a2aCard.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src/pages/agents/a2aCard.ts apps/web/src/pages/agents/a2aCard.test.ts
git commit -m "feat(web): add A2A card model and validation"
```

---

### Task 6: Structured A2A editor UI

**Files:**
- Modify: `apps/web/src/pages/agents/AgentCardModal.tsx`
- Create: `apps/web/src/pages/agents/A2ASkillsEditor.tsx`
- Test: `apps/web/src/pages/agents/AgentCardModal.test.tsx`

**Interfaces:**
- Consumes Task 5 functions.
- Produces `AgentCardModal` with `Structured`/`JSON` tabs and `A2ASkillsEditor({skills,onChange,error})`.

- [ ] **Step 1: Write the failing UI test**

```tsx
import { fireEvent, screen } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("../../api/queries", () => ({
  useAgentCard: () => ({
    data: { name: "Reviewer", description: "Reviews", version: "1.0.0", skills: [] },
  }),
  useSetAgentCard: () => ({ mutateAsync: vi.fn() }),
  useDeleteAgentCard: () => ({ mutateAsync: vi.fn() }),
}));

import { AgentCardModal } from "./AgentCardModal";
import { renderWithTheme } from "../../test/render";
import { HelpProvider } from "../../help/HelpProvider";

test("edits core A2A fields and switches to JSON", () => {
  renderWithTheme(
    <HelpProvider>
      <AgentCardModal name="Reviewer" onClose={() => {}} />
    </HelpProvider>,
  );
  expect(screen.getByLabelText("Agent card name")).toHaveValue("Reviewer");
  expect(screen.getByText("Capabilities")).toBeTruthy();
  fireEvent.click(screen.getByRole("tab", { name: "JSON" }));
  expect((screen.getByLabelText("Agent card JSON") as HTMLTextAreaElement).value).toContain(
    "Reviewer",
  );
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/web && bun run test -- src/pages/agents/AgentCardModal.test.tsx`
Expected: FAIL because the structured UI does not exist.

- [ ] **Step 3: Implement skills editor**

`A2ASkillsEditor` renders a list of rows with inputs:
- `TextInput aria-label={`Skill ${index + 1} id`}`
- `TextInput aria-label={`Skill ${index + 1} name`}`
- `Textarea aria-label={`Skill ${index + 1} description`}`
- `TextInput aria-label={`Skill ${index + 1} tags`}` and split `value.split(",").map(t => t.trim()).filter(Boolean)`.
- `Textarea aria-label={`Skill ${index + 1} examples`}` and split on newlines.
- Up/down/remove `IconButton`s.
- `Add skill` `Button`.

Props: `{ skills: A2ASkill[]; onChange: (skills: A2ASkill[]) => void; error?: string }`.

- [ ] **Step 4: Implement the modal**

Use local state:
```ts
const [rawCard, setRawCard] = useState<Record<string, unknown> | null>(card ?? null);
const [structured, setStructured] = useState<StructuredA2ACard>(() =>
  toStructuredCard(card ?? null, name),
);
const [jsonText, setJsonText] = useState(() =>
  JSON.stringify(card ?? mergeStructuredCard(null, structured), null, 2),
);
const [tab, setTab] = useState<string | null>("structured");
const [errors, setErrors] = useState<Record<string, string>>({});
const [jsonError, setJsonError] = useState<string | null>(null);
```

Render:
- `Tabs` with `Structured` and `JSON`.
- Structured fields with `FormField` and `HelpTip`: name, description, version, provider organization/url, documentation URL.
- Capabilities: three `Checkbox` controls labeled `Streaming`, `Push notifications`, `State transition history`.
- Input/output modes: `MultiSelect data={["text/plain","application/json"]}` with `searchable` and `creatable`.
- `A2ASkillsEditor`.
- JSON `Textarea aria-label="Agent card JSON"` with `jsonText`; `onChange` reparses and sets `jsonError`.
- Save button uses:
```ts
const cardToSave =
  tab === "json"
    ? parseCardJson(jsonText).card
    : mergeStructuredCard(rawCard, structured);
const nextErrors = tab === "structured" ? validateStructuredCard(structured) : {};
setErrors(nextErrors);
if (!cardToSave || Object.keys(nextErrors).length > 0 || jsonError) return;
await save.mutateAsync({ name, card: cardToSave });
```
- On successful JSON parse, update `rawCard` and `structured` via `toStructuredCard`.
- Remove/Delete remains a separate danger action.

- [ ] **Step 5: Run tests and build**

Run:
```powershell
cd apps/web
bun run test -- src/pages/agents/AgentCardModal.test.tsx
bun run build
```
Expected: PASS and build clean.

- [ ] **Step 6: Commit**

```powershell
git add apps/web/src/pages/agents/AgentCardModal.tsx apps/web/src/pages/agents/A2ASkillsEditor.tsx apps/web/src/pages/agents/AgentCardModal.test.tsx
git commit -m "feat(web): add structured A2A card editor"
```

---

### Task 7: Tool catalog and grouped tools editor

**Files:**
- Create: `apps/web/src/pages/agents/toolCatalog.ts`
- Create: `apps/web/src/pages/agents/AgentToolsEditor.tsx`
- Test: `apps/web/src/pages/agents/toolCatalog.test.ts`
- Test: `apps/web/src/pages/agents/AgentToolsEditor.test.tsx`

**Interfaces:**
- Produces `ToolCategory`, `ToolMeta`, `TOOL_META`, `TOOL_GROUPS`.
- Produces `AgentToolsEditor({ value, onChange })`.

- [ ] **Step 1: Write failing catalog and editor tests**

```ts
import { describe, expect, it } from "vitest";
import { TOOL_META, TOOL_GROUPS } from "./toolCatalog";

it("catalogs every selectable tool", () => {
  expect(TOOL_META.read_text_file.category).toBe("filesystem-read");
  expect(TOOL_META.write_file.risk).toBe("write");
  expect(TOOL_META.web_search.category).toBe("web");
  expect(TOOL_GROUPS.map((group) => group.category)).toContain("terminal");
});
```

```tsx
import { fireEvent, screen } from "@testing-library/react";
import { useState } from "react";
import { AgentToolsEditor } from "./AgentToolsEditor";
import { renderWithTheme } from "../../test/render";

function Harness() {
  const [value, setValue] = useState<string[]>([]);
  return <AgentToolsEditor value={value} onChange={setValue} />;
}

test("filters and selects tools", () => {
  renderWithTheme(<Harness />);
  fireEvent.change(screen.getByLabelText("Search tools"), {
    target: { value: "delete" },
  });
  expect(screen.getByText("delete_path")).toBeTruthy();
  expect(screen.queryByText("web_search")).toBeNull();
  fireEvent.click(screen.getByRole("checkbox", { name: /delete_path/i }));
  expect(screen.getByText("1 selected")).toBeTruthy();
});
```

- [ ] **Step 2: Run to verify failure**

Run:
```powershell
cd apps/web
bun run test -- src/pages/agents/toolCatalog.test.ts src/pages/agents/AgentToolsEditor.test.tsx
```
Expected: FAIL because the modules do not exist.

- [ ] **Step 3: Implement the catalog**

```ts
export type ToolCategory =
  | "filesystem-read"
  | "filesystem-write"
  | "web"
  | "terminal";

export type ToolMeta = {
  name: string;
  label: string;
  description: string;
  category: ToolCategory;
  risk: "read" | "write";
};

export const TOOL_META: Record<string, ToolMeta> = {
  read_text_file: { name: "read_text_file", label: "Read text file", description: "Read a text file from the project.", category: "filesystem-read", risk: "read" },
  read_media_file: { name: "read_media_file", label: "Read media file", description: "Read an image, audio, or video file.", category: "filesystem-read", risk: "read" },
  read_multiple_files: { name: "read_multiple_files", label: "Read multiple files", description: "Read several files in one call.", category: "filesystem-read", risk: "read" },
  list_directory: { name: "list_directory", label: "List directory", description: "List files and folders in a directory.", category: "filesystem-read", risk: "read" },
  list_directory_with_sizes: { name: "list_directory_with_sizes", label: "List directory with sizes", description: "List entries with file sizes.", category: "filesystem-read", risk: "read" },
  directory_tree: { name: "directory_tree", label: "Directory tree", description: "Show a recursive directory tree.", category: "filesystem-read", risk: "read" },
  search_files: { name: "search_files", label: "Search files", description: "Find files by name.", category: "filesystem-read", risk: "read" },
  get_file_info: { name: "get_file_info", label: "File info", description: "Read file metadata.", category: "filesystem-read", risk: "read" },
  list_allowed_directories: { name: "list_allowed_directories", label: "Allowed roots", description: "Show directories the agent may access.", category: "filesystem-read", risk: "read" },
  write_file: { name: "write_file", label: "Write file", description: "Create or overwrite a file.", category: "filesystem-write", risk: "write" },
  append_file: { name: "append_file", label: "Append file", description: "Append content to a file.", category: "filesystem-write", risk: "write" },
  edit_file: { name: "edit_file", label: "Edit file", description: "Apply a targeted edit to a file.", category: "filesystem-write", risk: "write" },
  create_directory: { name: "create_directory", label: "Create directory", description: "Create a directory.", category: "filesystem-write", risk: "write" },
  move_file: { name: "move_file", label: "Move file", description: "Move or rename a file.", category: "filesystem-write", risk: "write" },
  copy_file: { name: "copy_file", label: "Copy file", description: "Copy a file.", category: "filesystem-write", risk: "write" },
  delete_path: { name: "delete_path", label: "Delete path", description: "Delete a file or directory.", category: "filesystem-write", risk: "write" },
  web_search: { name: "web_search", label: "Web search", description: "Search the web.", category: "web", risk: "read" },
  fetch_url: { name: "fetch_url", label: "Fetch URL", description: "Fetch content from a URL.", category: "web", risk: "read" },
  terminal: { name: "terminal", label: "Terminal", description: "Run shell commands and manage jobs.", category: "terminal", risk: "write" },
};

export const TOOL_GROUPS = [
  { category: "filesystem-read", title: "Filesystem read", description: "Inspect project files." },
  { category: "filesystem-write", title: "Filesystem write", description: "Modify files and directories." },
  { category: "web", title: "Web", description: "Search and fetch web content." },
  { category: "terminal", title: "Terminal", description: "Run commands and manage jobs." },
] as const;
```

- [ ] **Step 4: Implement AgentToolsEditor**

Render:
- Header with `Search tools` `TextInput`, `Select all`/`Clear` buttons, `1 selected` `Badge`.
- `Switch`/`Checkbox` labeled `Show advanced`; advanced includes the terminal group and destructive tools (`delete_path`, `move_file`, `copy_file`).
- Group panels with `Section title={group.title}`, description, and checkboxes using `TOOL_META[name].label` and a `Badge tone={risk === "write" ? "warning" : "neutral"}`.
- Toggling a tool updates `value` without duplicates.

- [ ] **Step 5: Replace the flat tool grid in `AgentCreateDrawer`**

Replace the `NATIVE_TOOLS.map` block with:
```tsx
<AgentToolsEditor value={tools} onChange={setTools} />
```
Keep `buildToolBindings(tools)` unchanged.

- [ ] **Step 6: Run tests and build**

Run:
```powershell
cd apps/web
bun run test -- src/pages/agents/toolCatalog.test.ts src/pages/agents/AgentToolsEditor.test.tsx
bun run build
```
Expected: PASS and build clean.

- [ ] **Step 7: Commit**

```powershell
git add apps/web/src/pages/agents/toolCatalog.ts apps/web/src/pages/agents/AgentToolsEditor.tsx apps/web/src/pages/agents/toolCatalog.test.ts apps/web/src/pages/agents/AgentToolsEditor.test.tsx apps/web/src/pages/agents/AgentCreateDrawer.tsx
git commit -m "feat(web): add grouped agent tools editor"
```

---

### Task 8: Mode and MCP editors with validation

**Files:**
- Create: `apps/web/src/pages/agents/agentFormValidation.ts`
- Create: `apps/web/src/pages/agents/AgentModesEditor.tsx`
- Create: `apps/web/src/pages/agents/AgentMcpEditor.tsx`
- Test: `apps/web/src/pages/agents/agentFormValidation.test.ts`
- Test: `apps/web/src/pages/agents/AgentModesEditor.test.tsx`
- Modify: `apps/web/src/pages/agents/AgentCreateDrawer.tsx`

**Interfaces:**
- Produces `AgentMode`, `validateModes(modes)`, `validateMcpUrl(url)`.
- Produces `AgentModesEditor({ value, onChange, error })`, `AgentMcpEditor({ value, onChange, error })`.

- [ ] **Step 1: Write failing validation tests**

```ts
import { describe, expect, it } from "vitest";
import { validateMcpUrl, validateModes } from "./agentFormValidation";

describe("agent form validation", () => {
  it("rejects blank and duplicate modes", () => {
    expect(validateModes([{ name: " ", write: false }])).toContain("blank");
    expect(
      validateModes([
        { name: "ask", write: false },
        { name: "ask", write: true },
      ]),
    ).toContain("unique");
  });

  it("accepts http and https MCP URLs", () => {
    expect(validateMcpUrl("https://example.test/mcp")).toBeNull();
    expect(validateMcpUrl("http://localhost:9000/mcp")).toBeNull();
    expect(validateMcpUrl("ftp://example.test")).toContain("http");
  });
});
```

Also create `AgentModesEditor.test.tsx`:

```tsx
import { fireEvent, screen } from "@testing-library/react";
import { useState } from "react";
import { AgentModesEditor } from "./AgentModesEditor";
import { renderWithTheme } from "../../test/render";

function Harness() {
  const [value, setValue] = useState([{ name: "ask", write: false }]);
  return <AgentModesEditor value={value} onChange={setValue} />;
}

test("adds and removes a mode", () => {
  renderWithTheme(<Harness />);
  fireEvent.click(screen.getByRole("button", { name: "Add mode" }));
  expect(screen.getByLabelText("Mode 2 name")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Remove mode 1" }));
  expect(screen.getByDisplayValue("ask")).toBeTruthy();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/web && bun run test -- src/pages/agents/agentFormValidation.test.ts src/pages/agents/AgentModesEditor.test.tsx`
Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement validation**

```ts
export type AgentMode = { name: string; write: boolean };

export function validateModes(modes: AgentMode[]): string | null {
  if (modes.some((mode) => !mode.name.trim())) return "Mode names cannot be blank.";
  const names = modes.map((mode) => mode.name.trim().toLowerCase());
  if (new Set(names).size !== names.length) return "Mode names must be unique.";
  return null;
}

export function validateMcpUrl(value: string): string | null {
  try {
    const url = new URL(value);
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      return "MCP URLs must use http or https.";
    }
    return null;
  } catch {
    return "Enter a valid http/https MCP URL.";
  }
}
```

- [ ] **Step 4: Implement editors**

`AgentModesEditor`:
- Renders each mode as a bordered row with `TextInput aria-label={`Mode ${index + 1} name`}`, `Checkbox label="Write enabled"`, help text explaining write tools, `Remove` button, and `Add mode`.
- Calls `onChange` for every edit.
- Shows `error` in a `FormField`-style inline alert.

`AgentMcpEditor`:
- Renders added servers as rows with `<code>{url}</code>`, `Remove`, and a `StatusChip tone="danger"` when `validateMcpUrl(url)` is non-null.
- Input has `aria-label="MCP server URL"`, placeholder `https://server/mcp`, `Add` button disabled when invalid.
- Shows help text: remote MCP endpoint, transport/auth handled by the server, failures surface as tool errors.
- Accepts `error?: string`.

- [ ] **Step 5: Integrate into AgentCreateDrawer**

Replace the MCP inline form/list and modes block with:
```tsx
<AgentMcpEditor
  value={mcpServers}
  onChange={setMcpServers}
  error={mcpError ?? undefined}
/>
<AgentModesEditor
  value={modes}
  onChange={setModes}
  error={modesError ?? undefined}
/>
```
Compute errors before `onCreate`:
```ts
const modesError = validateModes(modes);
const mcpError = mcpServers.map(validateMcpUrl).find(Boolean) ?? null;
if (modesError || mcpError || !modelRef) return;
```
Render a `HelpTip id="agent.modes"`/`agent.mcp"` beside the section titles.

- [ ] **Step 6: Run tests and build**

Run:
```powershell
cd apps/web
bun run test -- src/pages/agents/agentFormValidation.test.ts src/pages/agents/AgentModesEditor.test.tsx
bun run build
```
Expected: PASS and build clean.

- [ ] **Step 7: Commit**

```powershell
git add apps/web/src/pages/agents/agentFormValidation.ts apps/web/src/pages/agents/AgentModesEditor.tsx apps/web/src/pages/agents/AgentMcpEditor.tsx apps/web/src/pages/agents/agentFormValidation.test.ts apps/web/src/pages/agents/AgentModesEditor.test.tsx apps/web/src/pages/agents/AgentCreateDrawer.tsx
git commit -m "feat(web): add mode and MCP editors"
```

---

### Task 9: API scope help, recommendations, and copy feedback

**Files:**
- Create: `apps/web/src/pages/api-keys/scopeHelp.ts`
- Create: `apps/web/src/pages/api-keys/ScopePicker.tsx`
- Test: `apps/web/src/pages/api-keys/scopeHelp.test.ts`
- Test: `apps/web/src/pages/api-keys/ScopePicker.test.tsx`
- Modify: `apps/web/src/pages/ApiKeysPage.tsx`
- Modify: `apps/web/src/pages/api-keys.module.css`

**Interfaces:**
- Produces `SCOPE_HELP`, `RECOMMENDED_SCOPES`, `describeScope(scope)`.
- Produces `ScopePicker({ available, value, onChange })`.

- [ ] **Step 1: Write failing tests**

```ts
import { describe, expect, it } from "vitest";
import { RECOMMENDED_SCOPES, describeScope } from "./scopeHelp";

it("describes known scopes and falls back safely", () => {
  expect(describeScope("sessions:create")).toContain("Create");
  expect(describeScope("custom:thing")).toBe("custom:thing");
  expect(RECOMMENDED_SCOPES).toContain("providers:read");
});
```

```tsx
import { fireEvent, screen } from "@testing-library/react";
import { useState } from "react";
import { ScopePicker } from "./ScopePicker";
import { renderWithTheme } from "../../test/render";

function Harness() {
  const [value, setValue] = useState<string[]>([]);
  return (
    <ScopePicker
      available={["sessions:create", "providers:read", "api_keys:manage"]}
      value={value}
      onChange={setValue}
    />
  );
}

test("warns when no scopes are selected and recommends defaults", () => {
  renderWithTheme(<Harness />);
  expect(screen.getByText(/unusable/i)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Use recommended" }));
  expect(screen.getByText("2 selected")).toBeTruthy();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/web && bun run test -- src/pages/api-keys/scopeHelp.test.ts src/pages/api-keys/ScopePicker.test.tsx`
Expected: FAIL because the modules do not exist.

- [ ] **Step 3: Implement scope help**

```ts
export const SCOPE_HELP: Record<string, string> = {
  "agents:create": "Create and update agents.",
  "agents:read": "View agents and their A2A cards.",
  "agents:delete": "Delete agents.",
  "providers:create": "Create and update providers.",
  "providers:read": "View providers.",
  "providers:delete": "Delete providers.",
  "providers:list-models": "Fetch the provider model list.",
  "projects:create": "Create and update projects.",
  "projects:read": "View projects.",
  "projects:delete": "Delete projects.",
  "sessions:create": "Send messages and create sessions.",
  "sessions:read": "View sessions, messages, and attachments.",
  "users:manage": "Manage users.",
  "roles:manage": "Manage roles and permissions.",
  "api_keys:manage": "Create and revoke API keys.",
};

export const RECOMMENDED_SCOPES = [
  "providers:read",
  "sessions:read",
];

export function describeScope(scope: string): string {
  return SCOPE_HELP[scope] ?? scope;
}
```

`ScopePicker` groups known scopes by prefix before `:` (`Agents`, `Providers`, `Projects`, `Sessions`, `Admin`, `Other`) and renders grouped `Checkbox` rows with description text and a `Use recommended` button. Show `No scopes selected. The key cannot perform authorized work.` when `value.length === 0`.

- [ ] **Step 4: Integrate ApiKeysPage**

- Replace `MultiSelect` for scopes with `ScopePicker`.
- Add `HelpTip id="api.scopes"` next to the Scopes label.
- Add a warning `StatusChip tone="warning"` above `Create key` when `scopes.length === 0`.
- Keep the creation disabled only by the existing mutation loading state; allow creation but show the warning.
- In the created-key modal, add a `ref` and `useEffect` that calls `select()` when `created` changes, plus a `HelpTip id="api.scopes"`.

- [ ] **Step 5: Run tests and build**

Run:
```powershell
cd apps/web
bun run test -- src/pages/api-keys/scopeHelp.test.ts src/pages/api-keys/ScopePicker.test.tsx
bun run build
```
Expected: PASS and build clean.

- [ ] **Step 6: Commit**

```powershell
git add apps/web/src/pages/api-keys/scopeHelp.ts apps/web/src/pages/api-keys/ScopePicker.tsx apps/web/src/pages/api-keys/scopeHelp.test.ts apps/web/src/pages/api-keys/ScopePicker.test.tsx apps/web/src/pages/ApiKeysPage.tsx apps/web/src/pages/api-keys.module.css
git commit -m "feat(web): add API scope guidance"
```

---

### Task 10: Guided empty states

**Files:**
- Create: `apps/web/src/design-system/patterns/GuidedEmptyState.tsx`
- Test: `apps/web/src/design-system/patterns/GuidedEmptyState.test.tsx`
- Modify: `apps/web/src/pages/ProvidersPage.tsx`
- Modify: `apps/web/src/pages/agents/AgentList.tsx`
- Modify: `apps/web/src/pages/ApiKeysPage.tsx`
- Modify: `apps/web/src/pages/SkillsPage.tsx`

**Interfaces:**
- Produces `GuidedEmptyState({ icon, title, description, action, helpId })`.

- [ ] **Step 1: Write the failing component test**

```tsx
import { fireEvent, screen } from "@testing-library/react";
import { RiRobot2Line } from "@remixicon/react";
import { GuidedEmptyState } from "./GuidedEmptyState";
import { HelpProvider } from "../../help/HelpProvider";
import { renderWithTheme } from "../../test/render";

test("shows a CTA and help link", () => {
  renderWithTheme(
    <HelpProvider>
      <GuidedEmptyState
        icon={RiRobot2Line}
        title="No agents"
        description="Create an agent to start."
        action={<button type="button">Create agent</button>}
        helpId="agent.tools"
      />
    </HelpProvider>,
  );
  expect(screen.getByText("No agents")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Learn about Agent tools" }));
  expect(screen.getByRole("dialog", { name: "Agent tools" })).toBeTruthy();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/web && bun run test -- src/design-system/patterns/GuidedEmptyState.test.tsx`
Expected: FAIL because the component does not exist.

- [ ] **Step 3: Implement GuidedEmptyState**

Wrap `EmptyStatePanel`, include `action`, and add a secondary `HelpLink` button:
```tsx
<HelpLink id={helpId}>Learn about {getHelpEntry(helpId).title}</HelpLink>
```

- [ ] **Step 4: Replace page empty states**

- Providers: if `providers?.length === 0`, render `GuidedEmptyState` with `helpId="provider.kind"` and CTA opening the provider drawer; do not render an empty table.
- Agents: replace the existing `EmptyStatePanel` with `GuidedEmptyState`, `helpId="agent.tools"`, CTA `Create your first agent`.
- API Keys: when `keys?.length === 0`, render `GuidedEmptyState` below the creation panel with `helpId="api.scopes"` and CTA focusing/creating a key.
- Skills: when `skills?.length === 0`, replace the table with `GuidedEmptyState`, `helpId="skills.overview"`, and the CTA “Create your first skill”.

- [ ] **Step 5: Run tests and build**

Run:
```powershell
cd apps/web
bun run test -- src/design-system/patterns/GuidedEmptyState.test.tsx src/pages/AgentsPage.test.tsx src/pages/ProvidersPage.test.tsx
bun run build
```
Expected: PASS and build clean.

- [ ] **Step 6: Commit**

```powershell
git add apps/web/src/design-system/patterns/GuidedEmptyState.tsx apps/web/src/design-system/patterns/GuidedEmptyState.test.tsx apps/web/src/pages/ProvidersPage.tsx apps/web/src/pages/agents/AgentList.tsx apps/web/src/pages/ApiKeysPage.tsx apps/web/src/pages/SkillsPage.tsx
git commit -m "feat(web): add guided empty states"
```

---

### Task 11: Onboarding progress and Home checklist

**Files:**
- Create: `apps/web/src/onboarding/onboardingProgress.ts`
- Create: `apps/web/src/onboarding/HomeChecklist.tsx`
- Test: `apps/web/src/onboarding/onboardingProgress.test.ts`
- Test: `apps/web/src/onboarding/HomeChecklist.test.tsx`

**Interfaces:**
- Produces `OnboardingStep`, `OnboardingSnapshot`, `OnboardingProgress`, `deriveOnboardingProgress(snapshot)`.
- Produces `HomeChecklist({ progress, onOpenStep })`.

- [ ] **Step 1: Write failing progress tests**

```ts
import { describe, expect, it } from "vitest";
import { deriveOnboardingProgress } from "./onboardingProgress";

it("reports the first incomplete step", () => {
  const progress = deriveOnboardingProgress({
    providers: 1,
    models: 1,
    agents: 0,
    sessions: 0,
  });
  expect(progress.items.find((item) => item.id === "provider")?.done).toBe(true);
  expect(progress.nextStep).toBe("agent");
  expect(progress.complete).toBe(false);
});

it("is complete with all resources", () => {
  const progress = deriveOnboardingProgress({
    providers: 1,
    models: 1,
    agents: 1,
    sessions: 1,
  });
  expect(progress.complete).toBe(true);
  expect(progress.nextStep).toBe("done");
});
```

Also create `HomeChecklist.test.tsx`:

```tsx
import { fireEvent, screen } from "@testing-library/react";
import { vi } from "vitest";
import { HomeChecklist } from "./HomeChecklist";
import { deriveOnboardingProgress } from "./onboardingProgress";
import { renderWithTheme } from "../test/render";

test("opens the first incomplete step", () => {
  const progress = deriveOnboardingProgress({
    providers: 1,
    models: 1,
    agents: 0,
    sessions: 0,
  });
  const onOpenStep = vi.fn();
  renderWithTheme(<HomeChecklist progress={progress} onOpenStep={onOpenStep} />);
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));
  expect(onOpenStep).toHaveBeenCalledWith("agent");
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/web && bun run test -- src/onboarding/onboardingProgress.test.ts src/onboarding/HomeChecklist.test.tsx`
Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement progress**

```ts
export type OnboardingStep = "welcome" | "provider" | "agent" | "session" | "done";

export type OnboardingSnapshot = {
  providers: number;
  models: number;
  agents: number;
  sessions: number;
};

export type OnboardingProgress = {
  items: { id: "provider" | "model" | "agent" | "session"; label: string; done: boolean }[];
  nextStep: OnboardingStep;
  complete: boolean;
};

export function deriveOnboardingProgress(
  snapshot: OnboardingSnapshot,
): OnboardingProgress {
  const items = [
    { id: "provider" as const, label: "Provider connected", done: snapshot.providers > 0 },
    { id: "model" as const, label: "Model available", done: snapshot.models > 0 },
    { id: "agent" as const, label: "Agent ready", done: snapshot.agents > 0 },
    { id: "session" as const, label: "First session started", done: snapshot.sessions > 0 },
  ];
  const next = items.find((item) => !item.done);
  const map = { provider: "provider", model: "provider", agent: "agent", session: "session" } as const;
  return {
    items,
    nextStep: next ? map[next.id] : "done",
    complete: !next,
  };
}
```

- [ ] **Step 4: Implement HomeChecklist**

`HomeChecklist({ progress, onOpenStep })` renders a `Panel` with:
- title `Setup`
- completion text `{done} of 4 complete`
- list items with `StatusChip tone={done ? "success" : "neutral"}` and a `Button variant="light"` labeled `Continue` on the first incomplete item calling `onOpenStep(progress.nextStep)`.
- when complete, a `StatusChip tone="success">ready</StatusChip>` and no CTA.

- [ ] **Step 5: Run tests**

Run:
```powershell
cd apps/web
bun run test -- src/onboarding/onboardingProgress.test.ts src/onboarding/HomeChecklist.test.tsx
```
Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add apps/web/src/onboarding/onboardingProgress.ts apps/web/src/onboarding/HomeChecklist.tsx apps/web/src/onboarding/onboardingProgress.test.ts apps/web/src/onboarding/HomeChecklist.test.tsx
git commit -m "feat(web): add onboarding progress and checklist"
```

---

### Task 12: First-run onboarding wizard

**Files:**
- Create: `apps/web/src/onboarding/useOnboardingPreference.ts`
- Create: `apps/web/src/onboarding/OnboardingWizard.tsx`
- Create: `apps/web/src/onboarding/onboarding.module.css`
- Test: `apps/web/src/onboarding/OnboardingWizard.test.tsx`

**Interfaces:**
- Produces `useOnboardingPreference()` with `{ dismissed, dismiss, reset }` backed by `localStorage` key `agentbox-onboarding-v1`.
- Produces `OnboardingWizard({ opened, initialStep, onClose, onDone })`.
- Consumes `ProviderForm`, `useCreateProvider`, `useRefreshModels`, `useCreateAgent`, `useCreateProject`, `useCreateSession`.

- [ ] **Step 1: Write the failing wizard test**

```tsx
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi } from "vitest";

vi.mock("../api/queries", () => ({
  useModels: () => ({ data: [{ id: "m1", name: "model-a", provider_id: "p1" }] }),
  useProviders: () => ({ data: [{ id: "p1", name: "provider-a", kind: "generic" }] }),
  useAgents: () => ({ data: [] }),
  useCreateProvider: () => ({ mutateAsync: vi.fn(async () => ({ id: "p1" })), isPending: false }),
  useRefreshModels: () => ({ mutateAsync: vi.fn(async () => []) }),
  useCreateAgent: () => ({ mutateAsync: vi.fn(async () => ({ name: "agent-a" })), isPending: false }),
  useCreateProject: () => ({ mutateAsync: vi.fn(async () => ({ id: "prj1" })), isPending: false }),
  useCreateSession: () => ({ mutateAsync: vi.fn(async () => ({ id: "s1" })), isPending: false }),
}));

import { OnboardingWizard } from "./OnboardingWizard";
import { renderWithTheme } from "../test/render";

test("moves from welcome to provider setup and can be skipped", async () => {
  const onClose = vi.fn();
  renderWithTheme(
    <QueryClientProvider client={new QueryClient()}>
      <OnboardingWizard opened initialStep="welcome" onClose={onClose} onDone={() => {}} />
    </QueryClientProvider>,
  );
  expect(screen.getByText("Connect your first provider")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Skip setup" }));
  expect(onClose).toHaveBeenCalled();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/web && bun run test -- src/onboarding/OnboardingWizard.test.tsx`
Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement preference hook**

```ts
import { useState } from "react";

const KEY = "agentbox-onboarding-v1";

function read() {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "{}") as { dismissed?: boolean };
  } catch {
    return {};
  }
}

export function useOnboardingPreference() {
  const [dismissed, setDismissed] = useState(() => read().dismissed === true);
  const dismiss = () => {
    localStorage.setItem(KEY, JSON.stringify({ dismissed: true }));
    setDismissed(true);
  };
  const reset = () => {
    localStorage.removeItem(KEY);
    setDismissed(false);
  };
  return { dismissed, dismiss, reset };
}
```

- [ ] **Step 4: Implement the wizard**

Use `Modal` with `size="lg"`, `closeOnClickOutside={false}` and a title `Set up Agentbox`.

State:
```ts
const [step, setStep] = useState<OnboardingStep>(initialStep);
const [draft, setDraft] = useState<ProviderDraft>(EMPTY_PROVIDER_DRAFT);
const [createdProviderId, setCreatedProviderId] = useState<string | null>(null);
const [agentName, setAgentName] = useState("");
const [agentDescription, setAgentDescription] = useState("");
const [agentInstructions, setAgentInstructions] = useState("You are a helpful coding agent.");
const [agentModel, setAgentModel] = useState<string | null>(null);
const [agentTools, setAgentTools] = useState<string[]>(["read_text_file", "read_multiple_files", "list_directory", "search_files", "get_file_info"]);
const [createdAgent, setCreatedAgent] = useState<string | null>(null);
const [projectName, setProjectName] = useState("My project");
const [projectPath, setProjectPath] = useState(".");
const [error, setError] = useState<string | null>(null);
```

Render each step:
- Welcome: title `Connect your first provider`, short paragraph, `Get started`, `Skip setup`.
- Provider: `ProviderForm`, `Create provider` button; on success call `useRefreshModels().mutateAsync(created.id)`, store id, next step. On error set `error`.
- Agent: name/description/instructions `TextInput`/`Textarea`, model `Select` from `useModels()` labels `provider — model`, read-only tools help note, `Create agent`. The create call sets `tool_bindings: buildToolBindings(agentTools)`, `mode_definitions: [{ name: "ask", flags: { write: false } }, { name: "agent", flags: { write: true } }]`, and `sub_agent_ids: []`.
- Session: project name/path, agent `Select`, `Create project and start session`; create project then session, call `onDone(session.id)` and `onClose()`.
- Done: checkmark, `Open Home` button.

Every step renders a `Skip setup` button that calls `onClose()`. Back button goes to the previous step.

- [ ] **Step 5: Run tests and build**

Run:
```powershell
cd apps/web
bun run test -- src/onboarding/OnboardingWizard.test.tsx
bun run build
```
Expected: PASS and build clean.

- [ ] **Step 6: Commit**

```powershell
git add apps/web/src/onboarding/useOnboardingPreference.ts apps/web/src/onboarding/OnboardingWizard.tsx apps/web/src/onboarding/onboarding.module.css apps/web/src/onboarding/OnboardingWizard.test.tsx
git commit -m "feat(web): add first-run onboarding wizard"
```

---

### Task 13: Home integration and auto-launch

**Files:**
- Modify: `apps/web/src/pages/HomePage.tsx`
- Modify: `apps/web/src/pages/home.module.css`
- Test: `apps/web/src/pages/HomePage.test.tsx`

**Interfaces:**
- Consumes `deriveOnboardingProgress`, `HomeChecklist`, `OnboardingWizard`, `useOnboardingPreference`.
- Produces auto-launch when `providers === 0 && agents === 0 && !dismissed`.

- [ ] **Step 1: Write the failing Home test**

```tsx
import { screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { renderWithTheme as render } from "../test/render";

vi.mock("../api/queries", () => ({
  useProjects: () => ({ data: [] }),
  useSessions: () => ({ data: [] }),
  useAgents: () => ({ data: [] }),
  useProviders: () => ({ data: [] }),
  useModels: () => ({ data: [] }),
}));

import { HomePage } from "./HomePage";

test("shows the setup checklist", () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(screen.getByText("Provider connected")).toBeTruthy();
  expect(screen.getByText("Agent ready")).toBeTruthy();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/web && bun run test -- src/pages/HomePage.test.tsx`
Expected: FAIL because the Home page does not render the checklist.

- [ ] **Step 3: Implement Home integration**

- Add `useProviders`, `useModels` to HomePage.
- Build `snapshot = { providers: providers?.length ?? 0, models: models?.length ?? 0, agents: agentList.length, sessions: sessionList.length }`.
- Build `progress = deriveOnboardingProgress(snapshot)`.
- Add `useOnboardingPreference()`.
- Add `const [wizardOpen, setWizardOpen] = useState(false); const [wizardStep, setWizardStep] = useState<OnboardingStep>("welcome")`.
- `useEffect(() => { if (snapshot.providers === 0 && snapshot.agents === 0 && !dismissed) setWizardOpen(true); }, [snapshot.providers, snapshot.agents, dismissed]);`
- Render `<HomeChecklist progress={progress} onOpenStep={(step) => { setWizardStep(step); setWizardOpen(true); }} />` above the stats.
- Render `<OnboardingWizard opened={wizardOpen} initialStep={wizardStep} onClose={() => { dismiss(); setWizardOpen(false); }} onDone={() => { reset(); setWizardOpen(false); }} />`.

Add `home.module.css` rule:
```css
.setupRow {
  margin-bottom: var(--ab-space-5);
}
```

- [ ] **Step 4: Run tests/build**

Run:
```powershell
cd apps/web
bun run test -- src/pages/HomePage.test.tsx
bun run build
```
Expected: PASS and build clean.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src/pages/HomePage.tsx apps/web/src/pages/home.module.css apps/web/src/pages/HomePage.test.tsx
git commit -m "feat(web): add setup checklist to Home"
```

---

### Task 14: Storybook stories and screenshot pack

**Files:**
- Create: `apps/web/src/help/help.stories.tsx`
- Create: `apps/web/src/pages/providers/providers.stories.tsx`
- Create: `apps/web/src/pages/agents/editors.stories.tsx`
- Create: `apps/web/src/onboarding/onboarding.stories.tsx`
- Create: `apps/web/scripts/screenshots-ux3.mjs`
- Create: `docs/reviews/2026-11-21-ux-3/README.md`
- Modify: `apps/web/.storybook/main.ts`

**Interfaces:**
- Stories for help, provider form, A2A structured/JSON, grouped tools/modes, onboarding steps, and guided empty states.
- Screenshot script saves deterministic captures.

- [ ] **Step 1: Add stories**

Use titles `Help/States`, `Providers/Setup`, `Agents/Editors`, `Onboarding/States`. Each story uses fixed props; wrap components needing queries in `QueryClientProvider` or mock hooks through small demo wrappers.

Required story exports:
- `Help/Overview`
- `Providers/Form`
- `Agents/Tools`
- `Agents/Modes`
- `Agents/A2AStructured`
- `Agents/A2AJson`
- `Onboarding/Checklist`
- `Onboarding/Welcome`

Use this exact structure for the help stories:

```tsx
import type { Meta, StoryObj } from "@storybook/react-vite";
import { HelpProvider } from "../help/HelpProvider";
import { HelpDrawer } from "../help/HelpDrawer";

const meta: Meta = { title: "Help/States" };
export default meta;

export const Overview: StoryObj = {
  render: () => (
    <HelpProvider>
      <HelpDrawer active="provider.kind" onClose={() => {}} />
    </HelpProvider>
  ),
};
```

Create a separate `onboarding.stories.tsx`:

```tsx
import type { Meta, StoryObj } from "@storybook/react-vite";
import { HomeChecklist } from "./HomeChecklist";
import { deriveOnboardingProgress } from "./onboardingProgress";

const meta: Meta = { title: "Onboarding/States" };
export default meta;

export const Checklist: StoryObj = {
  render: () => (
    <HomeChecklist
      progress={deriveOnboardingProgress({
        providers: 1,
        models: 1,
        agents: 0,
        sessions: 0,
      })}
      onOpenStep={() => {}}
    />
  ),
};

export const Welcome: StoryObj = {
  render: () => <div id="onboarding-welcome">Connect your first provider</div>,
};
```

Provider stories wrap `ProviderForm` in `HelpProvider` and `QueryClientProvider`; agent stories wrap tools/modes/A2A components in `HelpProvider`. Use the component names from Tasks 4, 7, 8, and 6.

- [ ] **Step 2: Include story paths**

In `.storybook/main.ts`, add:
```ts
"../src/help/**/*.stories.@(ts|tsx)",
"../src/onboarding/**/*.stories.@(ts|tsx)",
```
Keep existing design-system and chat story globs.

- [ ] **Step 3: Write screenshot script**

Copy the structure of `apps/web/scripts/screenshots-ux2.mjs`, output to `docs/reviews/2026-11-21-ux-3/`, and capture:

```js
const shots = [
  ["help-overview", "help-states--overview", desktop, "dark"],
  ["provider-form", "providers-setup--form", desktop, "dark"],
  ["tools-editor", "agents-editors--tools", desktop, "dark"],
  ["modes-editor", "agents-editors--modes", desktop, "dark"],
  ["a2a-structured", "agents-editors--a2a-structured", desktop, "dark"],
  ["a2a-json", "agents-editors--a2a-json", desktop, "dark"],
  ["onboarding-checklist", "onboarding-states--checklist", desktop, "dark"],
  ["onboarding-welcome", "onboarding-states--welcome", mobile, "dark"],
];
```

Use `theme:dark` and `viewMode=story`.

- [ ] **Step 4: Build Storybook and capture**

Run:
```powershell
cd apps/web
bun run build-storybook
bun run preview-storybook
# second terminal:
bun run scripts/screenshots-ux3.mjs
```
Expected: storybook builds; script saves all eight PNGs.

- [ ] **Step 5: Write README**

Embed each screenshot with a one-line caption grouped by Help / Providers / Agents / Onboarding.

- [ ] **Step 6: Commit**

```powershell
git add apps/web/.storybook apps/web/src/help/help.stories.tsx apps/web/src/pages/providers/providers.stories.tsx apps/web/src/pages/agents/editors.stories.tsx apps/web/src/onboarding/onboarding.stories.tsx apps/web/scripts/screenshots-ux3.mjs docs/reviews/2026-11-21-ux-3
git commit -m "docs(ux): add UX-3 screenshot pack"
```

---

### Task 15: E2E coverage for onboarding, provider test, and editors

**Files:**
- Create: `apps/web/e2e/00-ux3-onboarding.spec.ts`
- Create: `apps/web/e2e/ux3-editors.spec.ts`

**Interfaces:**
- Uses the deterministic `test` provider and existing e2e stub model server.
- Covers first-run wizard, provider test failure/success, A2A structured save, mode duplicate rejection, scope warning.

- [ ] **Step 1: Write onboarding/provider test**

`00-ux3-onboarding.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

test("first-run wizard tests a provider and completes setup", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByRole("textbox", { name: "Password" }).fill("admin");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();

  const wizard = page.getByRole("dialog", { name: "Set up Agentbox" });
  await expect(wizard).toBeVisible();
  await wizard.getByRole("button", { name: "Get started" }).click();

  await wizard.getByLabel("Name").fill("e2e-ux3-provider");
  await wizard.getByLabel("Kind").click();
  await page.getByRole("option", { name: "Generic OpenAI-compatible" }).click();
  await wizard.getByLabel("Models URL").fill("not-a-url");
  await wizard.getByRole("button", { name: "Test connection" }).click();
  await expect(wizard.getByText(/http\/https/i)).toBeVisible();

  await wizard.getByLabel("Models URL").fill("http://localhost:9999/models");
  await wizard.getByRole("button", { name: "Test connection" }).click();
  await expect(wizard.getByText(/Connected/i)).toBeVisible({ timeout: 15000 });
  await wizard.getByRole("button", { name: "Create provider" }).click();

  await wizard.getByLabel("Agent name").fill("e2e-ux3-agent");
  await wizard.getByLabel("Model").click();
  await page.getByRole("option", { name: /e2e-model/ }).click();
  await wizard.getByRole("button", { name: "Create agent" }).click();

  await wizard.getByLabel("Project name").fill("e2e-ux3-project");
  await wizard.getByLabel("Project path").fill(".");
  await wizard.getByRole("button", { name: "Create project and start session" }).click();

  await expect(page.getByText("Provider connected")).toBeVisible();
  await expect(page.getByText("Agent ready")).toBeVisible();
  await expect(page.getByText("First session started")).toBeVisible();
});
```

- [ ] **Step 2: Write editor test**

`ux3-editors.spec.ts`:

```ts
import { expect, type Page, test } from "@playwright/test";

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
  const provider = await request.post("http://localhost:8000/providers", {
    headers,
    data: {
      name: `e2e-ux3-card-provider-${suffix}`,
      kind: "test",
      models_url: "http://localhost:9999/models",
    },
  });
  const providerId = (await provider.json()).id;
  await request.post(
    `http://localhost:8000/providers/${providerId}/models/refresh`,
    { headers },
  );
  const agentName = `e2e-ux3-card-${suffix}`;
  await request.post("http://localhost:8000/agents", {
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
  await page.getByRole("button", { name: `A2A ${agentName}` }).click();
  const card = page.getByRole("dialog", { name: `A2A card: ${agentName}` });
  await card.getByLabel("Agent card name").fill("Reviewer");
  await card.getByRole("button", { name: "Add skill" }).click();
  await card.getByLabel("Skill 1 id").fill("review");
  await card.getByLabel("Skill 1 name").fill("Review");
  await card.getByRole("button", { name: "Save" }).click();
  await page.getByRole("button", { name: `A2A ${agentName}` }).click();
  await expect(card.getByLabel("Agent card name")).toHaveValue("Reviewer");
  await expect(card.getByLabel("Skill 1 name")).toHaveValue("Review");

  await card.getByRole("tab", { name: "JSON" }).click();
  await card.getByLabel("Agent card JSON").fill("{bad");
  await card.getByRole("button", { name: "Save" }).click();
  await expect(card.getByText(/JSON/i)).toBeVisible();
  await expect(card).toBeVisible();
  await card.getByRole("button", { name: "Close" }).click();

  await page.goto("/providers");
  await page.getByRole("button", { name: "New provider" }).click();
  const providerForm = page.getByRole("dialog", { name: "New provider" });
  await providerForm.getByLabel("Kind").click();
  await page.getByRole("option", { name: "DeepSeek" }).click();
  await expect(providerForm.getByLabel("Base URL")).toHaveValue(
    "https://api.deepseek.com/v1",
  );
  await providerForm.getByRole("button", { name: "Help: Provider kind" }).hover();
  await expect(page.getByText(/OpenAI-compatible APIs/i)).toBeVisible();

  await page.goto("/api-keys");
  await page.getByRole("button", { name: "Use recommended" }).click();
  await expect(page.getByText(/selected/i)).toBeVisible();
  await page.getByRole("button", { name: "Clear scopes" }).click();
  await expect(page.getByText(/cannot perform authorized work/i)).toBeVisible();
});
```

The agent row must expose its A2A action as `aria-label={`A2A ${agent.name}`}`; update `AgentList` if the current label is only `A2A`.

- [ ] **Step 3: Run E2E**

Run: `cd apps/web && bun run e2e`
Expected: all existing and new tests pass.

- [ ] **Step 4: Commit**

```powershell
git add apps/web/e2e/00-ux3-onboarding.spec.ts apps/web/e2e/ux3-editors.spec.ts
git commit -m "test(web): cover UX-3 setup and editors"
```

---

### Task 16: Roadmap and final verification

**Files:**
- Modify: `docs/ROADMAP.md`
- Modify: `docs/superpowers/plans/2026-11-21-ux-3-contextual-help-structured-editors.md` (mark status)

**Interfaces:**
- Roadmap marks UX-3 `DONE`, adds history row 32, and leaves UX-4 as next.

- [ ] **Step 1: Update roadmap**

- Set UX-3 status from `PLANNED` to `DONE`.
- Update the paragraph: UX-1, UX-2, UX-3 complete; next cycle UX-4.
- Add history row 32 for UX-3 with the spec and plan paths.

- [ ] **Step 2: Mark plan status**

Add `**Status:** COMPLETE` at the top of this plan.

- [ ] **Step 3: Run all checks**

```powershell
cd apps/web
bun run test
bun run build
bun run build-storybook
bun run e2e
cd ../..
uv run pytest packages/agentbox-api -q
uv run pytest packages/agentbox-harness -q
uv run pytest packages/agentbox-models -q
uv run pytest packages/agentbox-providers -q
uv run ruff check packages
uv run ty check packages
```

Expected: all tests pass, build clean, Storybook clean, E2E passes, ruff/ty clean.

- [ ] **Step 4: Confirm screenshots**

Verify `docs/reviews/2026-11-21-ux-3/README.md` embeds every required screenshot and all PNG files exist.

- [ ] **Step 5: Commit**

```powershell
git add docs/ROADMAP.md docs/superpowers/plans/2026-11-21-ux-3-contextual-help-structured-editors.md
git commit -m "docs: complete UX-3"
```

---

## Self-review

**Spec coverage:** Tasks 1-2 cover the provider test endpoint/client; 3 covers shared help; 4 covers provider presets/form; 5-6 cover A2A; 7-8 cover tools/modes/MCP; 9 covers scopes; 10 covers empty states; 11-13 cover onboarding/Home; 14-16 cover visuals, E2E, roadmap, and verification.

**Placeholder scan:** No TBD/TODO steps; each test and implementation step names concrete files, signatures, and expected outcomes.

**Type consistency:** `ProviderDraft`, `ProviderTestResult`, `HelpId`, `StructuredA2ACard`, `AgentMode`, `OnboardingStep`, and `OnboardingProgress` keep the same names across tasks. `useTestProvider`, `applyProviderPreset`, `mergeStructuredCard`, `deriveOnboardingProgress`, and `HomeChecklist` are defined before later tasks consume them.
