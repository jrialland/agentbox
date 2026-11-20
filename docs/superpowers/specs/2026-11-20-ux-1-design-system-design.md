# UX-1 — Design System, Command Shell, and Product Character

- **Date:** 2026-11-20
- **Status:** Draft (design approved; pending spec review)
- **Sub-project:** UX-1 — the visual foundation for Agentbox: design tokens, RemixIcon system, Storybook-documented component library, 3-pane command shell, responsive shell, and migration of all non-chat pages.
- **Source:** [`docs/reviews/2026-11-20-ux-review/report.md`](../../reviews/2026-11-20-ux-review/report.md)
- **Roadmap:** `UX-1` in [`docs/ROADMAP.md`](../../ROADMAP.md)

## 1. Context and scope

The 2026-11-20 UX review found that the app works but reads as a default-library prototype: no brand identity, no iconography (despite `@remixicon/react` being installed), no typography hierarchy, no coherent shell, a Mantine/Bulma style collision, and broken responsive behavior. UX-1 fixes the foundation rather than the individual symptoms.

### 1.1 In scope

- A self-hosted design system under `apps/web/src/design-system/`.
- CSS-variable design tokens + a Mantine theme that consumes them.
- Silkscreen / Inter / JetBrains Mono typography.
- RemixIcon-based icon layer and icon-only actions.
- Dark-first theme with system detection and a visible toggle.
- A 3-pane command-center shell (icon rail, project panel, workspace).
- Top segmented navigation + project sheet on mobile.
- Restyling of all non-chat pages: Login, Home, Agents, Providers/Models, Admin, API keys, Skills.
- Storybook documentation for tokens and components.
- Migration off Bulma for the shell and non-chat pages.

### 1.2 Out of scope

- Chat Markdown/Mermaid/runtime behavior and chat surface restyling (UX-2).
- Contextual help and structured editors such as the A2A card (UX-3).
- Validation, destructive confirmations, API error propagation, 404/session-not-found states (UX-4).
- Backend changes.
- New product features.

### 1.3 Chat exception

The existing chat subtree (`SessionPage`, `Composer`, `MarkdownBlock`, `MermaidBlock`, tool/reasoning blocks) keeps its current markup and styling for UX-1. It is mounted inside the new workspace pane through a **scoped chat compatibility layer**. Bulma is isolated in a low-priority `legacy` CSS cascade layer and loaded only for the chat subtree's benefit; design-system styles live in higher-priority layers and override Bulma on the shell and non-chat pages. No Bulma class names remain outside the chat subtree. The `bulma` import and dependency are removed at the end of UX-2 when the chat surface is rebuilt.

## 2. Goals and success criteria

- The product has a distinct, repeatable visual identity: hacker/operator console with computer-culture pop.
- Every navigation and action has a consistent RemixIcon, accessible name, and tooltip where icon-only.
- Desktop uses a true 3-pane command-center layout; mobile uses top segmented nav and a project sheet.
- All non-chat pages use design-system components and page templates.
- Storybook documents tokens and components with light/dark and viewport variants.
- Existing E2E flows continue to pass; no horizontal overflow at 390px.

## 3. Decisions and rationale

| # | Decision | Rationale |
|---|---|---|
| D1 | **Mantine-first; drop Bulma** from the shell and non-chat pages, isolating it in a low-priority `legacy` cascade layer for chat until UX-2. | The Mantine/Bulma collision is the root of the inconsistent resets and typography. |
| D2 | **Internal design system** at `apps/web/src/design-system/`, not a new package. | The frontend is a standalone Bun app; a second JS workspace would add tooling cost without reuse. Extract later if needed. |
| D3 | **Storybook** as the documentation and review surface. | Component states and tokens are easier to validate in isolation than in the full app. |
| D4 | **Dark-first**, system-aware, with a visible toggle. | The hacker/command-center identity is strongest in dark, while accessibility and preference require light support. |
| D5 | **Silkscreen + Inter + JetBrains Mono**. | Pixel display type for identity; Inter for readable UI; JetBrains Mono for code, IDs, metadata, and terminal affordances. |
| D6 | **Phosphor green + amber + cyan + magenta** palette. | Classic terminal DNA with a pop accent system that supports status differentiation. |
| D7 | **Subtle CRT accents**, not full retro. | Scanlines/glow on hero, login, empty states, and live status only; no texture behind body text. |
| D8 | **3-pane desktop shell**; top segmented nav + project sheet on mobile. | Delivers the command-center identity and fixes the broken responsive layout. |
| D9 | **Temporary chat compatibility layer**. | Keeps UX-1 shippable without partially redesigning chat; UX-2 owns the chat surface. |
| D10 | **Small primitive set with compound components**, not a giant prop-heavy library. | Keeps APIs clear and avoids overengineering. |

## 4. Brand and visual language

### 4.1 Wordmark

`[AGENTBOX]` in Silkscreen, with a blinking block cursor after it:

```
[AGENTBOX]▮
```

The bracket motif is reused for active nav items, panel headers, section labels, and empty states. A compact `[A]` mark may be used in the collapsed mobile/top-bar context.

### 4.2 Color tokens

All body-text pairings must meet WCAG AA. The accent colors are for emphasis/status, not long text.

| Token | Dark | Light | Use |
|---|---|---|---|
| `canvas` | `#0A0D0A` | `#F3F6F0` | App background |
| `surface` | `#111611` | `#FFFFFF` | Panels, cards |
| `surface-raised` | `#182018` | `#E9EEE5` | Hover, raised rows |
| `border` | `#2A352A` | `#C8D2C4` | Default 1px borders |
| `text` | `#DCE7DC` | `#121812` | Primary text |
| `text-muted` | `#8E9C8E` | `#5A6658` | Metadata, hints |
| `phosphor` | `#5CFF9D` | `#087A43` | Primary accent, active state |
| `amber` | `#FFB000` | `#9A5A00` | Warnings, degraded status |
| `cyan` | `#39D7FF` | `#007A99` | Info, links |
| `magenta` | `#FF4FD8` | `#A31C8C` | Agent activity, live pulses |
| `danger` | `#FF5C5C` | `#B42318` | Errors, destructive actions |

Semantic aliases: `success` = `phosphor`, `warning` = `amber`, `info` = `cyan`, `error` = `danger`, `agent` = `magenta`.

### 4.3 Typography

- Display/nav/section labels: **Silkscreen**, uppercase, 12–32px, short strings only.
- Body/UI: **Inter**, 13–16px, line-height 1.5–1.6.
- Code/IDs/timestamps/terminal: **JetBrains Mono**, 12–14px.
- Scale: `12 / 13 / 14 / 16 / 18 / 20 / 24 / 32 / 40`.
- Never use pixel type for long body copy or form labels.

### 4.4 Shape, borders, and motion

- Radius: `0` and `2px` for panels/inputs; `4px` for buttons and overlays; `8px` only for floating menus.
- Borders: 1px default; 2px focus ring in `phosphor` with 2px offset.
- Shadows: hard 2px offset shadows for selected/pop elements; soft blur only for floating overlays.
- Motion: `fast 120ms`, `base 180ms`, `slow 280ms`; standard easing; respect `prefers-reduced-motion`.
- Live status: blinking block cursor and a restrained phosphor pulse; no continuous animation on static content.
- Background: near-black canvas with a faint 8%-opacity 1px grid in the workspace; scanline texture only on hero/login/empty states.

### 4.5 Iconography

- Use RemixIcon line icons through a shared `Icon` wrapper.
- Sizes: 16 / 20 / 24; consistent optical weight.
- Icon-only actions require `aria-label` and a tooltip.
- Primary buttons may pair icon + label; toolbars are icon-first.
- Delete uses a trash icon, never `×`. Add uses `+`/`RiAddLine`. Settings uses a gear. Copy uses a copy icon. Mic uses `RiMicLine` / `RiMicOffLine`.
- No barrel import of the whole icon set; import individual icons so the bundle stays small.

## 5. Design-system architecture

### 5.1 Structure

```
apps/web/src/design-system/
  tokens/          # CSS variables + TS token exports
  theme/           # Mantine theme mapping, ThemeProvider, color-scheme state
  icons/           # Icon, IconButton, curated Remix map
  primitives/      # Button, Link, Badge, StatusChip, Panel, Section, PageHeader,
                   # Toolbar, Divider, Tooltip, Spinner, Skeleton, EmptyState,
                   # CodeBlock, CopyButton, Kbd, Tabs
  forms/           # FormField, TextInput, Textarea, Select, MultiSelect,
                   # NumberInput, Checkbox, Switch, FileDropzone, InlineError,
                   # FormActions
  data/            # DataTable, ListRow, TableToolbar, Pagination
  overlays/        # Modal, ConfirmDialog, Drawer, toast pattern
  navigation/      # AppRail, RailItem, ProjectPanel, ProjectItem, SessionItem,
                   # MobileNav, ThemeToggle, UserMenu, Breadcrumbs
  patterns/        # AuthCard, DashboardCard, ListPage, SettingsPage,
                   # AdminTablePage, EmptyStatePanel
  shell/           # CommandShell, Workspace, PageContainer
  storybook/       # decorators, theme/viewport toolbars, a11y setup
```

### 5.2 Tokens and theming

- CSS variables are the single source of truth.
- `ThemeProvider` sets `data-theme="dark|light"` on `<html>`, resolves `stored preference → system → dark`, and exposes a `useTheme()` hook.
- The Mantine theme consumes the same variables for colors, fonts, headings, radius, focus ring, and default component props.
- Light and dark are both first-class; every component story renders in both.
- Fonts are self-hosted with `@fontsource` packages; `font-display: swap` and preload for the primary UI font.

### 5.3 Component conventions

- Prefer compound components over large prop surfaces.
- Forward refs and native props where applicable.
- All interactive components support hover, focus-visible, disabled, and error states.
- All overlays support Escape, focus trap, and restore focus.
- Tables support responsive stacking or a contained horizontal scroll; the page itself never overflows.
- Components expose stable `data-testid` only where E2E needs it; accessible roles/names remain the primary selector contract.

### 5.4 Storybook

- `@storybook/react-vite` with Docs and accessibility addons, pinned to a version compatible with React 19 + Vite 8.
- Storybook toolbar for theme (light/dark) and viewport (mobile/tablet/desktop).
- A token reference page: palette, typography, spacing, radii, borders, shadows, motion.
- Every component gets default, hover/focus, disabled, error (where relevant), and long-content/empty stories.
- Scripts: `bun run storybook`, `bun run build-storybook`.

### 5.5 Legacy Bulma isolation

- `main.tsx` imports Bulma through a `legacy.css` entry that places it in `@layer legacy`.
- `layers.css` declares `@layer reset, legacy, ds, utilities;` so design-system rules always win.
- The session subtree is wrapped in `.legacy-chat` for scoping and documentation.
- Non-chat pages must not use Bulma classes; a Vitest/grep guard asserts no banned class names outside the session subtree.
- UX-2 deletes the legacy layer and the Bulma dependency.

## 6. Shell and responsive behavior

### 6.1 Desktop

| Pane | Width | Contents |
|---|---|---|
| Icon rail | 56px | Brand mark, primary nav, theme toggle, user menu |
| Project panel | 280px | Projects header, new-project action, project/session tree |
| Workspace | remaining | Breadcrumbs, page header, scrollable content |

- Rail nav: Home, Agents, Providers, Skills, API keys, Admin (permission-gated). Active item uses `aria-current="page"`, a phosphor edge bar, and a filled icon.
- Project panel: project row shows name + session count; actions are single-row icon buttons revealed on hover/focus. Sessions show a compact status dot and delete icon.
- Workspace: top bar with breadcrumbs, Silkscreen title, optional subtitle, and page actions. `PageContainer` defaults to `max-width: 1200px`; tables/dashboards can opt into full-bleed.
- Skip link, 2px focus ring, arrow-key rail navigation, Escape closes overlays.
- Theme toggle in the rail footer; user menu shows username/logout.

### 6.2 Tablet and mobile

- Below 1100px the rail collapses into a horizontally scrollable top segmented nav with icon + label; overflow goes into a “More” segment.
- Below 768px the project panel becomes a slide-over sheet from a “Projects” switcher in the top bar.
- Workspace is full width; mobile top bar includes theme toggle and user menu.
- No page-level horizontal overflow at 390px. Tables stack or scroll within their panel.
- Touch targets are at least 44px on mobile.

### 6.3 Login

Login stays outside the command shell: an `AuthCard` centered on the grid/CRT background, `[AGENTBOX]` mark, terminal-style status line, icon-prefixed fields, and the existing authentication behavior.

## 7. Page templates and migration

| Page | Template |
|---|---|
| Home | Command-center dashboard: brand hero/terminal panel, quick actions, project cards, recent sessions, system status strip |
| Agents | `ListPage` with search/filter toolbar; agent cards or compact rows; create in a `Drawer` with grouped sections |
| Providers / Models | Tabs; provider cards with kind/status/actions; models `DataTable` with label chips |
| Admin | `AdminTablePage`: Permissions/Roles/Users tabs, searchable tables, assignment drawers, confirmations |
| API keys | `ListPage`; create dialog with scope chips and expiry; status chips |
| Skills | `ListPage` with built-in/custom scope chips; Markdown body preview |
| Session | Existing chat subtree mounted inside the workspace; scoped compatibility styles only |

### 7.1 Migration sequence

1. Add fonts, Storybook, tokens, theme provider, and token stories.
2. Build icons and primitives in Storybook-first order.
3. Build forms, data, overlays, navigation, patterns, and shell.
4. Replace `AppShell` with `CommandShell`; preserve routes and permission checks.
5. Migrate Login, Home, Agents, Providers/Models, Admin, API keys, Skills.
6. Add the scoped chat compatibility layer.
7. Remove Bulma classes from shell/non-chat pages and delete dead CSS.
8. Update E2E selectors where markup changed; add visual smoke tests.
9. Update the roadmap (UX-1 status) and run all checks.

## 8. Testing and quality gates

- **Storybook a11y:** no critical axe violations on component stories.
- **Vitest:** token/theme resolution, theme persistence, icon wrapper, form field errors, shell navigation.
- **Playwright E2E:** existing auth, projects/sessions, agents/providers, API keys, skills, and chat entry flows pass.
- **Playwright visual smoke:** Login + management pages at 390/1280/1920 in light/dark; assert no horizontal overflow and correct active nav.
- **Accessibility:** focus-visible rings, keyboard nav, labelled icon buttons, `aria-current`, reduced-motion support.
- **Build:** `bun run test`, `bun run build`, `bun run e2e`, `bun run build-storybook`.
- **Performance:** self-hosted fonts, individual icon imports, no layout shift from font loading.

## 9. Acceptance criteria

- The app matches the `[AGENTBOX]` hacker/command-center identity in dark and light themes.
- RemixIcons are used for navigation and icon actions; no text-only `Edit / + / ×` controls remain.
- The shell is a true 3-pane desktop layout and adapts to top segmented nav + project sheet on mobile.
- All non-chat pages use design-system components; no Bulma classes remain outside the chat compat layer.
- Storybook runs and documents tokens + components.
- Existing E2E flows pass; no horizontal overflow at 390px.
- The chat surface remains on its temporary compatibility layer; UX-2 owns its redesign.

## 10. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Storybook / React 19 / Vite 8 incompatibility | Verify and pin a working version before building stories. |
| Mantine theme overrides become too deep | Prefer thin wrappers over theme hacks; keep component CSS local. |
| Chat compatibility layer leaks styles | Scope it to the session subtree; document its removal in UX-2. |
| E2E selector churn | Preserve accessible roles/names; update tests alongside each page. |
| Scope creep into chat/help/validation | Enforce the explicit out-of-scope list; defer to UX-2/3/4. |

## 11. Open items

- Storybook: pin the latest stable `@storybook/react-vite` version compatible with React 19 + Vite 8 at implementation time and record it in `package.json`.
- The compact `[A]` mobile mark is optional; the full `[AGENTBOX]` wordmark may be used if it fits.
- Playwright visual baselines live in `apps/web/e2e/__screenshots__/` using the standard `toHaveScreenshot` naming convention.

## References

- UX review report — [`docs/reviews/2026-11-20-ux-review/report.md`](../../reviews/2026-11-20-ux-review/report.md)
- Roadmap — [`docs/ROADMAP.md`](../../ROADMAP.md)
- Web scaffold design — `docs/superpowers/specs/2026-11-17-web-scaffold-design.md`
- Chat design — `docs/superpowers/specs/2026-11-17-web-chat-design.md`
