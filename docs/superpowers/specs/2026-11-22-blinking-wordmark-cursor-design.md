# Blinking Wordmark Cursor — Design

## Context

The Agentbox wordmark is rendered as the literal string `[AGENTBOX]▮` in three
application surfaces:

- `apps/web/src/pages/HomePage.tsx` (home hero)
- `apps/web/src/design-system/patterns/AuthCard.tsx`
- `apps/web/src/design-system/navigation/MobileTopBar.tsx`

The design-system spec already describes the mark as `[AGENTBOX]` with a
blinking block cursor
(`docs/superpowers/specs/2026-11-20-ux-1-design-system-design.md:66`), but the
cursor is currently static. The compact `[A]` mark in `AppRail` stays static and
is out of scope.

## Decision

Extract a shared `Wordmark` primitive that owns the mark and its cursor
animation. Reuse it in all three surfaces and in the Storybook tokens story so
there is exactly one implementation of the brand mark.

Rationale: a single component keeps the decorative-cursor markup, animation,
accessibility attributes, and reduced-motion handling in one place and removes
the scattered literal `▮` from JSX.

## Design

### Component

New file `apps/web/src/design-system/primitives/Wordmark.tsx`:

```tsx
import styles from "./primitives.module.css";

export function Wordmark({ className }: { className?: string }) {
  return (
    <span role="img" aria-label="Agentbox" className={className}>
      [AGENTBOX]
      <span aria-hidden className={styles.brandCursor}>
        ▮
      </span>
    </span>
  );
}
```

- The wrapper is a `<span>`; callers pass their existing per-surface class
  (`heroBrand`, `authBrand`, `mobileBrand`) for typography and color. The
  component owns content, semantics, and the cursor.
- `role="img"` + `aria-label="Agentbox"` gives the mark a clean accessible name
  instead of the bracketed literal.
- `aria-hidden` on the cursor keeps the decorative block out of the accessible
  name.

### Animation

Add to `apps/web/src/design-system/primitives/primitives.module.css`:

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

`step-end` produces a hard on/off terminal blink: visible for the first half of
each one-second cycle, hidden for the second half. Disabling the animation under
`prefers-reduced-motion` leaves the cursor at its default `opacity: 1`, so it
stays solid and readable.

### Call sites

- `HomePage.tsx:119` → `<Wordmark className={styles.heroBrand} />`
- `AuthCard.tsx:17` → `<Wordmark className={styles.authBrand} />`
- `MobileTopBar.tsx:22` → `<Wordmark className={styles.mobileBrand} />`
- `stories/tokens.stories.tsx:22` → render `<Wordmark />` inside the display-font
  heading.

Existing per-surface CSS classes remain unchanged; only the literal `▮` and
wrapper element move into `Wordmark`.

### Tests

- Update `patterns.test.tsx` so the auth-card brand assertion targets the
  `Agentbox` accessible name (`getByLabelText("Agentbox")`) rather than the
  exact split text.
- Add a `Wordmark` case to `primitives.test.tsx` asserting the accessible name
  and that the `▮` cursor is present and `aria-hidden`.

## Out of scope

- Animating the compact `[A]` rail mark.
- Any glow, color, or typography change to the wordmark.
- Changes to the existing design-system spec or roadmap.

## Verification

From `apps/web`:

```powershell
bun run test
bun run build
```
