# Blinking Wordmark Cursor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the `[AGENTBOX]▮` brand mark a hard terminal-style blinking cursor everywhere it appears.

**Architecture:** Extract a shared `Wordmark` primitive that renders the text plus an `aria-hidden` cursor span. The cursor animation lives once in `primitives.module.css`. The three surfaces and the Storybook tokens story render `<Wordmark />` with their existing per-surface class.

**Tech Stack:** React 19, TypeScript, CSS Modules, Vitest + Testing Library, Storybook, Bun.

## Global Constraints

- Frontend commands run from `apps/web`.
- Use Bun, not npm/pnpm.
- Do not hand-edit generated API artifacts.
- Conventional commit messages, e.g. `feat(web): ...`.
- Cursor stays static (solid) under `prefers-reduced-motion: reduce`.
- The compact `[A]` rail mark (`AppRail.tsx`) stays unchanged.

---

## File Structure

- Create: `apps/web/src/design-system/primitives/Wordmark.tsx` — brand mark component; owns text, accessibility, and cursor.
- Modify: `apps/web/src/design-system/primitives/primitives.module.css` — `.brandCursor` class, `ab-cursor-blink` keyframes, reduced-motion override.
- Modify: `apps/web/src/design-system/primitives/primitives.test.tsx` — test for the new primitive.
- Modify: `apps/web/src/pages/HomePage.tsx` — hero brand uses `Wordmark`.
- Modify: `apps/web/src/design-system/patterns/AuthCard.tsx` — auth brand uses `Wordmark`.
- Modify: `apps/web/src/design-system/navigation/MobileTopBar.tsx` — mobile brand uses `Wordmark`.
- Modify: `apps/web/src/design-system/stories/tokens.stories.tsx` — story uses `Wordmark`.
- Modify: `apps/web/src/design-system/patterns/patterns.test.tsx` — assertion targets the accessible name.

---

### Task 1: Create the Wordmark primitive

**Files:**
- Create: `apps/web/src/design-system/primitives/Wordmark.tsx`
- Modify: `apps/web/src/design-system/primitives/primitives.module.css`
- Test: `apps/web/src/design-system/primitives/primitives.test.tsx`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `export function Wordmark({ className }: { className?: string }): JSX.Element` — renders `role="img"` wrapper named `Agentbox`, text `[AGENTBOX]`, and an `aria-hidden` cursor `▮` styled by `.brandCursor`.

- [ ] **Step 1: Write the failing test**

Add the import near the other primitive imports in
`apps/web/src/design-system/primitives/primitives.test.tsx`:

```tsx
import { Wordmark } from "./Wordmark";
```

Add this test inside the existing `describe("surface primitives", ...)` block:

```tsx
  it("renders the wordmark with a decorative cursor", () => {
    render(<Wordmark />);
    expect(screen.getByRole("img", { name: "Agentbox" })).toBeInTheDocument();
    const cursor = screen.getByText("▮");
    expect(cursor).toHaveAttribute("aria-hidden", "true");
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bun run test -- primitives.test.tsx`
Expected: FAIL because `./Wordmark` cannot be resolved.

- [ ] **Step 3: Create the component**

Create `apps/web/src/design-system/primitives/Wordmark.tsx`:

```tsx
import styles from "./primitives.module.css";

export function Wordmark({ className }: { className?: string }) {
  return (
    <span role="img" aria-label="Agentbox" className={className}>
      [AGENTBOX]<span aria-hidden className={styles.brandCursor}>▮</span>
    </span>
  );
}
```

- [ ] **Step 4: Add the cursor animation**

Append to `apps/web/src/design-system/primitives/primitives.module.css`:

```css
.brandCursor {
  animation: ab-cursor-blink 1s step-end infinite;
}

@keyframes ab-cursor-blink {
  0% {
    opacity: 1;
  }
  50% {
    opacity: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .brandCursor {
    animation: none;
  }
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `bun run test -- primitives.test.tsx`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/design-system/primitives/Wordmark.tsx apps/web/src/design-system/primitives/primitives.module.css apps/web/src/design-system/primitives/primitives.test.tsx
git commit -m "feat(web): add blinking wordmark cursor primitive"
```

---

### Task 2: Adopt Wordmark in every surface and story

**Files:**
- Modify: `apps/web/src/pages/HomePage.tsx:119`
- Modify: `apps/web/src/design-system/patterns/AuthCard.tsx:17`
- Modify: `apps/web/src/design-system/navigation/MobileTopBar.tsx:22`
- Modify: `apps/web/src/design-system/stories/tokens.stories.tsx:22`
- Test: `apps/web/src/design-system/patterns/patterns.test.tsx:15`

**Interfaces:**
- Consumes: `Wordmark({ className?: string })` from Task 1.
- Produces: all three `[AGENTBOX]▮` marks and the tokens story driven by `Wordmark`; no literal `▮` remains in these files.

- [ ] **Step 1: Update the failing auth-card test**

In `apps/web/src/design-system/patterns/patterns.test.tsx`, replace:

```tsx
    expect(screen.getByText("[AGENTBOX]▮")).toBeInTheDocument();
```

with:

```tsx
    expect(screen.getByRole("img", { name: "Agentbox" })).toBeInTheDocument();
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bun run test -- patterns.test.tsx`
Expected: FAIL because `AuthCard` still renders the literal text with no `img` role.

- [ ] **Step 3: Replace the home hero mark**

In `apps/web/src/pages/HomePage.tsx`, add the import after the existing primitives imports:

```tsx
import { Wordmark } from "../design-system/primitives/Wordmark";
```

Replace:

```tsx
        <div className={styles.heroBrand}>[AGENTBOX]▮</div>
```

with:

```tsx
        <Wordmark className={styles.heroBrand} />
```

- [ ] **Step 4: Replace the auth-card mark**

In `apps/web/src/design-system/patterns/AuthCard.tsx`, add the import:

```tsx
import { Wordmark } from "../primitives/Wordmark";
```

Replace:

```tsx
        <div className={styles.authBrand}>[AGENTBOX]▮</div>
```

with:

```tsx
        <Wordmark className={styles.authBrand} />
```

- [ ] **Step 5: Replace the mobile top-bar mark**

In `apps/web/src/design-system/navigation/MobileTopBar.tsx`, add the import:

```tsx
import { Wordmark } from "../primitives/Wordmark";
```

Replace:

```tsx
        <span className={styles.mobileBrand}>[AGENTBOX]▮</span>
```

with:

```tsx
        <Wordmark className={styles.mobileBrand} />
```

- [ ] **Step 6: Update the tokens story**

In `apps/web/src/design-system/stories/tokens.stories.tsx`, add the import:

```tsx
import { Wordmark } from "../primitives/Wordmark";
```

Replace:

```tsx
        <h1 style={{ fontFamily: "var(--ab-font-display)", fontSize: 24 }}>
          [AGENTBOX]▮
        </h1>
```

with:

```tsx
        <h1 style={{ fontFamily: "var(--ab-font-display)", fontSize: 24 }}>
          <Wordmark />
        </h1>
```

- [ ] **Step 7: Run the full test suite**

Run: `bun run test`
Expected: PASS with no references to the literal `[AGENTBOX]▮` failing.

- [ ] **Step 8: Run the build**

Run: `bun run build`
Expected: PASS (`tsc --noEmit` and `vite build` succeed).

- [ ] **Step 9: Commit**

```bash
git add apps/web/src/pages/HomePage.tsx apps/web/src/design-system/patterns/AuthCard.tsx apps/web/src/design-system/navigation/MobileTopBar.tsx apps/web/src/design-system/stories/tokens.stories.tsx apps/web/src/design-system/patterns/patterns.test.tsx
git commit -m "feat(web): use blinking Wordmark across brand surfaces"
```

---

## Self-Review

- **Spec coverage:** Shared `Wordmark` primitive (Task 1), animation + reduced motion (Task 1), three call sites + tokens story (Task 2), test updates (Tasks 1–2). Rail `[A]` explicitly untouched.
- **Placeholders:** None; every step has concrete code or commands.
- **Type consistency:** `Wordmark` takes `{ className?: string }` in both tasks; imports use the correct relative paths per directory.
