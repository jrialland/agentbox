# Web Scaffold + Design System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scaffold `apps/web` — a Bun + Vite + React + TypeScript SPA with a Bulma-layout/Mantine-widgets design system (RemixIcons, synced light/dark), an OpenAPI-generated typed API client, routing with an app shell, a typed `mitt` message bus, and TanStack Query + Zustand plumbing.

**Architecture:** A standalone frontend app under `apps/web`. `App.tsx` composes providers (Mantine, TanStack Query, Router) and a `ThemeSync` that mirrors Mantine's color scheme onto Bulma's `data-theme`. Placeholder pages render inside a Bulma `AppShell` (navbar + sidebar + outlet). The API client is generated from the backend's OpenAPI schema.

**Tech Stack:** Bun, Vite, React 19, TypeScript, React Router, TanStack Query, Zustand, mitt, Mantine, Bulma, `@remixicon/react`, `openapi-fetch`/`openapi-typescript`, Vitest + Testing Library.

## Global Constraints

- Frontend lives in `apps/web` as a **standalone Bun project** (the Python Uv workspace is untouched).
- **Bulma = layout/typography/spacing; Mantine = complex widgets.** Never both on one element.
- **RemixIcons** via `@remixicon/react` components.
- **OpenAPI-generated** API client (no hand-written request types).
- Async/server state via TanStack Query; client state via Zustand; cross-component messages via the **mitt bus**.
- Tests via **Vitest + Testing Library (jsdom)**; no real backend calls.
- Run `bun run test` and `bun run build` (and the global `uv run ruff`/`ty`/`bandit` are unrelated here — those are Python).

**Reference docs (verify package versions/APIs while implementing):**
- Vite + React: `https://vite.dev/guide/`; Vitest: `https://vitest.dev/`.
- Mantine: `https://mantine.dev/`; Bulma: `https://bulma.io/`.
- openapi-fetch / openapi-typescript: `https://openapi-ts.dev/`.

---

### Task 1: Scaffold + first render test

**Files:**
- Create: `apps/web/package.json`, `apps/web/vite.config.ts`, `apps/web/tsconfig.json`, `apps/web/index.html`
- Create: `apps/web/src/main.tsx`, `apps/web/src/App.tsx`, `apps/web/src/test/setup.ts`
- Test: `apps/web/src/App.test.tsx`

**Interfaces:**
- Produces: a runnable Vite app; `App` renders; Vitest harness with Mantine polyfills.

- [ ] **Step 1: Create config files**

```jsonc
// apps/web/package.json
{
  "name": "agentbox-web",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "codegen": "openapi-typescript openapi.json -o src/api/schema.d.ts"
  }
}
```

```ts
// apps/web/vite.config.ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
  },
});
```

```jsonc
// apps/web/tsconfig.json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noEmit": true,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "resolveJsonModule": true,
    "types": ["vite/client", "vitest/globals"]
  },
  "include": ["src"]
}
```

```html
<!-- apps/web/index.html -->
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Agentbox</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 2: Install dependencies (bun resolves versions)**

`package.json` (created in Step 1) already exists with the scripts above; `bun add` will populate its dependency fields. Run (from `apps/web`):
```bash
bun add react react-dom react-router-dom @tanstack/react-query zustand mitt @mantine/core @mantine/hooks @mantine/notifications @mantine/modals bulma @remixicon/react openapi-fetch
bun add -d vite @vitejs/plugin-react typescript vitest @testing-library/react @testing-library/jest-dom jsdom openapi-typescript @types/react @types/react-dom
```

- [ ] **Step 3: Write minimal app + test harness**

```tsx
// apps/web/src/main.tsx
import React from "react";
import ReactDOM from "react-dom/client";

import { App } from "./App";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

```tsx
// apps/web/src/App.tsx
export function App() {
  return <div>Agentbox</div>;
}
```

```ts
// apps/web/src/test/setup.ts
import "@testing-library/jest-dom/vitest";

if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

if (!("ResizeObserver" in window)) {
  class RO {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  (window as unknown as { ResizeObserver: typeof RO }).ResizeObserver = RO;
}
```

```tsx
// apps/web/src/App.test.tsx
import { render, screen } from "@testing-library/react";

import { App } from "./App";

test("renders the app", () => {
  render(<App />);
  expect(screen.getByText("Agentbox")).toBeInTheDocument();
});
```

- [ ] **Step 4: Run test + build**

Run (from `apps/web`): `bun run test` → 1 passed. `bun run build` → succeeds.

- [ ] **Step 5: Commit**

```bash
git add apps/web
git commit -m "feat(web): scaffold Vite + React + TS app with Vitest"
```

---

### Task 2: Design system (Mantine + Bulma + RemixIcons + ThemeSync)

**Files:**
- Create: `apps/web/src/theme/ThemeSync.tsx`
- Modify: `apps/web/src/main.tsx` (CSS imports), `apps/web/src/App.tsx` (providers)
- Test: `apps/web/src/theme/ThemeSync.test.tsx`

**Interfaces:**
- Produces: `ThemeSync` mirrors Mantine's computed scheme onto `<html data-theme>`.

- [ ] **Step 1: Write the failing test**

```tsx
// apps/web/src/theme/ThemeSync.test.tsx
import { MantineProvider } from "@mantine/core";
import { render } from "@testing-library/react";

import { ThemeSync } from "./ThemeSync";

test("sets data-theme on documentElement", () => {
  render(
    <MantineProvider defaultColorScheme="light">
      <ThemeSync />
    </MantineProvider>,
  );
  expect(document.documentElement.dataset.theme).toBe("light");
});
```

- [ ] **Step 2: Run to fail** → `bun run test` fails (module missing).

- [ ] **Step 3: Implement**

```tsx
// apps/web/src/theme/ThemeSync.tsx
import { useComputedColorScheme } from "@mantine/core";
import { useEffect } from "react";

export function ThemeSync() {
  const scheme = useComputedColorScheme("light");
  useEffect(() => {
    document.documentElement.dataset.theme = scheme;
  }, [scheme]);
  return null;
}
```

- [ ] **Step 4: Wire CSS + providers**

```tsx
// apps/web/src/main.tsx (add at top, before other imports)
import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";
import "bulma/css/bulma.css";
```

```tsx
// apps/web/src/App.tsx
import { MantineProvider } from "@mantine/core";
import { ModalsProvider } from "@mantine/modals";
import { Notifications } from "@mantine/notifications";

import { ThemeSync } from "./theme/ThemeSync";

export function App() {
  return (
    <MantineProvider defaultColorScheme="auto">
      <ThemeSync />
      <Notifications />
      <ModalsProvider>
        <div>Agentbox</div>
      </ModalsProvider>
    </MantineProvider>
  );
}
```

- [ ] **Step 5: Run to pass + commit**

Run: `bun run test` (2 passed). `bun run build` succeeds.

```bash
git add apps/web
git commit -m "feat(web): add design system providers + ThemeSync (Bulma/Mantine)"
```

---

### Task 3: OpenAPI-generated API client

**Files:**
- Create: `apps/web/scripts/gen-openapi.py`
- Create (generated): `apps/web/openapi.json`, `apps/web/src/api/schema.d.ts`
- Create: `apps/web/src/api/client.ts`
- Test: `apps/web/src/api/client.test.ts`

**Interfaces:**
- Produces: `authMiddleware(token)` (adds `Authorization: Bearer`) and `api` (an `openapi-fetch` client bound to `VITE_API_URL`).

- [ ] **Step 1: Write the schema dump script**

```python
# apps/web/scripts/gen-openapi.py
import json
from pathlib import Path

from agentbox_api.app import create_app
from agentbox_api.config import Settings

app = create_app(Settings(jwt_secret="x" * 32))
out = Path(__file__).resolve().parent.parent / "openapi.json"
out.write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
print(f"Wrote {out}")
```

- [ ] **Step 2: Generate schema + typed client**

Run (from repo root): `uv run python apps/web/scripts/gen-openapi.py`
Then (from `apps/web`): `bun run codegen`
Expected: `apps/web/openapi.json` and `apps/web/src/api/schema.d.ts` exist.

- [ ] **Step 3: Write the failing test**

```ts
// apps/web/src/api/client.test.ts
import { authMiddleware } from "./client";

test("authMiddleware adds bearer header", async () => {
  const mw = authMiddleware("tok123");
  const request = new Request("http://x/");
  await mw.onRequest({ request });
  expect(request.headers.get("Authorization")).toBe("Bearer tok123");
});

test("authMiddleware leaves header off without token", async () => {
  const mw = authMiddleware(null);
  const request = new Request("http://x/");
  await mw.onRequest({ request });
  expect(request.headers.get("Authorization")).toBeNull();
});
```

- [ ] **Step 4: Run to fail** → `bun run test` fails (module missing).

- [ ] **Step 5: Implement**

```ts
// apps/web/src/api/client.ts
import createClient from "openapi-fetch";

import type { paths } from "./schema";

export function authMiddleware(token: string | null) {
  return {
    onRequest({ request }: { request: Request }) {
      if (token) request.headers.set("Authorization", `Bearer ${token}`);
      return request;
    },
  };
}

export const api = createClient<paths>({
  baseUrl: import.meta.env.VITE_API_URL ?? "http://localhost:8000",
});

api.use(authMiddleware(null));
```

- [ ] **Step 6: Run to pass + commit**

Run: `bun run test` (4 passed). `bun run build` succeeds (requires `schema.d.ts` present).

```bash
git add apps/web
git commit -m "feat(web): add OpenAPI-generated client + JWT middleware"
```

---

### Task 4: Message bus + client state (Zustand)

**Files:**
- Create: `apps/web/src/lib/bus.ts`
- Create: `apps/web/src/store/auth.ts`
- Test: `apps/web/src/lib/bus.test.ts`, `apps/web/src/store/auth.test.ts`

**Interfaces:**
- Produces: `bus` (typed `mitt` emitter over `AppEvents`); `useAuthStore` (`token`, `setToken`, `clear`).

- [ ] **Step 1: Write the failing tests**

```ts
// apps/web/src/lib/bus.test.ts
import { vi } from "vitest";

import { bus } from "./bus";

test("bus delivers typed events", () => {
  const handler = vi.fn();
  bus.on("theme:changed", handler);
  bus.emit("theme:changed", { scheme: "dark" });
  expect(handler).toHaveBeenCalledWith({ scheme: "dark" });
});
```

```ts
// apps/web/src/store/auth.test.ts
import { useAuthStore } from "./auth";

test("auth store sets and clears token", () => {
  useAuthStore.getState().setToken("abc");
  expect(useAuthStore.getState().token).toBe("abc");
  useAuthStore.getState().clear();
  expect(useAuthStore.getState().token).toBeNull();
});
```

- [ ] **Step 2: Run to fail** → modules missing.

- [ ] **Step 3: Implement**

```ts
// apps/web/src/lib/bus.ts
import mitt, { type Emitter } from "mitt";

export type AppEvents = {
  "theme:changed": { scheme: "light" | "dark" };
};

export const bus: Emitter<AppEvents> = mitt<AppEvents>();
```

```ts
// apps/web/src/store/auth.ts
import { create } from "zustand";

type AuthState = {
  token: string | null;
  setToken: (token: string) => void;
  clear: () => void;
};

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  setToken: (token) => set({ token }),
  clear: () => set({ token: null }),
}));
```

- [ ] **Step 4: Run to pass + commit**

Run: `bun run test` (6 passed).

```bash
git add apps/web
git commit -m "feat(web): add typed mitt bus and Zustand auth store"
```

---

### Task 5: App shell, routing, and placeholder pages

**Files:**
- Create: `apps/web/src/components/layout/AppShell.tsx`
- Create: `apps/web/src/pages/HomePage.tsx`, `LoginPage.tsx`, `AgentsPage.tsx`, `ProvidersPage.tsx`, `ProjectsPage.tsx`
- Modify: `apps/web/src/App.tsx` (router + QueryClient + shell)
- Test: `apps/web/src/App.test.tsx` (extend)

**Interfaces:**
- Produces: routed `AppShell` with nav links and page placeholders.

- [ ] **Step 1: Write the failing test**

```tsx
// apps/web/src/App.test.tsx
import { render, screen } from "@testing-library/react";

import { App } from "./App";

test("renders the shell navigation", () => {
  render(<App />);
  expect(screen.getByText("Agents")).toBeInTheDocument();
  expect(screen.getByText("Projects")).toBeInTheDocument();
});

test("renders the home page", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: "Home" })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to fail** → assertion fails (no shell).

- [ ] **Step 3: Implement pages**

```tsx
// apps/web/src/pages/HomePage.tsx
export function HomePage() {
  return <h1 className="title">Home</h1>;
}
```

```tsx
// apps/web/src/pages/LoginPage.tsx
export function LoginPage() {
  return <h1 className="title">Login</h1>;
}
```

```tsx
// apps/web/src/pages/AgentsPage.tsx
export function AgentsPage() {
  return <h1 className="title">Agents</h1>;
}
```

```tsx
// apps/web/src/pages/ProvidersPage.tsx
export function ProvidersPage() {
  return <h1 className="title">Providers</h1>;
}
```

```tsx
// apps/web/src/pages/ProjectsPage.tsx
export function ProjectsPage() {
  return <h1 className="title">Projects</h1>;
}
```

- [ ] **Step 4: Implement the shell**

```tsx
// apps/web/src/components/layout/AppShell.tsx
import { Link, Outlet } from "react-router-dom";

export function AppShell() {
  return (
    <div>
      <nav className="navbar" role="navigation" aria-label="main navigation">
        <div className="navbar-brand">
          <Link className="navbar-item" to="/">
            Agentbox
          </Link>
        </div>
      </nav>
      <div className="columns">
        <aside className="column is-2">
          <aside className="menu">
            <p className="menu-label">Navigation</p>
            <ul className="menu-list">
              <li>
                <Link to="/agents">Agents</Link>
              </li>
              <li>
                <Link to="/providers">Providers</Link>
              </li>
              <li>
                <Link to="/projects">Projects</Link>
              </li>
            </ul>
          </aside>
        </aside>
        <main className="column">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Wire the router in App**

```tsx
// apps/web/src/App.tsx
import { MantineProvider } from "@mantine/core";
import { ModalsProvider } from "@mantine/modals";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AppShell } from "./components/layout/AppShell";
import { AgentsPage } from "./pages/AgentsPage";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { ProvidersPage } from "./pages/ProvidersPage";
import { ThemeSync } from "./theme/ThemeSync";

const queryClient = new QueryClient();

export function App() {
  return (
    <MantineProvider defaultColorScheme="auto">
      <ThemeSync />
      <Notifications />
      <ModalsProvider>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <Routes>
              <Route element={<AppShell />}>
                <Route index element={<HomePage />} />
                <Route path="login" element={<LoginPage />} />
                <Route path="agents" element={<AgentsPage />} />
                <Route path="providers" element={<ProvidersPage />} />
                <Route path="projects" element={<ProjectsPage />} />
              </Route>
            </Routes>
          </BrowserRouter>
        </QueryClientProvider>
      </ModalsProvider>
    </MantineProvider>
  );
}
```

- [ ] **Step 6: Run to pass + build + commit**

Run: `bun run test` (all pass). `bun run build` succeeds.

```bash
git add apps/web
git commit -m "feat(web): add app shell, routing, and placeholder pages"
```

---

## Self-Review Notes

- **Spec coverage:** scaffold/tooling (1), design system + ThemeSync (2), OpenAPI client + JWT middleware (3), bus + state (4), shell + routing + pages (5). All §1.1 items covered.
- **Extension points used:** Vite/Vitest, Mantine provider, Bulma, `@remixicon/react`, `openapi-fetch`/`openapi-typescript`, TanStack Query, Zustand, mitt.
- **Verification note:** exact dep versions resolved by `bun add`; verify Mantine/`openapi-fetch` APIs against installed versions during implementation (as done for Python deps).
- **RemixIcons usage:** the scaffold doesn't yet render icons; add them when building actual nav/pages in later sub-projects (the dependency is installed now).
