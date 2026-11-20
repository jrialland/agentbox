# UX-1 Design System, Command Shell, and Product Character — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the default-library frontend with an Agentbox-specific hacker/command-center design system, 3-pane shell, RemixIcon iconography, and restyled non-chat pages.

**Architecture:** Build a self-contained design system under `apps/web/src/design-system/` (CSS-variable tokens + Mantine theme + Storybook-documented primitives). Then replace `AppShell` with a 3-pane `CommandShell`, refactor the project tree into a `ProjectPanel`, and migrate Login, Home, Agents, Providers/Models, Admin, API keys, and Skills. Chat keeps a scoped Bulma compatibility layer until UX-2.

**Tech Stack:** React 19, Vite 8, Mantine 9, RemixIcon, Storybook 10.6.8, Silkscreen / Inter / JetBrains Mono (Fontsource), Vitest, Playwright.

## Global Constraints

- Work from `apps/web` for all frontend commands; use `bun`, never npm/pnpm.
- Mantine-first: no new Bulma usage outside the chat compatibility layer.
- RemixIcons only for icons; icon-only controls require `aria-label` + tooltip.
- Fonts: Silkscreen for display/nav, Inter for body/UI, JetBrains Mono for code/metadata.
- Colors: CSS tokens from the spec; dark and light must both meet WCAG AA for body text.
- Dark-first, system-aware, visible toggle; persist preference in localStorage.
- No page-level horizontal overflow at 390px.
- Every component gets Storybook stories and light/dark rendering.
- Keep existing backend behavior, API calls, and permissions unchanged.
- Run focused tests while iterating; run `bun run test`, `bun run build`, `bun run build-storybook`, and `bun run e2e` before declaring UX-1 complete.

---

### Task 1: Design tokens, fonts, theme provider, and CSS layers

**Files:**
- Modify: `apps/web/package.json`
- Modify: `apps/web/src/main.tsx`
- Modify: `apps/web/src/App.tsx`
- Create: `apps/web/src/design-system/styles/layers.css`
- Create: `apps/web/src/design-system/styles/legacy.css`
- Create: `apps/web/src/design-system/styles/global.css`
- Create: `apps/web/src/design-system/tokens/tokens.css`
- Create: `apps/web/src/design-system/theme/theme.ts`
- Create: `apps/web/src/design-system/theme/ThemeProvider.tsx`
- Create: `apps/web/src/design-system/theme/ThemeToggle.tsx`
- Test: `apps/web/src/design-system/theme/ThemeProvider.test.tsx`
- Test: `apps/web/src/design-system/theme/ThemeToggle.test.tsx`

**Interfaces:**
- Produces: `ThemeProvider({ children, forceScheme? })`, `ThemeToggle({ className? })`, `theme` (Mantine theme).
- Produces CSS variables `--ab-*` and `data-theme="dark|light"` on `<html>`.

- [ ] **Step 1: Add font dependencies**

Run from `apps/web`:

```powershell
bun add @fontsource/silkscreen@5.3.0 @fontsource/inter@5.3.0 @fontsource/jetbrains-mono@5.3.0
```

- [ ] **Step 2: Write the failing theme tests**

Create `apps/web/src/design-system/theme/ThemeProvider.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ThemeProvider } from "./ThemeProvider";

describe("ThemeProvider", () => {
  it("renders children and sets a data-theme attribute", () => {
    render(
      <ThemeProvider forceScheme="dark">
        <span>hello</span>
      </ThemeProvider>,
    );
    expect(screen.getByText("hello")).toBeInTheDocument();
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
});
```

Create `apps/web/src/design-system/theme/ThemeToggle.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { ThemeProvider } from "./ThemeProvider";
import { ThemeToggle } from "./ThemeToggle";

describe("ThemeToggle", () => {
  beforeEach(() => {
    localStorage.setItem("agentbox-color-scheme", "dark");
  });

  it("switches from dark to light", async () => {
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>,
    );
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("dark"));
    fireEvent.click(screen.getByRole("button", { name: /switch to light theme/i }));
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("light"));
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

Run:

```powershell
bun run test -- src/design-system/theme
```

Expected: FAIL because `ThemeProvider.tsx` and `ThemeToggle.tsx` do not exist.

- [ ] **Step 4: Create CSS layers and legacy Bulma import**

Create `apps/web/src/design-system/styles/layers.css`:

```css
@layer reset, legacy, ds, utilities;
```

Create `apps/web/src/design-system/styles/legacy.css`:

```css
@import "bulma/css/bulma.css" layer(legacy);
```

Create `apps/web/src/design-system/styles/global.css`:

```css
@layer ds {
  *,
  *::before,
  *::after {
    box-sizing: border-box;
  }

  html,
  body,
  #root {
    min-height: 100%;
  }

  body {
    margin: 0;
    background: var(--ab-canvas);
    color: var(--ab-text);
    font-family: var(--ab-font-body);
    font-size: var(--ab-text-md);
    line-height: 1.55;
    -webkit-font-smoothing: antialiased;
  }

  ::selection {
    background: var(--ab-phosphor);
    color: var(--ab-canvas);
  }

  :focus-visible {
    outline: var(--ab-focus-width) solid var(--ab-phosphor);
    outline-offset: 2px;
  }

  .ab-grid-surface {
    background-image:
      linear-gradient(to right, var(--ab-grid) 1px, transparent 1px),
      linear-gradient(to bottom, var(--ab-grid) 1px, transparent 1px);
    background-size: 24px 24px;
  }

  .ab-scanlines {
    position: relative;
  }

  .ab-scanlines::after {
    content: "";
    position: absolute;
    inset: 0;
    pointer-events: none;
    background: repeating-linear-gradient(
      to bottom,
      transparent 0,
      transparent 2px,
      var(--ab-scanline) 3px
    );
    opacity: 0.35;
  }
}
```

- [ ] **Step 5: Create token variables**

Create `apps/web/src/design-system/tokens/tokens.css`:

```css
:root {
  --ab-font-display: "Silkscreen", monospace;
  --ab-font-body: "Inter", system-ui, sans-serif;
  --ab-font-mono: "JetBrains Mono", ui-monospace, monospace;

  --ab-text-xs: 12px;
  --ab-text-sm: 13px;
  --ab-text-md: 14px;
  --ab-text-lg: 16px;
  --ab-text-xl: 18px;
  --ab-text-2xl: 20px;
  --ab-text-3xl: 24px;
  --ab-text-4xl: 32px;
  --ab-text-5xl: 40px;

  --ab-space-1: 4px;
  --ab-space-2: 8px;
  --ab-space-3: 12px;
  --ab-space-4: 16px;
  --ab-space-5: 24px;
  --ab-space-6: 32px;
  --ab-space-7: 48px;
  --ab-space-8: 64px;

  --ab-radius-none: 0;
  --ab-radius-sm: 2px;
  --ab-radius-md: 4px;
  --ab-radius-lg: 8px;

  --ab-border-width: 1px;
  --ab-focus-width: 2px;

  --ab-motion-fast: 120ms;
  --ab-motion-base: 180ms;
  --ab-motion-slow: 280ms;
  --ab-ease-standard: cubic-bezier(0.2, 0, 0, 1);

  --ab-rail-width: 56px;
  --ab-panel-width: 280px;
  --ab-content-max: 1200px;

  --ab-z-rail: 20;
  --ab-z-panel: 30;
  --ab-z-overlay: 100;
  --ab-z-toast: 200;
}

[data-theme="dark"] {
  color-scheme: dark;
  --ab-canvas: #0a0d0a;
  --ab-surface: #111611;
  --ab-surface-raised: #182018;
  --ab-border: #2a352a;
  --ab-text: #dce7dc;
  --ab-text-muted: #8e9c8e;
  --ab-phosphor: #5cff9d;
  --ab-amber: #ffb000;
  --ab-cyan: #39d7ff;
  --ab-magenta: #ff4fd8;
  --ab-danger: #ff5c5c;
  --ab-grid: rgba(92, 255, 157, 0.08);
  --ab-scanline: rgba(0, 0, 0, 0.22);
}

[data-theme="light"] {
  color-scheme: light;
  --ab-canvas: #f3f6f0;
  --ab-surface: #ffffff;
  --ab-surface-raised: #e9eee5;
  --ab-border: #c8d2c4;
  --ab-text: #121812;
  --ab-text-muted: #5a6658;
  --ab-phosphor: #087a43;
  --ab-amber: #9a5a00;
  --ab-cyan: #007a99;
  --ab-magenta: #a31c8c;
  --ab-danger: #b42318;
  --ab-grid: rgba(8, 122, 67, 0.07);
  --ab-scanline: rgba(0, 0, 0, 0.06);
}
```

- [ ] **Step 6: Create the Mantine theme mapping**

Create `apps/web/src/design-system/theme/theme.ts`:

```ts
import { createTheme } from "@mantine/core";

export const theme = createTheme({
  primaryColor: "phosphor",
  defaultRadius: "sm",
  fontFamily: "var(--ab-font-body)",
  fontFamilyMonospace: "var(--ab-font-mono)",
  headings: {
    fontFamily: "var(--ab-font-display)",
    fontWeight: "400",
  },
  colors: {
    phosphor: [
      "#eafff2",
      "#c9ffdf",
      "#a3ffc9",
      "#7cffb3",
      "#5cff9d",
      "#3dec82",
      "#28c96a",
      "#16a653",
      "#08803e",
      "#00602c",
    ],
    amber: [
      "#fff8e1",
      "#ffefb8",
      "#ffe28a",
      "#ffd45c",
      "#ffc62e",
      "#ffb000",
      "#e09800",
      "#c07f00",
      "#9a5a00",
      "#7a4700",
    ],
    cyan: [
      "#e8fbff",
      "#c7f5ff",
      "#a0eeff",
      "#78e7ff",
      "#39d7ff",
      "#1cc2ec",
      "#0aa5cc",
      "#007a99",
      "#00647d",
      "#004e61",
    ],
    magenta: [
      "#fff0fb",
      "#ffd9f4",
      "#ffb8ec",
      "#ff90e2",
      "#ff4fd8",
      "#ef2fc4",
      "#d11aa8",
      "#a31c8c",
      "#861574",
      "#6b0f5d",
    ],
    danger: [
      "#fff0f0",
      "#ffd9d9",
      "#ffb8b8",
      "#ff9292",
      "#ff5c5c",
      "#ef3b3b",
      "#d12a2a",
      "#b42318",
      "#981a12",
      "#7a120c",
    ],
  },
  components: {
    Button: { defaultProps: { radius: "sm" } },
    ActionIcon: { defaultProps: { radius: "sm" } },
    TextInput: { defaultProps: { radius: "sm" } },
    Textarea: { defaultProps: { radius: "sm" } },
    Select: { defaultProps: { radius: "sm" } },
    MultiSelect: { defaultProps: { radius: "sm" } },
    NumberInput: { defaultProps: { radius: "sm" } },
    Modal: { defaultProps: { radius: "md" } },
    Drawer: { defaultProps: { radius: "md" } },
  },
});
```

- [ ] **Step 7: Create ThemeProvider and ThemeToggle**

Create `apps/web/src/design-system/theme/ThemeProvider.tsx`:

```tsx
import {
  localStorageColorSchemeManager,
  MantineProvider,
  useComputedColorScheme,
} from "@mantine/core";
import { useEffect, type ReactNode } from "react";

import { theme } from "./theme";

const colorSchemeManager = localStorageColorSchemeManager({
  key: "agentbox-color-scheme",
});

function ThemeDomSync() {
  const scheme = useComputedColorScheme("dark");
  useEffect(() => {
    document.documentElement.dataset.theme = scheme;
  }, [scheme]);
  return null;
}

export function ThemeProvider({
  children,
  forceScheme,
}: {
  children: ReactNode;
  forceScheme?: "light" | "dark";
}) {
  return (
    <MantineProvider
      theme={theme}
      defaultColorScheme="auto"
      colorSchemeManager={colorSchemeManager}
      forceColorScheme={forceScheme}
    >
      <ThemeDomSync />
      {children}
    </MantineProvider>
  );
}
```

Create `apps/web/src/design-system/theme/ThemeToggle.tsx`:

```tsx
import { ActionIcon, Tooltip, useComputedColorScheme, useMantineColorScheme } from "@mantine/core";
import { RiMoonLine, RiSunLine } from "@remixicon/react";

export function ThemeToggle({ className }: { className?: string }) {
  const { setColorScheme } = useMantineColorScheme();
  const scheme = useComputedColorScheme("dark");
  const next = scheme === "dark" ? "light" : "dark";
  const label = `Switch to ${next} theme`;

  return (
    <Tooltip label={label} withArrow>
      <ActionIcon
        className={className}
        variant="subtle"
        color="phosphor"
        aria-label={label}
        onClick={() => setColorScheme(next)}
      >
        {scheme === "dark" ? <RiSunLine size={18} /> : <RiMoonLine size={18} />}
      </ActionIcon>
    </Tooltip>
  );
}
```

- [ ] **Step 8: Wire fonts, CSS layers, and ThemeProvider**

Modify `apps/web/src/main.tsx`:

```tsx
import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";
import "@fontsource/silkscreen/400.css";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "./design-system/styles/layers.css";
import "./design-system/tokens/tokens.css";
import "./design-system/styles/legacy.css";
import "./design-system/styles/global.css";

import React from "react";
import ReactDOM from "react-dom/client";

import { App } from "./App";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

Modify `apps/web/src/App.tsx`: replace the `MantineProvider` import and wrapper with `ThemeProvider`, and delete the `ThemeSync` import/usage:

```tsx
import { ModalsProvider } from "@mantine/modals";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { RequireAuth } from "./components/auth/RequireAuth";
import { AppShell } from "./components/layout/AppShell";
import { AdminPage } from "./pages/AdminPage";
import { AgentsPage } from "./pages/AgentsPage";
import { ApiKeysPage } from "./pages/ApiKeysPage";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { ProvidersPage } from "./pages/ProvidersPage";
import { SessionPage } from "./pages/SessionPage";
import { SkillsPage } from "./pages/SkillsPage";
import { ThemeProvider } from "./design-system/theme/ThemeProvider";

const queryClient = new QueryClient();

export function App() {
  return (
    <ThemeProvider>
      <Notifications />
      <ModalsProvider>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route element={<RequireAuth />}>
                <Route element={<AppShell />}>
                  <Route index element={<HomePage />} />
                  <Route path="admin" element={<AdminPage />} />
                  <Route path="agents" element={<AgentsPage />} />
                  <Route path="api-keys" element={<ApiKeysPage />} />
                  <Route path="providers" element={<ProvidersPage />} />
                  <Route path="skills" element={<SkillsPage />} />
                  <Route path="sessions/:id" element={<SessionPage />} />
                </Route>
              </Route>
            </Routes>
          </BrowserRouter>
        </QueryClientProvider>
      </ModalsProvider>
    </ThemeProvider>
  );
}
```

- [ ] **Step 9: Run the focused tests**

Run:

```powershell
bun run test -- src/design-system/theme
```

Expected: PASS.

- [ ] **Step 10: Commit**

```powershell
git add apps/web/package.json apps/web/bun.lock apps/web/src/main.tsx apps/web/src/App.tsx apps/web/src/design-system
git commit -m "feat(web): add design tokens and theme provider"
```

---

### Task 2: Storybook configuration and token reference

**Files:**
- Modify: `apps/web/package.json`
- Create: `apps/web/.storybook/main.ts`
- Create: `apps/web/.storybook/preview.tsx`
- Create: `apps/web/src/design-system/stories/tokens.stories.tsx`

**Interfaces:**
- Produces Storybook scripts `storybook` and `build-storybook`.
- Storybook toolbar globals: `theme` (`dark`/`light`) and `viewport` (`mobile`/`tablet`/`desktop`).

- [ ] **Step 1: Add Storybook dependencies and scripts**

Run from `apps/web`:

```powershell
bun add -d storybook@10.6.8 @storybook/react-vite@10.6.8 @storybook/addon-docs@10.6.8 @storybook/addon-a11y@10.6.8
```

Add to `apps/web/package.json` scripts:

```json
"storybook": "storybook dev -p 6006",
"build-storybook": "storybook build"
```

- [ ] **Step 2: Create Storybook config**

Create `apps/web/.storybook/main.ts`:

```ts
import type { StorybookConfig } from "@storybook/react-vite";

const config: StorybookConfig = {
  stories: ["../src/design-system/**/*.stories.@(ts|tsx)"],
  addons: ["@storybook/addon-docs", "@storybook/addon-a11y"],
  framework: {
    name: "@storybook/react-vite",
    options: {},
  },
};

export default config;
```

Create `apps/web/.storybook/preview.tsx`:

```tsx
import "@mantine/core/styles.css";
import "@fontsource/silkscreen/400.css";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "../src/design-system/styles/layers.css";
import "../src/design-system/tokens/tokens.css";
import "../src/design-system/styles/global.css";

import type { Preview } from "@storybook/react-vite";

import { ThemeProvider } from "../src/design-system/theme/ThemeProvider";

const widths = {
  mobile: 390,
  tablet: 834,
  desktop: 1280,
} as const;

const preview: Preview = {
  parameters: {
    options: { storySort: { order: ["Foundations", "Icons", "Primitives", "Forms", "Data", "Overlays", "Navigation", "Patterns", "Shell"] } },
    a11y: { test: "error" },
  },
  globalTypes: {
    theme: {
      name: "Theme",
      defaultValue: "dark",
      toolbar: {
        icon: "mirror",
        items: [
          { value: "dark", title: "Dark" },
          { value: "light", title: "Light" },
        ],
      },
    },
    viewport: {
      name: "Viewport",
      defaultValue: "desktop",
      toolbar: {
        icon: "mobile",
        items: [
          { value: "mobile", title: "Mobile 390" },
          { value: "tablet", title: "Tablet 834" },
          { value: "desktop", title: "Desktop 1280" },
        ],
      },
    },
  },
  decorators: [
    (Story, context) => {
      const theme = (context.globals.theme as "dark" | "light") ?? "dark";
      const viewport = (context.globals.viewport as keyof typeof widths) ?? "desktop";
      return (
        <ThemeProvider forceScheme={theme}>
          <div
            style={{
              width: widths[viewport],
              maxWidth: "100%",
              margin: "0 auto",
              padding: 24,
              background: "var(--ab-canvas)",
              color: "var(--ab-text)",
              minHeight: 240,
            }}
          >
            <Story />
          </div>
        </ThemeProvider>
      );
    },
  ],
};

export default preview;
```

- [ ] **Step 3: Add a token reference story**

Create `apps/web/src/design-system/stories/tokens.stories.tsx`:

```tsx
import type { Meta, StoryObj } from "@storybook/react-vite";

const colors = [
  "canvas",
  "surface",
  "surface-raised",
  "border",
  "text",
  "text-muted",
  "phosphor",
  "amber",
  "cyan",
  "magenta",
  "danger",
] as const;

function TokenReference() {
  return (
    <div style={{ display: "grid", gap: 32 }}>
      <section>
        <h1 style={{ fontFamily: "var(--ab-font-display)", fontSize: 24 }}>[AGENTBOX]▮</h1>
        <p style={{ fontFamily: "var(--ab-font-body)" }}>
          Inter body text. The quick brown fox jumps over the lazy agent.
        </p>
        <p style={{ fontFamily: "var(--ab-font-mono)" }}>session_cffa8f32 · 12:04:11 · 1.2k tokens</p>
      </section>
      <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 12 }}>
        {colors.map((name) => (
          <div key={name} style={{ border: "1px solid var(--ab-border)", padding: 12 }}>
            <div style={{ height: 48, background: `var(--ab-${name})`, border: "1px solid var(--ab-border)" }} />
            <strong style={{ fontFamily: "var(--ab-font-mono)", fontSize: 12 }}>{name}</strong>
            <div style={{ fontFamily: "var(--ab-font-mono)", fontSize: 11, color: "var(--ab-text-muted)" }}>
              var(--ab-{name})
            </div>
          </div>
        ))}
      </section>
    </div>
  );
}

const meta: Meta<typeof TokenReference> = {
  title: "Foundations/Tokens",
  component: TokenReference,
};

export default meta;
type Story = StoryObj<typeof TokenReference>;
export const Default: Story = {};
```

- [ ] **Step 4: Build Storybook**

Run:

```powershell
bun run build-storybook
```

Expected: PASS, static Storybook generated in `storybook-static/`.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/package.json apps/web/bun.lock apps/web/.storybook apps/web/src/design-system/stories
git commit -m "docs(web): add Storybook and token reference"
```

---

### Task 3: Icon and IconButton primitives

**Files:**
- Create: `apps/web/src/design-system/icons/Icon.tsx`
- Create: `apps/web/src/design-system/icons/IconButton.tsx`
- Create: `apps/web/src/design-system/icons/icons.stories.tsx`
- Test: `apps/web/src/design-system/icons/Icon.test.tsx`
- Test: `apps/web/src/design-system/icons/IconButton.test.tsx`

**Interfaces:**
- Produces: `Icon({ as, size?, label? })`, `IconButton({ label, icon, onClick, ... })`.
- Later tasks import icons directly from `@remixicon/react` and render through `Icon`.

- [ ] **Step 1: Write failing icon tests**

Create `apps/web/src/design-system/icons/Icon.test.tsx`:

```tsx
import { render } from "@testing-library/react";
import { RiHome5Line } from "@remixicon/react";
import { describe, expect, it } from "vitest";

import { Icon } from "./Icon";

describe("Icon", () => {
  it("renders an svg and is decorative by default", () => {
    const { container } = render(<Icon as={RiHome5Line} />);
    const svg = container.querySelector("svg");
    expect(svg).toBeTruthy();
    expect(svg?.getAttribute("aria-hidden")).toBe("true");
  });

  it("becomes labelled when a label is provided", () => {
    const { getByRole } = render(<Icon as={RiHome5Line} label="Home" />);
    expect(getByRole("img", { name: "Home" })).toBeInTheDocument();
  });
});
```

Create `apps/web/src/design-system/icons/IconButton.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { RiAddLine } from "@remixicon/react";
import { describe, expect, it, vi } from "vitest";

import { IconButton } from "./IconButton";

describe("IconButton", () => {
  it("exposes an accessible label and fires onClick", () => {
    const onClick = vi.fn();
    render(<IconButton label="New session" icon={RiAddLine} onClick={onClick} />);
    fireEvent.click(screen.getByRole("button", { name: "New session" }));
    expect(onClick).toHaveBeenCalledOnce();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
bun run test -- src/design-system/icons
```

Expected: FAIL because the components do not exist.

- [ ] **Step 3: Implement Icon and IconButton**

Create `apps/web/src/design-system/icons/Icon.tsx`:

```tsx
import type { RemixiconComponentType } from "@remixicon/react";

export function Icon({
  as: Component,
  size = 18,
  label,
  className,
}: {
  as: RemixiconComponentType;
  size?: 16 | 18 | 20 | 24;
  label?: string;
  className?: string;
}) {
  return (
    <Component
      className={className}
      size={size}
      aria-hidden={label ? undefined : "true"}
      role={label ? "img" : undefined}
      aria-label={label}
    />
  );
}
```

Create `apps/web/src/design-system/icons/IconButton.tsx`:

```tsx
import { ActionIcon, Tooltip, type ActionIconProps } from "@mantine/core";
import type { RemixiconComponentType } from "@remixicon/react";

import { Icon } from "./Icon";

export function IconButton({
  label,
  icon,
  size = 18,
  tooltip = true,
  ...props
}: Omit<ActionIconProps, "aria-label"> & {
  label: string;
  icon: RemixiconComponentType;
  size?: 16 | 18 | 20 | 24;
  tooltip?: boolean;
}) {
  const button = (
    <ActionIcon aria-label={label} variant="subtle" color="gray" {...props}>
      <Icon as={icon} size={size} />
    </ActionIcon>
  );
  return tooltip ? (
    <Tooltip label={label} withArrow>
      {button}
    </Tooltip>
  ) : (
    button
  );
}
```

- [ ] **Step 4: Add stories**

Create `apps/web/src/design-system/icons/icons.stories.tsx`:

```tsx
import type { Meta, StoryObj } from "@storybook/react-vite";
import { RiAddLine, RiDeleteBin6Line, RiMicLine, RiSettings3Line } from "@remixicon/react";

import { Icon } from "./Icon";
import { IconButton } from "./IconButton";

function IconsDemo() {
  return (
    <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
      <Icon as={RiAddLine} size={24} />
      <Icon as={RiSettings3Line} size={24} />
      <Icon as={RiMicLine} size={24} />
      <IconButton label="New session" icon={RiAddLine} />
      <IconButton label="Settings" icon={RiSettings3Line} />
      <IconButton label="Delete session" icon={RiDeleteBin6Line} color="red" />
    </div>
  );
}

const meta: Meta<typeof IconsDemo> = { title: "Icons/Overview", component: IconsDemo };
export default meta;
type Story = StoryObj<typeof IconsDemo>;
export const Default: Story = {};
```

- [ ] **Step 5: Run tests and Storybook build**

```powershell
bun run test -- src/design-system/icons
bun run build-storybook
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add apps/web/src/design-system/icons
git commit -m "feat(web): add RemixIcon icon primitives"
```

---

### Task 4: Surface primitives — Button, Panel, Section, PageHeader, Toolbar, Divider, EmptyState, Badge, StatusChip

**Files:**
- Create: `apps/web/src/design-system/primitives/Button.tsx`
- Create: `apps/web/src/design-system/primitives/Panel.tsx`
- Create: `apps/web/src/design-system/primitives/Section.tsx`
- Create: `apps/web/src/design-system/primitives/PageHeader.tsx`
- Create: `apps/web/src/design-system/primitives/Toolbar.tsx`
- Create: `apps/web/src/design-system/primitives/Divider.tsx`
- Create: `apps/web/src/design-system/primitives/EmptyState.tsx`
- Create: `apps/web/src/design-system/primitives/Badge.tsx`
- Create: `apps/web/src/design-system/primitives/StatusChip.tsx`
- Create: `apps/web/src/design-system/primitives/primitives.module.css`
- Create: `apps/web/src/design-system/primitives/primitives.stories.tsx`
- Test: `apps/web/src/design-system/primitives/primitives.test.tsx`

**Interfaces:**
- Produces: `Button`, `Panel` + `Panel.Header` + `Panel.Body`, `Section`, `PageHeader({title, subtitle?, breadcrumbs?, actions?})`, `Toolbar`, `Divider`, `EmptyState({icon, title, description, action?})`, `Badge({tone, children})`, `StatusChip({tone, children})`.
- Tones: `neutral | success | warning | info | danger | agent`.

- [ ] **Step 1: Write failing tests**

Create `apps/web/src/design-system/primitives/primitives.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { RiRobot2Line } from "@remixicon/react";
import { describe, expect, it } from "vitest";

import { EmptyState } from "./EmptyState";
import { PageHeader } from "./PageHeader";
import { Panel } from "./Panel";
import { StatusChip } from "./StatusChip";

describe("surface primitives", () => {
  it("renders a page header with actions", () => {
    render(<PageHeader title="Agents" subtitle="2 configured" actions={<button>New agent</button>} />);
    expect(screen.getByRole("heading", { name: "Agents" })).toBeInTheDocument();
    expect(screen.getByText("2 configured")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New agent" })).toBeInTheDocument();
  });

  it("renders an empty state", () => {
    render(
      <EmptyState icon={RiRobot2Line} title="No agents" description="Create your first agent." />,
    );
    expect(screen.getByText("No agents")).toBeInTheDocument();
    expect(screen.getByText("Create your first agent.")).toBeInTheDocument();
  });

  it("renders panel header and body", () => {
    render(
      <Panel>
        <Panel.Header>Projects</Panel.Header>
        <Panel.Body>content</Panel.Body>
      </Panel>,
    );
    expect(screen.getByText("Projects")).toBeInTheDocument();
    expect(screen.getByText("content")).toBeInTheDocument();
  });

  it("renders status tones", () => {
    render(<StatusChip tone="success">active</StatusChip>);
    expect(screen.getByText("active")).toHaveAttribute("data-tone", "success");
  });
});
```

- [ ] **Step 2: Run to verify failure**

```powershell
bun run test -- src/design-system/primitives
```

Expected: FAIL.

- [ ] **Step 3: Implement the components**

Create `apps/web/src/design-system/primitives/Button.tsx`:

```tsx
import { Button as MantineButton, type ButtonProps } from "@mantine/core";

export function Button({ variant = "filled", ...props }: ButtonProps) {
  return <MantineButton variant={variant} radius="sm" {...props} />;
}
```

Create `apps/web/src/design-system/primitives/Panel.tsx`:

```tsx
import type { ReactNode } from "react";
import styles from "./primitives.module.css";

function PanelRoot({ children, className }: { children: ReactNode; className?: string }) {
  return <section className={`${styles.panel} ${className ?? ""}`}>{children}</section>;
}

function PanelHeader({ children }: { children: ReactNode }) {
  return <header className={styles.panelHeader}>{children}</header>;
}

function PanelBody({ children }: { children: ReactNode }) {
  return <div className={styles.panelBody}>{children}</div>;
}

export const Panel = Object.assign(PanelRoot, { Header: PanelHeader, Body: PanelBody });
```

Create `apps/web/src/design-system/primitives/Section.tsx`:

```tsx
import type { ReactNode } from "react";
import styles from "./primitives.module.css";

export function Section({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <section className={styles.section}>
      {title && <h2 className={styles.sectionTitle}>{title}</h2>}
      {children}
    </section>
  );
}
```

Create `apps/web/src/design-system/primitives/PageHeader.tsx`:

```tsx
import type { ReactNode } from "react";
import styles from "./primitives.module.css";

export function PageHeader({
  title,
  subtitle,
  breadcrumbs,
  actions,
}: {
  title: string;
  subtitle?: string;
  breadcrumbs?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className={styles.pageHeader}>
      {breadcrumbs && <div className={styles.breadcrumbs}>{breadcrumbs}</div>}
      <div className={styles.pageHeaderRow}>
        <div>
          <h1 className={styles.pageTitle}>{title}</h1>
          {subtitle && <p className={styles.pageSubtitle}>{subtitle}</p>}
        </div>
        {actions && <div className={styles.pageActions}>{actions}</div>}
      </div>
    </header>
  );
}
```

Create `apps/web/src/design-system/primitives/Toolbar.tsx`:

```tsx
import type { ReactNode } from "react";
import styles from "./primitives.module.css";

export function Toolbar({ children, align = "space-between" }: { children: ReactNode; align?: "start" | "space-between" }) {
  return <div className={styles.toolbar} data-align={align}>{children}</div>;
}
```

Create `apps/web/src/design-system/primitives/Divider.tsx`:

```tsx
import styles from "./primitives.module.css";

export function Divider() {
  return <hr className={styles.divider} />;
}
```

Create `apps/web/src/design-system/primitives/EmptyState.tsx`:

```tsx
import type { RemixiconComponentType } from "@remixicon/react";
import type { ReactNode } from "react";

import { Icon } from "../icons/Icon";
import styles from "./primitives.module.css";

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon: RemixiconComponentType;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className={styles.emptyState}>
      <Icon as={icon} size={32} />
      <h2>{title}</h2>
      <p>{description}</p>
      {action}
    </div>
  );
}
```

Create `apps/web/src/design-system/primitives/Badge.tsx`:

```tsx
import type { ReactNode } from "react";
import styles from "./primitives.module.css";

export type Tone = "neutral" | "success" | "warning" | "info" | "danger" | "agent";

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return <span className={styles.badge} data-tone={tone}>{children}</span>;
}
```

Create `apps/web/src/design-system/primitives/StatusChip.tsx`:

```tsx
import type { ReactNode } from "react";
import styles from "./primitives.module.css";
import type { Tone } from "./Badge";

export function StatusChip({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={styles.statusChip} data-tone={tone}>
      <span className={styles.statusDot} />
      {children}
    </span>
  );
}
```

Create `apps/web/src/design-system/primitives/primitives.module.css`:

```css
.panel {
  background: var(--ab-surface);
  border: 1px solid var(--ab-border);
  border-radius: var(--ab-radius-sm);
}

.panelHeader {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--ab-space-2);
  padding: var(--ab-space-2) var(--ab-space-3);
  border-bottom: 1px solid var(--ab-border);
  font-family: var(--ab-font-display);
  font-size: 12px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.panelBody {
  padding: var(--ab-space-3);
}

.section {
  display: grid;
  gap: var(--ab-space-3);
}

.sectionTitle {
  margin: 0;
  font-family: var(--ab-font-display);
  font-size: 14px;
  text-transform: uppercase;
}

.pageHeader {
  display: grid;
  gap: var(--ab-space-2);
  margin-bottom: var(--ab-space-4);
}

.breadcrumbs {
  color: var(--ab-text-muted);
  font-family: var(--ab-font-mono);
  font-size: 12px;
}

.pageHeaderRow {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--ab-space-4);
  flex-wrap: wrap;
}

.pageTitle {
  margin: 0;
  font-family: var(--ab-font-display);
  font-size: clamp(22px, 3vw, 32px);
  font-weight: 400;
  text-transform: uppercase;
}

.pageSubtitle {
  margin: var(--ab-space-1) 0 0;
  color: var(--ab-text-muted);
  font-size: var(--ab-text-sm);
}

.pageActions {
  display: flex;
  gap: var(--ab-space-2);
  flex-wrap: wrap;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: var(--ab-space-2);
  flex-wrap: wrap;
}

.toolbar[data-align="space-between"] {
  justify-content: space-between;
}

.divider {
  margin: var(--ab-space-4) 0;
  border: 0;
  border-top: 1px solid var(--ab-border);
}

.emptyState {
  display: grid;
  justify-items: center;
  gap: var(--ab-space-2);
  padding: var(--ab-space-7) var(--ab-space-4);
  border: 1px dashed var(--ab-border);
  text-align: center;
  color: var(--ab-text-muted);
}

.emptyState h2 {
  margin: 0;
  color: var(--ab-text);
  font-family: var(--ab-font-display);
  font-size: 16px;
  text-transform: uppercase;
}

.emptyState p {
  margin: 0;
  max-width: 44ch;
}

.badge,
.statusChip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 8px;
  border: 1px solid var(--ab-border);
  border-radius: 999px;
  font-family: var(--ab-font-mono);
  font-size: 11px;
  line-height: 1.6;
  text-transform: uppercase;
}

.badge[data-tone="success"],
.statusChip[data-tone="success"] { color: var(--ab-phosphor); border-color: var(--ab-phosphor); }
.badge[data-tone="warning"],
.statusChip[data-tone="warning"] { color: var(--ab-amber); border-color: var(--ab-amber); }
.badge[data-tone="info"],
.statusChip[data-tone="info"] { color: var(--ab-cyan); border-color: var(--ab-cyan); }
.badge[data-tone="danger"],
.statusChip[data-tone="danger"] { color: var(--ab-danger); border-color: var(--ab-danger); }
.badge[data-tone="agent"],
.statusChip[data-tone="agent"] { color: var(--ab-magenta); border-color: var(--ab-magenta); }

.statusDot {
  width: 6px;
  height: 6px;
  background: currentColor;
  border-radius: 50%;
}
```

- [ ] **Step 4: Add stories**

Create `apps/web/src/design-system/primitives/primitives.stories.tsx`:

```tsx
import type { Meta, StoryObj } from "@storybook/react-vite";
import { RiRobot2Line } from "@remixicon/react";

import { Button } from "./Button";
import { EmptyState } from "./EmptyState";
import { PageHeader } from "./PageHeader";
import { Panel } from "./Panel";
import { StatusChip } from "./StatusChip";

function PrimitivesDemo() {
  return (
    <div style={{ display: "grid", gap: 24 }}>
      <PageHeader
        title="Agents"
        subtitle="2 configured agents"
        actions={<Button leftSection={<span>+</span>}>New agent</Button>}
      />
      <Panel>
        <Panel.Header>Projects</Panel.Header>
        <Panel.Body>Panel body</Panel.Body>
      </Panel>
      <div style={{ display: "flex", gap: 8 }}>
        <StatusChip tone="success">active</StatusChip>
        <StatusChip tone="warning">degraded</StatusChip>
        <StatusChip tone="danger">error</StatusChip>
      </div>
      <EmptyState icon={RiRobot2Line} title="No agents" description="Create your first agent." action={<Button>Create agent</Button>} />
    </div>
  );
}

const meta: Meta<typeof PrimitivesDemo> = { title: "Primitives/Surfaces", component: PrimitivesDemo };
export default meta;
type Story = StoryObj<typeof PrimitivesDemo>;
export const Default: Story = {};
```

- [ ] **Step 5: Run tests and Storybook build**

```powershell
bun run test -- src/design-system/primitives
bun run build-storybook
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add apps/web/src/design-system/primitives
git commit -m "feat(web): add surface design primitives"
```

---

### Task 5: Feedback primitives — Spinner, Skeleton, CodeBlock, CopyButton, Kbd, Tooltip, Tabs

**Files:**
- Create: `apps/web/src/design-system/primitives/Spinner.tsx`
- Create: `apps/web/src/design-system/primitives/Skeleton.tsx`
- Create: `apps/web/src/design-system/primitives/CodeBlock.tsx`
- Create: `apps/web/src/design-system/primitives/CopyButton.tsx`
- Create: `apps/web/src/design-system/primitives/Kbd.tsx`
- Create: `apps/web/src/design-system/primitives/Tabs.tsx`
- Create: `apps/web/src/design-system/primitives/feedback.module.css`
- Create: `apps/web/src/design-system/primitives/feedback.stories.tsx`
- Test: `apps/web/src/design-system/primitives/feedback.test.tsx`

**Interfaces:**
- Produces: `Spinner({label?})`, `Skeleton({width?, height?})`, `CodeBlock({code, language?})`, `CopyButton({value, label?})`, `Kbd`, `Tabs` re-export.

- [ ] **Step 1: Write failing tests**

Create `apps/web/src/design-system/primitives/feedback.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CodeBlock } from "./CodeBlock";
import { CopyButton } from "./CopyButton";
import { Spinner } from "./Spinner";

describe("feedback primitives", () => {
  it("renders a spinner with a label", () => {
    render(<Spinner label="Thinking" />);
    expect(screen.getByLabelText("Thinking")).toBeInTheDocument();
  });

  it("renders code with a language label", () => {
    render(<CodeBlock code="const x = 1;" language="ts" />);
    expect(screen.getByText("ts")).toBeInTheDocument();
    expect(screen.getByText("const x = 1;")).toBeInTheDocument();
  });

  it("copies a value and shows confirmation", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    render(<CopyButton value="hello" />);
    fireEvent.click(screen.getByRole("button", { name: /copy/i }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("hello"));
    expect(screen.getByText("Copied")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify failure**

```powershell
bun run test -- src/design-system/primitives/feedback
```

Expected: FAIL.

- [ ] **Step 3: Implement**

Create `apps/web/src/design-system/primitives/Spinner.tsx`:

```tsx
import { Loader } from "@mantine/core";

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <span role="status" aria-label={label}>
      <Loader size="sm" color="phosphor" />
    </span>
  );
}
```

Create `apps/web/src/design-system/primitives/Skeleton.tsx`:

```tsx
import styles from "./feedback.module.css";

export function Skeleton({ width = "100%", height = 16 }: { width?: number | string; height?: number }) {
  return <div className={styles.skeleton} style={{ width, height }} aria-hidden="true" />;
}
```

Create `apps/web/src/design-system/primitives/CodeBlock.tsx`:

```tsx
import styles from "./feedback.module.css";

export function CodeBlock({ code, language }: { code: string; language?: string }) {
  return (
    <figure className={styles.codeBlock}>
      {language && <figcaption>{language}</figcaption>}
      <pre><code>{code}</code></pre>
    </figure>
  );
}
```

Create `apps/web/src/design-system/primitives/CopyButton.tsx`:

```tsx
import { RiCheckLine, RiFileCopyLine } from "@remixicon/react";
import { useState } from "react";

import { Icon } from "../icons/Icon";

export function CopyButton({ value, label = "Copy" }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }
  return (
    <button type="button" onClick={copy} aria-label={copied ? "Copied" : label}>
      <Icon as={copied ? RiCheckLine : RiFileCopyLine} size={16} />
      {copied ? "Copied" : label}
    </button>
  );
}
```

Create `apps/web/src/design-system/primitives/Kbd.tsx`:

```tsx
import type { ReactNode } from "react";
import styles from "./feedback.module.css";

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className={styles.kbd}>{children}</kbd>;
}
```

Create `apps/web/src/design-system/primitives/Tabs.tsx`:

```tsx
export { Tabs } from "@mantine/core";
```

Create `apps/web/src/design-system/primitives/feedback.module.css`:

```css
.skeleton {
  background: linear-gradient(90deg, var(--ab-surface-raised), var(--ab-border), var(--ab-surface-raised));
  background-size: 200% 100%;
  animation: ab-shimmer 1.4s linear infinite;
  border-radius: var(--ab-radius-sm);
}

@keyframes ab-shimmer {
  from { background-position: 200% 0; }
  to { background-position: -200% 0; }
}

.codeBlock {
  margin: 0;
  border: 1px solid var(--ab-border);
  background: var(--ab-surface);
}

.codeBlock figcaption {
  padding: 4px 8px;
  border-bottom: 1px solid var(--ab-border);
  color: var(--ab-text-muted);
  font-family: var(--ab-font-mono);
  font-size: 11px;
}

.codeBlock pre {
  margin: 0;
  padding: 12px;
  overflow: auto;
  font-family: var(--ab-font-mono);
  font-size: 13px;
}

.kbd {
  display: inline-block;
  padding: 1px 6px;
  border: 1px solid var(--ab-border);
  border-bottom-width: 2px;
  background: var(--ab-surface-raised);
  font-family: var(--ab-font-mono);
  font-size: 11px;
}

@media (prefers-reduced-motion: reduce) {
  .skeleton { animation: none; }
}
```

- [ ] **Step 4: Add stories and run checks**

Create `apps/web/src/design-system/primitives/feedback.stories.tsx` with variants for all five components. Run:

```powershell
bun run test -- src/design-system/primitives
bun run build-storybook
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src/design-system/primitives
git commit -m "feat(web): add feedback and code primitives"
```

---

### Task 6: Form primitives

**Files:**
- Create: `apps/web/src/design-system/forms/FormField.tsx`
- Create: `apps/web/src/design-system/forms/TextInput.tsx`
- Create: `apps/web/src/design-system/forms/PasswordInput.tsx`
- Create: `apps/web/src/design-system/forms/Textarea.tsx`
- Create: `apps/web/src/design-system/forms/Select.tsx`
- Create: `apps/web/src/design-system/forms/MultiSelect.tsx`
- Create: `apps/web/src/design-system/forms/NumberInput.tsx`
- Create: `apps/web/src/design-system/forms/Checkbox.tsx`
- Create: `apps/web/src/design-system/forms/Switch.tsx`
- Create: `apps/web/src/design-system/forms/FileDropzone.tsx`
- Create: `apps/web/src/design-system/forms/InlineError.tsx`
- Create: `apps/web/src/design-system/forms/FormActions.tsx`
- Create: `apps/web/src/design-system/forms/forms.module.css`
- Create: `apps/web/src/design-system/forms/forms.stories.tsx`
- Test: `apps/web/src/design-system/forms/forms.test.tsx`

**Interfaces:**
- Produces thin wrappers that accept Mantine props: `TextInput`, `PasswordInput`, `Textarea`, `Select`, `MultiSelect`, `NumberInput`, `Checkbox`, `Switch`.
- Produces `FormField({label, description?, error?, required?, children})`, `FileDropzone({onFiles, accept?, multiple?})`, `InlineError`, `FormActions`.

- [ ] **Step 1: Write failing tests**

Create `apps/web/src/design-system/forms/forms.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FormField } from "./FormField";
import { TextInput } from "./TextInput";

describe("form primitives", () => {
  it("renders a label, description, and error", () => {
    render(
      <FormField label="Name" description="Required" error="Name is required" required>
        <TextInput value="" onChange={() => {}} />
      </FormField>,
    );
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Required")).toBeInTheDocument();
    expect(screen.getByText("Name is required")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify failure**

```powershell
bun run test -- src/design-system/forms
```

Expected: FAIL.

- [ ] **Step 3: Implement**

Create `apps/web/src/design-system/forms/FormField.tsx`:

```tsx
import type { ReactNode } from "react";
import styles from "./forms.module.css";

export function FormField({
  label,
  description,
  error,
  required,
  children,
}: {
  label: string;
  description?: string;
  error?: string | null;
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <label className={styles.field}>
      <span className={styles.label}>
        {label}
        {required && <span aria-hidden="true"> *</span>}
      </span>
      {description && <span className={styles.description}>{description}</span>}
      {children}
      {error && <span className={styles.error} role="alert">{error}</span>}
    </label>
  );
}
```

Create wrappers, each forwarding props:

```tsx
// TextInput.tsx
import { TextInput as MantineTextInput, type TextInputProps } from "@mantine/core";
export function TextInput(props: TextInputProps) {
  return <MantineTextInput radius="sm" {...props} />;
}
```

Create `PasswordInput.tsx`:

```tsx
import { PasswordInput as MantinePasswordInput, type PasswordInputProps } from "@mantine/core";
export function PasswordInput(props: PasswordInputProps) {
  return <MantinePasswordInput radius="sm" {...props} />;
}
```

Repeat the same pattern for `Textarea`, `Select`, `MultiSelect`, `NumberInput`, `Checkbox`, `Switch`, importing the corresponding Mantine component and props type.

Create `FileDropzone.tsx`:

```tsx
import { RiUploadCloud2Line } from "@remixicon/react";
import { useRef } from "react";

import { Icon } from "../icons/Icon";
import styles from "./forms.module.css";

export function FileDropzone({
  onFiles,
  accept,
  multiple,
}: {
  onFiles: (files: FileList) => void;
  accept?: string;
  multiple?: boolean;
}) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <div
      className={styles.dropzone}
      onClick={() => ref.current?.click()}
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        if (e.dataTransfer.files.length) onFiles(e.dataTransfer.files);
      }}
    >
      <Icon as={RiUploadCloud2Line} size={24} />
      <span>Drop files or click to browse</span>
      <input
        ref={ref}
        type="file"
        accept={accept}
        multiple={multiple}
        hidden
        onChange={(e) => e.currentTarget.files && onFiles(e.currentTarget.files)}
      />
    </div>
  );
}
```

Create `InlineError.tsx`:

```tsx
export function InlineError({ children }: { children: string }) {
  return <p role="alert" style={{ color: "var(--ab-danger)", margin: 0 }}>{children}</p>;
}
```

Create `FormActions.tsx`:

```tsx
import type { ReactNode } from "react";
import styles from "./forms.module.css";

export function FormActions({ children }: { children: ReactNode }) {
  return <div className={styles.actions}>{children}</div>;
}
```

Create `forms.module.css`:

```css
.field {
  display: grid;
  gap: 4px;
  margin-bottom: var(--ab-space-3);
}

.label {
  color: var(--ab-text);
  font-family: var(--ab-font-mono);
  font-size: 12px;
  text-transform: uppercase;
}

.description {
  color: var(--ab-text-muted);
  font-size: 12px;
}

.error {
  color: var(--ab-danger);
  font-size: 12px;
}

.dropzone {
  display: grid;
  justify-items: center;
  gap: 8px;
  padding: 24px;
  border: 1px dashed var(--ab-border);
  color: var(--ab-text-muted);
  cursor: pointer;
}

.dropzone:hover {
  border-color: var(--ab-phosphor);
  color: var(--ab-text);
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--ab-space-2);
  margin-top: var(--ab-space-4);
}
```

- [ ] **Step 4: Add stories and run checks**

Create `forms.stories.tsx` with a form demo using `FormField`, `TextInput`, `Select`, `Checkbox`, and `FormActions`. Run:

```powershell
bun run test -- src/design-system/forms
bun run build-storybook
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src/design-system/forms
git commit -m "feat(web): add design system form primitives"
```

---

### Task 7: Data primitives — DataTable, ListRow, TableToolbar, Pagination

**Files:**
- Create: `apps/web/src/design-system/data/DataTable.tsx`
- Create: `apps/web/src/design-system/data/ListRow.tsx`
- Create: `apps/web/src/design-system/data/TableToolbar.tsx`
- Create: `apps/web/src/design-system/data/Pagination.tsx`
- Create: `apps/web/src/design-system/data/data.module.css`
- Create: `apps/web/src/design-system/data/data.stories.tsx`
- Test: `apps/web/src/design-system/data/data.test.tsx`

**Interfaces:**
- `DataTable<T>({ columns, rows, rowKey, empty? })` where `columns: { key: string; header: string; render: (row: T) => ReactNode }[]`.
- `ListRow({ title, subtitle?, meta?, actions? })`, `TableToolbar`, `Pagination({page, totalPages, onChange})`.

- [ ] **Step 1: Write failing tests**

Create `apps/web/src/design-system/data/data.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DataTable } from "./DataTable";

type Row = { id: string; name: string };

describe("DataTable", () => {
  it("renders headers and rows", () => {
    render(
      <DataTable<Row>
        rowKey={(row) => row.id}
        columns={[{ key: "name", header: "Name", render: (row) => row.name }]}
        rows={[{ id: "1", name: "alpha" }]}
      />,
    );
    expect(screen.getByRole("columnheader", { name: "Name" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "alpha" })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify failure**

```powershell
bun run test -- src/design-system/data
```

Expected: FAIL.

- [ ] **Step 3: Implement DataTable**

Create `apps/web/src/design-system/data/DataTable.tsx`:

```tsx
import type { ReactNode } from "react";
import styles from "./data.module.css";

export type DataColumn<T> = {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
};

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  empty,
}: {
  columns: DataColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  empty?: ReactNode;
}) {
  if (rows.length === 0 && empty) return <>{empty}</>;
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>{columns.map((column) => <th key={column.key}>{column.header}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)}>
              {columns.map((column) => <td key={column.key}>{column.render(row)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

Create `ListRow.tsx`:

```tsx
import type { ReactNode } from "react";
import styles from "./data.module.css";

export function ListRow({
  title,
  subtitle,
  meta,
  actions,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className={styles.listRow}>
      <div className={styles.listRowMain}>
        <strong>{title}</strong>
        {subtitle && <span>{subtitle}</span>}
      </div>
      {meta && <div className={styles.listRowMeta}>{meta}</div>}
      {actions && <div className={styles.listRowActions}>{actions}</div>}
    </div>
  );
}
```

Create `TableToolbar.tsx`:

```tsx
import type { ReactNode } from "react";
import styles from "./data.module.css";

export function TableToolbar({ children }: { children: ReactNode }) {
  return <div className={styles.tableToolbar}>{children}</div>;
}
```

Create `Pagination.tsx`:

```tsx
import { Pagination as MantinePagination } from "@mantine/core";

export function Pagination({
  page,
  totalPages,
  onChange,
}: {
  page: number;
  totalPages: number;
  onChange: (page: number) => void;
}) {
  return (
    <MantinePagination
      value={page}
      total={totalPages}
      onChange={onChange}
      size="sm"
      color="phosphor"
      mt="md"
    />
  );
}
```

Create `data.module.css` with responsive table overflow and stacked row behavior:

```css
.tableWrap {
  width: 100%;
  overflow-x: auto;
  border: 1px solid var(--ab-border);
  background: var(--ab-surface);
}

.table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--ab-text-sm);
}

.table th {
  padding: 10px 12px;
  border-bottom: 1px solid var(--ab-border);
  color: var(--ab-text-muted);
  font-family: var(--ab-font-mono);
  font-size: 11px;
  text-align: left;
  text-transform: uppercase;
}

.table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--ab-border);
  vertical-align: middle;
}

.table tr:last-child td {
  border-bottom: 0;
}

.listRow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--ab-space-3);
  padding: var(--ab-space-3);
  border-bottom: 1px solid var(--ab-border);
  flex-wrap: wrap;
}

.listRowMain {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.listRowMain span {
  color: var(--ab-text-muted);
  font-size: var(--ab-text-sm);
}

.listRowMeta,
.listRowActions {
  display: flex;
  align-items: center;
  gap: var(--ab-space-2);
}

.tableToolbar {
  display: flex;
  align-items: center;
  gap: var(--ab-space-2);
  flex-wrap: wrap;
  margin-bottom: var(--ab-space-3);
}

@media (max-width: 767px) {
  .table th,
  .table td {
    white-space: nowrap;
  }
  .listRow {
    align-items: flex-start;
  }
}
```

Add stories for a 3-column table and long-content row.

- [ ] **Step 4: Run tests and Storybook build**

```powershell
bun run test -- src/design-system/data
bun run build-storybook
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src/design-system/data
git commit -m "feat(web): add data display primitives"
```

---

### Task 8: Overlay primitives — Modal, ConfirmDialog, Drawer

**Files:**
- Create: `apps/web/src/design-system/overlays/Modal.tsx`
- Create: `apps/web/src/design-system/overlays/ConfirmDialog.tsx`
- Create: `apps/web/src/design-system/overlays/Drawer.tsx`
- Create: `apps/web/src/design-system/overlays/overlays.stories.tsx`
- Test: `apps/web/src/design-system/overlays/overlays.test.tsx`

**Interfaces:**
- `Modal` is a thin Mantine wrapper.
- `ConfirmDialog({opened, title, description, confirmLabel?, cancelLabel?, danger?, onConfirm, onClose})`.
- `Drawer` is a thin Mantine wrapper.

- [ ] **Step 1: Write failing test**

Create `overlays.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ConfirmDialog } from "./ConfirmDialog";

describe("ConfirmDialog", () => {
  it("calls onConfirm from the confirm button", () => {
    const onConfirm = vi.fn();
    render(
      <ConfirmDialog
        opened
        title="Delete project?"
        description="This cannot be undone."
        confirmLabel="Delete"
        danger
        onConfirm={onConfirm}
        onClose={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(onConfirm).toHaveBeenCalledOnce();
  });
});
```

- [ ] **Step 2: Run to verify failure**

```powershell
bun run test -- src/design-system/overlays
```

Expected: FAIL.

- [ ] **Step 3: Implement**

Create `Modal.tsx`:

```tsx
import { Modal as MantineModal, type ModalProps } from "@mantine/core";

export function Modal(props: ModalProps) {
  return <MantineModal radius="md" centered {...props} />;
}
```

Create `Drawer.tsx`:

```tsx
import { Drawer as MantineDrawer, type DrawerProps } from "@mantine/core";

export function Drawer(props: DrawerProps) {
  return <MantineDrawer radius="md" position="right" {...props} />;
}
```

Create `ConfirmDialog.tsx`:

```tsx
import { Button, Group } from "@mantine/core";

import { Modal } from "./Modal";

export function ConfirmDialog({
  opened,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger,
  onConfirm,
  onClose,
}: {
  opened: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <Modal opened={opened} onClose={onClose} title={title}>
      <p>{description}</p>
      <Group justify="flex-end" mt="md">
        <Button variant="light" onClick={onClose}>{cancelLabel}</Button>
        <Button color={danger ? "danger" : "phosphor"} onClick={onConfirm}>
          {confirmLabel}
        </Button>
      </Group>
    </Modal>
  );
}
```

Add stories and run tests + Storybook.

- [ ] **Step 4: Commit**

```powershell
git add apps/web/src/design-system/overlays
git commit -m "feat(web): add overlay primitives"
```

---

### Task 9: Navigation primitives — AppRail, RailItem, Breadcrumbs, MobileNav, UserMenu

**Files:**
- Create: `apps/web/src/design-system/navigation/AppRail.tsx`
- Create: `apps/web/src/design-system/navigation/RailItem.tsx`
- Create: `apps/web/src/design-system/navigation/Breadcrumbs.tsx`
- Create: `apps/web/src/design-system/navigation/MobileNav.tsx`
- Create: `apps/web/src/design-system/navigation/UserMenu.tsx`
- Create: `apps/web/src/design-system/navigation/navigation.module.css`
- Create: `apps/web/src/design-system/navigation/navigation.stories.tsx`
- Test: `apps/web/src/design-system/navigation/navigation.test.tsx`

**Interfaces:**
- `RailItem({to, label, icon, end?})` uses React Router `NavLink`; active state via `aria-current`.
- `AppRail({items, footer})`, `Breadcrumbs({items})`, `MobileNav({items})`, `UserMenu({username, onLogout})`.

- [ ] **Step 1: Write failing tests**

Create `navigation.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { RiHome5Line } from "@remixicon/react";
import { describe, expect, it } from "vitest";

import { RailItem } from "./RailItem";

describe("RailItem", () => {
  it("marks the active route", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <RailItem to="/" label="Home" icon={RiHome5Line} end />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute("aria-current", "page");
  });
});
```

- [ ] **Step 2: Run to verify failure**

```powershell
bun run test -- src/design-system/navigation
```

Expected: FAIL.

- [ ] **Step 3: Implement RailItem and AppRail**

Create `RailItem.tsx`:

```tsx
import type { RemixiconComponentType } from "@remixicon/react";
import { NavLink } from "react-router-dom";

import { Icon } from "../icons/Icon";
import styles from "./navigation.module.css";

export function RailItem({
  to,
  label,
  icon,
  end,
}: {
  to: string;
  label: string;
  icon: RemixiconComponentType;
  end?: boolean;
}) {
  return (
    <NavLink
      to={to}
      end={end}
      className={styles.railItem}
      aria-label={label}
      title={label}
    >
      {({ isActive }) => (
        <>
          <Icon as={icon} size={20} />
          <span className={styles.railLabel}>{label}</span>
          {isActive && <span className={styles.railActive} aria-hidden="true" />}
        </>
      )}
    </NavLink>
  );
}
```

Create `AppRail.tsx`:

```tsx
import type { ReactNode } from "react";
import styles from "./navigation.module.css";

export function AppRail({ children, footer }: { children: ReactNode; footer?: ReactNode }) {
  return (
    <nav className={styles.rail} aria-label="Primary navigation">
      <div className={styles.railBrand} aria-label="Agentbox">[A]</div>
      <div className={styles.railItems}>{children}</div>
      <div className={styles.railFooter}>{footer}</div>
    </nav>
  );
}
```

Add `Breadcrumbs`, `MobileNav`, `UserMenu`, and `navigation.module.css` with rail width 56px, active phosphor edge, mobile segmented styles.

- [ ] **Step 4: Add stories; run tests and Storybook**

```powershell
bun run test -- src/design-system/navigation
bun run build-storybook
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src/design-system/navigation
git commit -m "feat(web): add navigation primitives"
```

---

### Task 10: Page patterns — AuthCard, DashboardCard, ListPage, SettingsPage, AdminTablePage

**Files:**
- Create: `apps/web/src/design-system/patterns/AuthCard.tsx`
- Create: `apps/web/src/design-system/patterns/DashboardCard.tsx`
- Create: `apps/web/src/design-system/patterns/ListPage.tsx`
- Create: `apps/web/src/design-system/patterns/SettingsPage.tsx`
- Create: `apps/web/src/design-system/patterns/AdminTablePage.tsx`
- Create: `apps/web/src/design-system/patterns/EmptyStatePanel.tsx`
- Create: `apps/web/src/design-system/patterns/patterns.module.css`
- Create: `apps/web/src/design-system/patterns/patterns.stories.tsx`
- Test: `apps/web/src/design-system/patterns/patterns.test.tsx`

**Interfaces:**
- `ListPage({title, subtitle?, actions?, toolbar?, children})`, `SettingsPage`, `AdminTablePage`, `AuthCard({title, subtitle?, children})`, `DashboardCard({label, value, hint?, icon?})`, `EmptyStatePanel`.

- [ ] **Step 1: Write failing tests**

Create `patterns.test.tsx` that renders `AuthCard`, `ListPage`, and `DashboardCard` and asserts headings/labels. Run:

```powershell
bun run test -- src/design-system/patterns
```

Expected: FAIL.

- [ ] **Step 2: Implement the patterns**

Create `AuthCard.tsx`:

```tsx
import type { ReactNode } from "react";
import styles from "./patterns.module.css";

export function AuthCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <div className={styles.authShell}>
      <div className={styles.authCard}>
        <div className={styles.authBrand}>[AGENTBOX]▮</div>
        <p className={styles.authStatus}>operator console · secure session</p>
        <h1>{title}</h1>
        {subtitle && <p className={styles.authSubtitle}>{subtitle}</p>}
        {children}
      </div>
    </div>
  );
}
```

Create `ListPage.tsx`:

```tsx
import type { ReactNode } from "react";

import { PageHeader } from "../primitives/PageHeader";

export function ListPage({
  title,
  subtitle,
  actions,
  toolbar,
  children,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  toolbar?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div>
      <PageHeader title={title} subtitle={subtitle} actions={actions} />
      {toolbar}
      {children}
    </div>
  );
}
```

Create `DashboardCard.tsx`:

```tsx
import type { ReactNode } from "react";
import styles from "./patterns.module.css";

export function DashboardCard({
  label,
  value,
  hint,
  icon,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  icon?: ReactNode;
}) {
  return (
    <div className={styles.dashboardCard}>
      <div className={styles.dashboardCardTop}>
        <span>{label}</span>
        {icon}
      </div>
      <strong>{value}</strong>
      {hint && <small>{hint}</small>}
    </div>
  );
}
```

Create `SettingsPage.tsx` and `AdminTablePage.tsx` as `ListPage` compositions; create `EmptyStatePanel.tsx` as a `Panel` + `EmptyState` wrapper. Add `patterns.module.css`:

```css
.authShell {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: var(--ab-space-5);
  background: var(--ab-canvas);
}

.authCard {
  width: min(440px, 100%);
  display: grid;
  gap: var(--ab-space-3);
  padding: var(--ab-space-6);
  border: 1px solid var(--ab-border);
  background: var(--ab-surface);
  box-shadow: 6px 6px 0 var(--ab-border);
}

.authBrand {
  font-family: var(--ab-font-display);
  font-size: 20px;
  letter-spacing: 0.04em;
}

.authStatus,
.authSubtitle {
  margin: 0;
  color: var(--ab-text-muted);
  font-family: var(--ab-font-mono);
  font-size: 12px;
}

.dashboardCard {
  display: grid;
  gap: var(--ab-space-2);
  padding: var(--ab-space-4);
  border: 1px solid var(--ab-border);
  background: var(--ab-surface);
}

.dashboardCardTop {
  display: flex;
  justify-content: space-between;
  color: var(--ab-text-muted);
  font-family: var(--ab-font-mono);
  font-size: 11px;
  text-transform: uppercase;
}

.dashboardCard strong {
  color: var(--ab-phosphor);
  font-family: var(--ab-font-display);
  font-size: 32px;
  font-weight: 400;
}

.dashboardCard small {
  color: var(--ab-text-muted);
}
```

- [ ] **Step 3: Add stories; run tests and Storybook**

```powershell
bun run test -- src/design-system/patterns
bun run build-storybook
```

Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
git add apps/web/src/design-system/patterns
git commit -m "feat(web): add page patterns"
```

---

### Task 11: CommandShell desktop and routing integration

**Files:**
- Create: `apps/web/src/design-system/shell/CommandShell.tsx`
- Create: `apps/web/src/design-system/shell/PageContainer.tsx`
- Create: `apps/web/src/design-system/shell/Workspace.tsx`
- Create: `apps/web/src/design-system/shell/shell.module.css`
- Create: `apps/web/src/design-system/shell/CommandShell.test.tsx`
- Create temporarily: `apps/web/src/design-system/navigation/ProjectPanel.tsx` (re-export `ProjectTree`; Task 12 replaces it)
- Modify: `apps/web/src/App.tsx`
- Delete: `apps/web/src/components/layout/AppShell.tsx`

**Interfaces:**
- `CommandShell` reads auth permissions, renders `AppRail`, project panel placeholder (`ProjectPanel` from Task 12), workspace `<Outlet />`, and theme/user footer.
- `PageContainer({children, fullBleed?})` applies max-width 1200 and gutters.

- [ ] **Step 1: Write failing shell test**

Create `CommandShell.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { useAuthStore } from "../../store/auth";
import { ThemeProvider } from "../theme/ThemeProvider";
import { CommandShell } from "./CommandShell";

vi.mock("../navigation/ProjectPanel", () => ({
  ProjectPanel: () => <div>projects</div>,
}));

describe("CommandShell", () => {
  it("renders primary navigation and the outlet", () => {
    useAuthStore.setState({
      token: "t",
      user: { id: "1", username: "admin", permissions: ["agents:create", "api_keys:manage"] },
    });
    render(
      <ThemeProvider forceScheme="dark">
        <MemoryRouter initialEntries={["/"]}>
          <Routes>
            <Route element={<CommandShell />}>
              <Route index element={<div>workspace</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </ThemeProvider>,
    );
    expect(screen.getByRole("navigation", { name: "Primary navigation" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Agents" })).toBeInTheDocument();
    expect(screen.getByText("workspace")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify failure**

```powershell
bun run test -- src/design-system/shell
```

Expected: FAIL.

- [ ] **Step 3: Implement CommandShell**

Create the temporary `ProjectPanel` bridge so the new shell can compile before Task 12:

`apps/web/src/design-system/navigation/ProjectPanel.tsx`:

```tsx
export { ProjectTree as ProjectPanel } from "../../components/projects/ProjectTree";
```

Create `CommandShell.tsx`:

```tsx
import {
  RiBookOpenLine,
  RiHome5Line,
  RiKey2Line,
  RiRobot2Line,
  RiServerLine,
  RiShieldUserLine,
} from "@remixicon/react";
import type { RemixiconComponentType } from "@remixicon/react";
import { Outlet, useNavigate } from "react-router-dom";

import { useAuthStore } from "../../store/auth";
import { AppRail } from "../navigation/AppRail";
import { ProjectPanel } from "../navigation/ProjectPanel";
import { RailItem } from "../navigation/RailItem";
import { UserMenu } from "../navigation/UserMenu";
import { ThemeToggle } from "../theme/ThemeToggle";
import { Workspace } from "./Workspace";
import styles from "./shell.module.css";

type NavItem = {
  to: string;
  label: string;
  icon: RemixiconComponentType;
  end?: boolean;
  permission?: string | string[];
};

const items: NavItem[] = [
  { to: "/", label: "Home", icon: RiHome5Line, end: true },
  { to: "/agents", label: "Agents", icon: RiRobot2Line },
  { to: "/providers", label: "Providers", icon: RiServerLine },
  { to: "/skills", label: "Skills", icon: RiBookOpenLine },
  { to: "/api-keys", label: "API keys", icon: RiKey2Line, permission: "api_keys:manage" },
  {
    to: "/admin",
    label: "Admin",
    icon: RiShieldUserLine,
    permission: ["roles:manage", "users:manage"],
  },
];

function allowed(permissions: string[], required?: string | string[]) {
  if (!required) return true;
  const list = Array.isArray(required) ? required : [required];
  return list.some((permission) => permissions.includes(permission));
}

export function CommandShell() {
  const user = useAuthStore((state) => state.user);
  const clear = useAuthStore((state) => state.clear);
  const navigate = useNavigate();
  const permissions = user?.permissions ?? [];
  const visible = items.filter((item) => allowed(permissions, item.permission));

  function logout() {
    clear();
    navigate("/login");
  }

  return (
    <div className={styles.shell}>
      <AppRail
        footer={
          <>
            <ThemeToggle />
            <UserMenu username={user?.username ?? "operator"} onLogout={logout} />
          </>
        }
      >
        {visible.map((item) => (
          <RailItem
            key={item.to}
            to={item.to}
            label={item.label}
            icon={item.icon}
            end={item.end}
          />
        ))}
      </AppRail>
      <aside className={styles.projectPane} aria-label="Projects">
        <ProjectPanel />
      </aside>
      <Workspace>
        <Outlet />
      </Workspace>
    </div>
  );
}
```

Create `Workspace.tsx`:

```tsx
import type { ReactNode } from "react";
import styles from "./shell.module.css";

export function Workspace({ children }: { children: ReactNode }) {
  return <main className={styles.workspace}>{children}</main>;
}
```

Create `PageContainer.tsx`:

```tsx
import type { ReactNode } from "react";
import styles from "./shell.module.css";

export function PageContainer({
  children,
  fullBleed,
}: {
  children: ReactNode;
  fullBleed?: boolean;
}) {
  return (
    <div className={fullBleed ? styles.fullBleed : styles.container}>{children}</div>
  );
}
```

`shell.module.css` defines the grid:

```css
.shell {
  display: grid;
  grid-template-columns: var(--ab-rail-width) var(--ab-panel-width) minmax(0, 1fr);
  min-height: 100vh;
  background: var(--ab-canvas);
}
.projectPane {
  min-width: 0;
  border-right: 1px solid var(--ab-border);
  background: var(--ab-surface);
  overflow: hidden;
}
.workspace {
  min-width: 0;
  overflow: auto;
  padding: var(--ab-space-5);
}
.container {
  width: 100%;
  max-width: var(--ab-content-max);
  margin: 0 auto;
}
.fullBleed {
  width: 100%;
}
```

Modify `App.tsx` import to `CommandShell` and use it in the layout route. Delete the old `AppShell.tsx` in this task; routing still points at the new shell.

- [ ] **Step 4: Run tests and build**

```powershell
bun run test -- src/design-system/shell
bun run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src/App.tsx apps/web/src/design-system/shell
git commit -m "feat(web): add command shell layout"
```

---

### Task 12: ProjectPanel with design-system tree controls

**Files:**
- Create: `apps/web/src/design-system/navigation/ProjectPanel.tsx`
- Create: `apps/web/src/design-system/navigation/ProjectItem.tsx`
- Create: `apps/web/src/design-system/navigation/SessionItem.tsx`
- Create: `apps/web/src/design-system/navigation/ProjectPanel.test.tsx`
- Create: `apps/web/src/design-system/navigation/project-panel.module.css`
- Modify: `apps/web/src/design-system/shell/CommandShell.tsx`
- Delete: `apps/web/src/components/projects/ProjectTree.tsx`
- Replace: `apps/web/src/components/projects/ProjectTree.test.tsx` with `ProjectPanel.test.tsx`

**Interfaces:**
- `ProjectPanel` consumes `useProjects`, `useSessions`, `useDeleteProject`, `useDeleteSession`; opens `NewProjectModal`, `NewSessionModal`.
- Project row actions: `IconButton` for settings (`RiSettings3Line`), new session (`RiAddLine`), delete (`RiDeleteBin6Line`).
- Session row: link + delete icon.

- [ ] **Step 1: Write failing ProjectPanel test**

Create `ProjectPanel.test.tsx` that mocks the query hooks and renders two projects + one session; assert project name, `New session in Demo` accessible label, and that action buttons are present. Run:

```powershell
bun run test -- src/design-system/navigation/ProjectPanel
```

Expected: FAIL.

- [ ] **Step 2: Implement ProjectPanel**

Move the logic from `ProjectTree.tsx` into `ProjectPanel`. Use `Panel`, `IconButton`, `Toolbar`, `EmptyState`, and `ConfirmDialog` for session deletion. Project deletion keeps current immediate behavior in UX-1 (UX-4 owns confirmations). Wrap actions in a nowrap flex container. Delete `ProjectTree.tsx` and port its test file to `ProjectPanel.test.tsx`.

Create `ProjectPanel.tsx` with this structure (keep the existing hooks/modal behavior from `ProjectTree`):

```tsx
import { RiAddLine, RiDeleteBin6Line, RiSettings3Line } from "@remixicon/react";
import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { NewProjectModal } from "../../components/projects/NewProjectModal";
import { NewSessionModal } from "../../components/projects/NewSessionModal";
import {
  useDeleteProject,
  useDeleteSession,
  useProjects,
  useSessions,
} from "../../api/queries";
import { IconButton } from "../icons/IconButton";
import { EmptyState } from "../primitives/EmptyState";
import { Panel } from "../primitives/Panel";
import styles from "./project-panel.module.css";

export function ProjectPanel() {
  const { data: projects, isLoading, error } = useProjects();
  const { data: sessions } = useSessions();
  const deleteProject = useDeleteProject();
  const deleteSession = useDeleteSession();
  const navigate = useNavigate();
  const location = useLocation();
  const [projectOpen, setProjectOpen] = useState(false);
  const [editProject, setEditProject] = useState<string | null>(null);
  const [sessionProject, setSessionProject] = useState<string | null>(null);

  if (isLoading) return <p className={styles.muted}>Loading projects…</p>;
  if (error) return <p className={styles.muted}>Failed to load projects</p>;

  return (
    <Panel>
      <Panel.Header>
        <span>Projects</span>
        <IconButton label="New project" icon={RiAddLine} onClick={() => setProjectOpen(true)} />
      </Panel.Header>
      <Panel.Body>
        {(projects ?? []).length === 0 ? (
          <EmptyState
            icon={RiSettings3Line}
            title="No projects"
            description="Create a project to start a session."
          />
        ) : (
          <ul className={styles.list}>
            {(projects ?? []).map((project) => {
              const projectSessions = (sessions ?? [])
                .filter((session) => session.project_id === project.id)
                .sort((a, b) => (a.created_at ?? "").localeCompare(b.created_at ?? ""));
              return (
                <li key={project.id} className={styles.project}>
                  <div className={styles.projectRow}>
                    <span className={styles.projectName}>{project.name}</span>
                    <div className={styles.actions}>
                      <IconButton label={`Settings ${project.name}`} icon={RiSettings3Line} onClick={() => setEditProject(project.id)} />
                      <IconButton label={`New session in ${project.name}`} icon={RiAddLine} onClick={() => setSessionProject(project.id)} />
                      <IconButton label={`Delete ${project.name}`} icon={RiDeleteBin6Line} color="red" onClick={() => deleteProject.mutate(project.id)} />
                    </div>
                  </div>
                  <ul className={styles.sessions}>
                    {projectSessions.map((session, index) => (
                      <li key={session.id} className={styles.sessionRow}>
                        <Link to={`/sessions/${session.id}`}>Session {index + 1}</Link>
                        <IconButton
                          label={`Delete session ${session.id}`}
                          icon={RiDeleteBin6Line}
                          size={16}
                          color="red"
                          onClick={() => deleteSession.mutate(session.id, { onSuccess: () => {
                            if (location.pathname === `/sessions/${session.id}`) navigate("/");
                          } })}
                        />
                      </li>
                    ))}
                  </ul>
                </li>
              );
            })}
          </ul>
        )}
      </Panel.Body>
      <NewProjectModal opened={projectOpen} onClose={() => setProjectOpen(false)} />
      <NewProjectModal opened={editProject !== null} onClose={() => setEditProject(null)} project={editProject ? projects?.find((p) => p.id === editProject) ?? null : null} />
      <NewSessionModal opened={sessionProject !== null} onClose={() => setSessionProject(null)} projectId={sessionProject ?? ""} />
    </Panel>
  );
}
```

Create `project-panel.module.css` with `.list`, `.project`, `.projectRow`, `.actions` (`display:flex; flex-wrap:nowrap; gap:2px`), `.sessions`, `.sessionRow`, `.projectName` (truncate), and `.muted` styles.

- [ ] **Step 3: Use ProjectPanel in CommandShell**

`CommandShell` already renders `<ProjectPanel />` in the middle pane (from the temporary bridge); no old `<ProjectTree />` reference remains.

- [ ] **Step 4: Run tests**

```powershell
bun run test -- src/design-system/navigation/ProjectPanel
bun run test -- src/components/projects
```

Expected: PASS (`ProjectPanel.test.tsx` replaces `ProjectTree.test.tsx`).

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src/design-system/navigation apps/web/src/components/projects apps/web/src/design-system/shell
git commit -m "feat(web): add project panel"
```

---

### Task 13: Responsive shell — top segmented nav and project sheet

**Files:**
- Modify: `apps/web/src/design-system/shell/CommandShell.tsx`
- Modify: `apps/web/src/design-system/shell/shell.module.css`
- Modify: `apps/web/src/design-system/navigation/MobileNav.tsx`
- Create: `apps/web/src/design-system/navigation/ProjectSheet.tsx`
- Test: `apps/web/src/design-system/shell/responsive.test.tsx`

**Interfaces:**
- Below 1100px: `MobileNav` renders a horizontally scrollable segmented nav with icon + label.
- Below 768px: a "Projects" button opens `ProjectSheet` (Mantine Drawer) containing `ProjectPanel`.
- Theme toggle and user menu appear in the top bar on mobile.

- [ ] **Step 1: Write failing responsive test**

Use `window.matchMedia` mock in `src/test/setup.ts` to return `matches: true` for `(max-width: 1099px)`. Render `CommandShell` and assert `MobileNav` is present and the rail has `aria-hidden` or is not rendered. Run:

```powershell
bun run test -- src/design-system/shell/responsive
```

Expected: FAIL.

- [ ] **Step 2: Implement responsive behavior**

Update `shell.module.css` with media queries at `1100px` and `768px`. Use a `useMediaQuery` hook from `@mantine/hooks` in `CommandShell` to switch between rail and mobile nav. Add `ProjectSheet` using `Drawer` with a "Projects" trigger in the mobile top bar.

- [ ] **Step 3: Run tests and build**

```powershell
bun run test -- src/design-system/shell
bun run build
```

Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
git add apps/web/src/design-system/shell apps/web/src/design-system/navigation
git commit -m "feat(web): make command shell responsive"
```

---

### Task 14: Migrate Login to AuthCard

**Files:**
- Modify: `apps/web/src/pages/LoginPage.tsx`
- Modify: `apps/web/src/pages/LoginPage.test.tsx`
- Create: `apps/web/src/pages/login.module.css`

**Interfaces:**
- Keeps existing `onSubmit` login behavior and error message.
- Uses `AuthCard`, `FormField`, `TextInput`, `Button`, `InlineError`.

- [ ] **Step 1: Update the login test**

Replace the current assertions with role-based assertions for `heading "Login"`, `textbox "Username"`, `textbox "Password"`, `button "Log in"`. Add a test that an invalid login renders `Invalid credentials`. Run:

```powershell
bun run test -- src/pages/LoginPage
```

Expected: FAIL until the page uses the new components (or passes if roles are unchanged; then add a visual-only assertion for `data-testid="auth-card"`).

- [ ] **Step 2: Rewrite LoginPage**

Wrap the form in `AuthCard`, add the `[AGENTBOX]▮` mark and a terminal status line. Use `FormField` + DS `TextInput` for the username and DS `PasswordInput` for the password, `InlineError` for the error, and DS `Button type="submit"` with `loading` state. Add `autoComplete="username"` / `"current-password"`.

- [ ] **Step 3: Run tests**

```powershell
bun run test -- src/pages/LoginPage
```

Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
git add apps/web/src/pages/LoginPage.tsx apps/web/src/pages/LoginPage.test.tsx apps/web/src/pages/login.module.css
git commit -m "feat(web): restyle login page"
```

---

### Task 15: Migrate Home to command-center dashboard

**Files:**
- Modify: `apps/web/src/pages/HomePage.tsx`
- Create: `apps/web/src/pages/HomePage.test.tsx`
- Create: `apps/web/src/pages/home.module.css`

**Interfaces:**
- Uses `useProjects`, `useSessions`, `ListPage`, `PageHeader`, `DashboardCard`, `Panel`, `EmptyState`, `Button`, `Link`.

- [ ] **Step 1: Write failing Home test**

Mock `useProjects` and `useSessions` to return one project and one session. Assert the welcome heading, project name, session link, and `New project` action. Run:

```powershell
bun run test -- src/pages/HomePage
```

Expected: FAIL.

- [ ] **Step 2: Implement the dashboard**

Render a `PageContainer` with:
- A terminal hero panel containing `[AGENTBOX]▮`, a short line ("Operator console for agentic work"), and primary actions (New project, View agents).
- A grid of `DashboardCard`s for project count, session count, agent count (use `useAgents` if available; otherwise omit).
- A `Panel` listing recent sessions with links.
- An `EmptyState` when no projects exist.

- [ ] **Step 3: Run tests and build**

```powershell
bun run test -- src/pages/HomePage
bun run build
```

Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
git add apps/web/src/pages/HomePage.tsx apps/web/src/pages/HomePage.test.tsx apps/web/src/pages/home.module.css
git commit -m "feat(web): add command center home dashboard"
```

---

### Task 16: Migrate Agents page to ListPage and create drawer

**Files:**
- Modify: `apps/web/src/pages/AgentsPage.tsx`
- Create: `apps/web/src/pages/agents/AgentCreateDrawer.tsx`
- Create: `apps/web/src/pages/agents/AgentList.tsx`
- Create: `apps/web/src/pages/agents/agents.module.css`
- Modify: `apps/web/src/pages/AgentsPage.test.tsx`

**Interfaces:**
- `AgentCreateDrawer({opened, onClose})` owns the existing create state/handlers and calls `useCreateAgent`, `useUploadAvatar`.
- `AgentList` renders agent cards/table with `Change photo`, `Remove photo`, `A2A`, `Delete` icon actions.
- Keeps `NATIVE_TOOLS`, `TERMINAL_TOOLS`, `buildToolBindings` exports.

- [ ] **Step 1: Update tests**

Keep the existing behavior tests for creating an agent and changing an avatar. Add an assertion that the create form opens in a drawer titled `New agent` and that the list uses a `PageHeader` with `New agent` action. Run:

```powershell
bun run test -- src/pages/AgentsPage
```

Expected: FAIL.

- [ ] **Step 2: Extract the form into AgentCreateDrawer**

Move the `name`, `description`, `instructions`, `modelRef`, tools, MCP, modes, sub-agents, photo, versions, preview state and handlers from `AgentsPage.tsx` into `AgentCreateDrawer.tsx`. Use `Drawer`, `FormField`, `TextInput`, `Textarea`, `Select`, `MultiSelect`, `Checkbox`, `FileDropzone`, `FormActions`, `Section`, `Button`.

Group the form into:
- Identity (name, description, instructions, model)
- Capabilities (native tools grouped by filesystem/web/terminal; MCP servers)
- Behavior (modes, sub-agents)
- Presentation (photo)

Keep the existing `Tool` checkbox list data; render with `Checkbox` and a compact two-column grid.

- [ ] **Step 3: Rebuild the list**

Use `ListPage` with `PageHeader` actions (`New agent`), a `Toolbar` search/filter, and `AgentList` cards. Each card shows avatar, name, description, model/label chip, and icon actions.

- [ ] **Step 4: Run tests and build**

```powershell
bun run test -- src/pages/AgentsPage
bun run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src/pages/AgentsPage.tsx apps/web/src/pages/agents apps/web/src/pages/AgentsPage.test.tsx
git commit -m "feat(web): restyle agents page"
```

---

### Task 17: Migrate Providers/Models page

**Files:**
- Modify: `apps/web/src/pages/ProvidersPage.tsx`
- Create: `apps/web/src/pages/providers/ProviderList.tsx`
- Create: `apps/web/src/pages/providers/ProviderFormDrawer.tsx`
- Create: `apps/web/src/pages/providers/ModelsTab.tsx`
- Create: `apps/web/src/pages/providers/providers.module.css`
- Modify: `apps/web/src/pages/ProvidersPage.test.tsx`

**Interfaces:**
- `ProviderList` renders provider cards with `Refresh models`, `Edit`, `Delete` icon actions.
- `ProviderFormDrawer` owns create/edit state and calls `useCreateProvider`/`useUpdateProvider`.
- `ModelsTab` uses `DataTable`, `StatusChip`, `Badge`, `TableToolbar`, `FormField`, `Select`, `TextInput`, `NumberInput`.

- [ ] **Step 1: Update tests**

Keep provider create/edit/delete and model label tests. Add assertions for the `PageHeader` title, `Providers`/`Models` tabs, and icon action labels. Run:

```powershell
bun run test -- src/pages/ProvidersPage
```

Expected: FAIL.

- [ ] **Step 2: Extract provider form**

Move `ProvidersTab` form state/handlers into `ProviderFormDrawer`. Use a `Drawer` with `FormField`s for Name, Kind, Base URL, API key (DS `PasswordInput` with its built-in reveal toggle), Models URL, and `FormActions`. Do not change the API payloads.

- [ ] **Step 3: Build provider cards and models table**

`ProviderList` uses `Panel`/cards with name, kind, status chip, and icon actions. `ModelsTab` uses `DataTable` with provider, name, context window, labels, actions. Keep the label editor modal but restyle with DS `Modal`, `FormField`, `Badge`, `IconButton`.

- [ ] **Step 4: Run tests and build**

```powershell
bun run test -- src/pages/ProvidersPage
bun run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src/pages/ProvidersPage.tsx apps/web/src/pages/providers apps/web/src/pages/ProvidersPage.test.tsx
git commit -m "feat(web): restyle providers and models"
```

---

### Task 18: Migrate Admin page

**Files:**
- Modify: `apps/web/src/pages/AdminPage.tsx`
- Create: `apps/web/src/pages/admin/PermissionsTab.tsx`
- Create: `apps/web/src/pages/admin/RolesTab.tsx`
- Create: `apps/web/src/pages/admin/UsersTab.tsx`
- Create: `apps/web/src/pages/admin/admin.module.css`
- Modify: `apps/web/src/pages/AdminPage.test.tsx`

**Interfaces:**
- Keeps all existing queries/mutations and modals.
- Uses `AdminTablePage`, `DataTable`, `FormField`, `Drawer`, `ConfirmDialog`, `IconButton`, `StatusChip`.

- [ ] **Step 1: Update tests**

Keep CRUD tests. Add assertions for the three tabs and page header. Run:

```powershell
bun run test -- src/pages/AdminPage
```

Expected: FAIL.

- [ ] **Step 2: Split tabs into files**

Move `PermissionsTab`, `RolesTab`, `UsersTab` and their modals into separate files. Replace tables with `DataTable`, create forms with `FormField`, and destructive actions with `IconButton` + `ConfirmDialog` where the current behavior already confirms (do not add new UX-4 confirmations yet; preserve current semantics).

- [ ] **Step 3: Run tests and build**

```powershell
bun run test -- src/pages/AdminPage
bun run build
```

Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
git add apps/web/src/pages/AdminPage.tsx apps/web/src/pages/admin apps/web/src/pages/AdminPage.test.tsx
git commit -m "feat(web): restyle admin page"
```

---

### Task 19: Migrate API keys page

**Files:**
- Modify: `apps/web/src/pages/ApiKeysPage.tsx`
- Create: `apps/web/src/pages/api-keys/api-keys.module.css`
- Modify: `apps/web/src/pages/ApiKeysPage.test.tsx`

**Interfaces:**
- Uses `ListPage`, `PageHeader`, `DataTable`, `StatusChip`, `FormField`, `MultiSelect`, `Select`, `Modal`, `CopyButton`.

- [ ] **Step 1: Update tests**

Keep create/revoke tests. Add assertions for `PageHeader` title, `Create key` action, and status chips. Run:

```powershell
bun run test -- src/pages/ApiKeysPage
```

Expected: FAIL.

- [ ] **Step 2: Rewrite the page**

Move the create form into a `Modal` opened by a `Create key` action. Render keys in a `DataTable` with ID (mono), scopes as badges, expiry, status chip, and revoke icon. Use `CopyButton` in the created-key modal. Preserve clipboard behavior (`data-testid="created-key"`).

- [ ] **Step 3: Run tests and build**

```powershell
bun run test -- src/pages/ApiKeysPage
bun run build
```

Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
git add apps/web/src/pages/ApiKeysPage.tsx apps/web/src/pages/ApiKeysPage.test.tsx apps/web/src/pages/api-keys
git commit -m "feat(web): restyle api keys page"
```

---

### Task 20: Migrate Skills page

**Files:**
- Modify: `apps/web/src/pages/SkillsPage.tsx`
- Create: `apps/web/src/pages/skills/skills.module.css`
- Modify: `apps/web/src/pages/SkillsPage.test.tsx` (create if missing)

**Interfaces:**
- Uses `ListPage`, `PageHeader`, `DataTable`, `StatusChip`, `Drawer`, `FormField`, `TextInput`, `Textarea`, `FormActions`.

- [ ] **Step 1: Add/update tests**

Create a test that mocks `useSkills` with one builtin and one user skill; assert the page heading, scope chips, and that only user skills have edit/delete actions. Run:

```powershell
bun run test -- src/pages/SkillsPage
```

Expected: FAIL.

- [ ] **Step 2: Rewrite the page**

Render a `ListPage`; move the create/edit form into a `Drawer` opened by `New skill`/`Edit`; render skills in `DataTable` with scope chips and icon actions. Keep `fetchSkill`/`useSaveSkill`/`useDeleteSkill` behavior.

- [ ] **Step 3: Run tests and build**

```powershell
bun run test -- src/pages/SkillsPage
bun run build
```

Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
git add apps/web/src/pages/SkillsPage.tsx apps/web/src/pages/SkillsPage.test.tsx apps/web/src/pages/skills
git commit -m "feat(web): restyle skills page"
```

---

### Task 21: Chat compatibility layer and no-Bulma guard

**Files:**
- Modify: `apps/web/src/pages/SessionPage.tsx`
- Create: `apps/web/src/design-system/styles/legacy-chat.css`
- Create: `apps/web/src/design-system/styles/no-bulma.test.ts`
- Modify: `apps/web/src/main.tsx` if additional legacy import is needed

**Interfaces:**
- `SessionPage` root gets `className="legacy-chat"`; existing chat markup/styles remain.
- `legacy-chat.css` contains only compatibility overrides needed to host the chat inside the new workspace.
- `no-bulma.test.ts` scans non-chat source files for banned class names.

- [ ] **Step 1: Write the failing no-Bulma guard**

Create `no-bulma.test.ts`:

```ts
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

const root = join(process.cwd(), "src");
const allowed = new Set([
  "pages/SessionPage.tsx",
  "chat/Composer.tsx",
  "chat/MarkdownBlock.tsx",
  "chat/MermaidBlock.tsx",
  "chat/ReasoningBlock.tsx",
  "chat/ToolCallBlock.tsx",
  "chat/AppPanel.tsx",
  "chat/PlanPanel.tsx",
]);
const bannedTokens = new Set([
  "box",
  "title",
  "button",
  "navbar",
  "columns",
  "column",
  "menu-list",
  "notification",
  "is-flex",
  "is-justify-content-space-between",
]);
const classAttribute = /className=(?:"([^"]*)"|\{`([^`]*)`\})/g;

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return files(path);
    return path.endsWith(".tsx") || path.endsWith(".ts") ? [path] : [];
  });
}

function hasBulmaClass(source: string): boolean {
  for (const line of source.split(/\r?\n/)) {
    for (const match of line.matchAll(classAttribute)) {
      const value = match[1] ?? match[2] ?? "";
      if (value.split(/\s+/).some((token) => bannedTokens.has(token))) return true;
    }
  }
  return false;
}

describe("no Bulma classes outside chat", () => {
  it("keeps non-chat components free of Bulma class names", () => {
    const offenders = files(root)
      .filter((path) => !path.includes(".test."))
      .filter((path) => !allowed.has(relative(root, path).replaceAll("\\", "/")))
      .filter((path) => hasBulmaClass(readFileSync(path, "utf8")));
    expect(offenders).toEqual([]);
  });
});
```

Run:

```powershell
bun run test -- src/design-system/styles/no-bulma
```

Expected: FAIL with the current pages.

- [ ] **Step 2: Add the chat compatibility wrapper**

In `SessionPage`, set the root `className="legacy-chat"`. Ensure the page is rendered inside the workspace and does not inherit page-level design-system typography that breaks chat. Add `legacy-chat.css` with scoped layout rules only (no global resets).

- [ ] **Step 3: Remove Bulma classes from migrated pages**

Run the guard and fix every offender by replacing Bulma classes with DS components/classes. Re-run until it passes.

- [ ] **Step 4: Commit**

```powershell
git add apps/web/src/pages/SessionPage.tsx apps/web/src/design-system/styles
git commit -m "feat(web): isolate chat compatibility styles"
```

---

### Task 22: E2E selector updates and visual smoke tests

**Files:**
- Create: `apps/web/e2e/visual-shell.spec.ts`
- Modify: `apps/web/e2e/*.spec.ts` (selector updates)
- Modify: `apps/web/playwright.config.ts` (if snapshot path config needed)

**Interfaces:**
- New spec uses the existing login helper pattern from `api-keys.spec.ts`.
- Visual snapshots stored in `apps/web/e2e/__screenshots__/`.

- [ ] **Step 1: Write the visual smoke spec**

Add the snapshot path to `apps/web/playwright.config.ts`:

```ts
snapshotPathTemplate: "{testDir}/__screenshots__/{testFilePath}/{arg}{ext}",
```

Create `apps/web/e2e/visual-shell.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

const pages = [
  ["login", "/login"],
  ["home", "/"],
  ["agents", "/agents"],
  ["providers", "/providers"],
  ["admin", "/admin"],
  ["api-keys", "/api-keys"],
  ["skills", "/skills"],
] as const;

test("shell renders without horizontal overflow at all breakpoints", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password").fill("admin");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();

  for (const width of [390, 1280, 1920]) {
    await page.setViewportSize({ width, height: 844 });
    for (const [name, path] of pages) {
      if (path === "/login") continue;
      await page.goto(path);
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow).toBeLessThanOrEqual(1);
      await expect(page).toHaveScreenshot(`shell-${name}-${width}.png`, { fullPage: true });
    }
  }
});
```

- [ ] **Step 2: Update existing E2E selectors**

Replace text-based nav selectors with accessible names that survive icons (e.g. `getByRole("link", { name: "Agents" })` remains valid). Update table/action selectors to the new `aria-label`s (`New agent`, `Create key`, `Refresh models`, `Delete`).

Generate the visual baselines once, then run the suite normally:

```powershell
bun run e2e/prepare.ts
bunx playwright test --update-snapshots
bun run e2e
```

Expected: PASS after fixes and baseline generation.

- [ ] **Step 3: Commit**

```powershell
git add apps/web/e2e apps/web/playwright.config.ts
git commit -m "test(web): add shell visual smoke tests"
```

---

### Task 23: Final cleanup, roadmap, and full verification

**Files:**
- Delete: `apps/web/src/theme/ThemeSync.tsx` (replaced by design-system ThemeProvider)
- Modify: `apps/web/src/design-system/styles/legacy-chat.css` (scope cleanup)
- Modify: `docs/ROADMAP.md`
- Possibly modify: `apps/web/package.json` (remove unused deps only if safe; keep `bulma` for chat until UX-2)

**Interfaces:**
- No behavior changes; only dead code removal, docs, and verification.

- [ ] **Step 1: Remove dead shell/theme code**

Delete `ThemeSync.tsx` if no imports remain (AppShell was removed in Task 11). Run:

```powershell
Get-ChildItem apps/web/src -Recurse -Include *.ts,*.tsx | Select-String -Pattern "AppShell|ThemeSync"
```

Expected: no references.

- [ ] **Step 2: Run the full frontend checks**

```powershell
cd apps/web
bun run test
bun run build
bun run build-storybook
bun run e2e
```

Expected: all PASS.

- [ ] **Step 3: Update roadmap**

In `docs/ROADMAP.md`:
- Set `UX-1` status to `DONE`.
- Add a sub-project history row: `30 | UX-1 design system + command shell | specs/2026-11-20-ux-1-design-system-design.md | plans/2026-11-20-ux-1-design-system.md`.
- Update the UI/technical-stack row to note RemixIcons are now used and the design system is in place.
- Update the chat row to note the temporary compatibility layer remains for UX-2.

- [ ] **Step 4: Commit**

```powershell
git add apps/web docs/ROADMAP.md
git commit -m "feat(web): complete UX-1 design system and shell"
```

---

## Plan self-review

- **Spec coverage:** brand/tokens/theme (Tasks 1–2), Storybook (Task 2), icons (Task 3), primitives/forms/data/overlays/navigation/patterns (Tasks 4–10), command shell + project panel + responsive (Tasks 11–13), all non-chat pages (Tasks 14–20), chat compat/no-Bulma guard (Task 21), visual/E2E (Task 22), cleanup/roadmap (Task 23).
- **Placeholder scan:** no TBD/TODO steps; every task has files, interfaces, tests or verification commands, and implementation code or precise extraction instructions.
- **Type consistency:** `ThemeProvider`, `ThemeToggle`, `Icon`, `IconButton`, `DataTable`, `DataColumn`, `ProjectPanel`, `CommandShell`, `PageContainer`, and `PageHeader` are named consistently across tasks. The `Tone` type is defined in `Badge.tsx` and reused by `StatusChip.tsx`.
- **Known implementation notes:** Storybook 10.6.8 is pinned from the compatibility check (React 19/Vite 8 peer support). The `no-bulma` guard uses Windows path normalization; adjust the `replace(root + "\\\\", "")` expression to `path.relative(root, path)` if the test runs on another OS.
