# Python Documentation Standard and Rollout Design

**Date:** 2026-11-24
**Status:** Approved for planning

## Problem

Production Python code in `packages/*/src` has almost no documentation:

- 100 modules, 92 without a module docstring
- 203 classes, 202 without a class docstring
- 262 public functions, 247 without a docstring
- 332 methods, all without a docstring
- 146 private functions, all without a docstring

The code is behaviorally correct but hard to review and maintain. Inline comments are
also absent in places where retry logic, concurrency, transaction boundaries, and
protocol translation are not self-evident.

## Goals

- Give every production source module a purpose docstring.
- Give every public class and public function/method a Google-style docstring
  describing its role, inputs, outputs, and expected failures.
- Document non-obvious fields and constraints on model and schema classes.
- Add inline comments only where intent or algorithm subtleties are not obvious.
- Add Ruff pydocstyle enforcement so the standard does not regress.
- Add a short contributor guide with examples and repo-specific caveats.

## Non-goals

- No behavior, API, or schema changes.
- No documentation of tests, Alembic migrations, or `apps/web/scripts`.
- No custom documentation coverage checker; Ruff is the enforcement mechanism.
- No reStructuredText/Sphinx directives. Google style only.
- No commit unless the user explicitly requests one.

## Scope

In scope: all Python under `packages/*/src`.

Out of scope:

- `packages/*/tests`
- `packages/agentbox-models/alembic`
- `apps/web/scripts/gen-openapi.py`
- Generated artifacts such as `apps/web/openapi.json` and
  `apps/web/src/api/schema.d.ts` (regenerated, not hand-edited)

## Documentation Standard

### Modules

Each module starts with a one-paragraph docstring covering:

- What the module is responsible for.
- The key collaborators or data it owns.
- Relevant side effects: filesystem, database, subprocess, network, concurrency,
  authentication, or protocol translation.

Do not list every symbol. Package `__init__.py` files get a one-line package docstring
even when they only re-export names.

### Classes

Each public class docstring explains:

- Its role in the architecture.
- Its collaborators and lifecycle (created per request, per session, long-lived, etc.).
- Non-obvious invariants or ownership rules.

Use an `Attributes:` section only for fields whose meaning, units, or constraints are
not obvious from the name and type. SQLModel and Pydantic model classes get a concise
table or schema purpose; do not restate every column or field.

### Functions and Methods

Use this order when a section is needed:

1. Imperative one-line summary.
2. Optional longer description for non-obvious behavior.
3. `Args:` for parameters whose meaning, units, or constraints need explanation.
4. `Returns:` or `Yields:`.
5. `Raises:` only for expected domain errors that callers should handle.
6. `Note:` or `Warning:` for side effects, ownership, retries, or transaction
   boundaries.

Omit sections that add no information. A short one-line docstring is acceptable for
simple public functions.

### Exemptions

- Dunder methods: no docstring required. Ruff rule `D105` is disabled.
- `__init__`: no docstring required. Ruff rule `D107` is disabled.
- Protocol stub methods: no docstring required. Use a targeted `# noqa: D102` on the
  stub. The Protocol class itself still needs a class docstring. If a stub's contract
  is non-obvious, prefer a real one-line docstring over the suppression.
- Private one-line helpers: not flagged by Ruff and not required unless the behavior is
  non-obvious.

### Inline Comments

Add comments when a reader would otherwise have to reverse-engineer intent, including:

- Retry, backoff, timeout, or cancellation logic.
- Concurrency, locking, ownership, and session-lifecycle rules.
- Transaction boundaries, flush/commit ordering, and rollback behavior.
- Path validation, sandboxing, permission checks, and other security decisions.
- Database portability workarounds.
- Protocol translation, event mapping, and state-machine transitions.

Do not comment obvious assignments, control flow, or logging calls.

### Vocabulary

Follow the domain vocabulary in `AGENTS.md`:

- Agent: configuration record.
- Session: live instance.
- Subagent: configuration selected for a child session.
- Subagent session: child session.

Avoid "spawn an agent", "run a subagent", and legacy `sub_session` vocabulary.

## Repo-Specific Caveats

### Model-facing tool docstrings

Harness tool functions in `agentbox_harness.tools` are passed to pydantic-ai. Their
docstrings become model-facing tool descriptions. These docstrings must:

- Describe what the tool does and when to use it.
- Use clear, action-oriented language.
- Avoid secrets, internal implementation details, and misleading guarantees.
- Stay concise enough for a tool prompt.

Documentation-only changes here can influence model behavior, so wording needs review.

### OpenAPI-facing route docstrings

FastAPI route handler docstrings become OpenAPI operation descriptions. These
docstrings must be written for API consumers, not only for maintainers. After changing
router docstrings:

1. Run `uv run python apps/web/scripts/gen-openapi.py`.
2. Run `bun run codegen` in `apps/web`.
3. Review the generated diff before accepting it.

## Enforcement

Update root `pyproject.toml`:

```toml
[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "SIM", "N", "D"]
ignore = ["B009", "D105", "D107"]

[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.ruff.lint.per-file-ignores]
"packages/**/tests/**" = ["D"]
"packages/agentbox-models/alembic/**" = ["D"]
"apps/web/scripts/**" = ["D"]
```

Keep `D417` active so any `Args:` section is complete. Use `# noqa: D417` only for
intentionally generic decorator wrappers, and add an adjacent comment explaining why.

If Ruff's Google convention conflicts with a rule we still want, prefer an explicit
`ignore` entry over weakening the whole convention. Do not disable `D417` globally.

Add `docs/contributing/python-documentation.md` with:

- The standard from this design.
- Good and bad docstring examples.
- The model-facing and OpenAPI caveats.
- The checks to run before submitting changes.

Link the guide from `AGENTS.md`.

## Rollout

Document packages in dependency order:

1. `agentbox-providers`
2. `agentbox-harness`
3. `agentbox-models`
4. `agentbox-api`

For each module: read the behavior first, then write docs and only the necessary inline
comments. Avoid speculative descriptions; when behavior is unclear, inspect tests and
call sites before writing.

Add `[tool.ruff.lint.pydocstyle]` early, but add `D` to `select` only in the final step
so untouched packages remain lint-clean. During batch work, run Ruff explicitly with
`--select D` for the package being edited.

## Verification

Per package:

```powershell
uv run ruff check packages/<package> --select D
uv run ruff check --fix packages/<package>
uv run ty check packages
uv run pytest packages/<package> -q
```

Final gate:

```powershell
uv run ruff check --fix packages
uv run ty check packages
uv run pytest packages/agentbox-api -q
uv run pytest packages/agentbox-models -q
uv run pytest packages/agentbox-harness -q
uv run pytest packages/agentbox-providers -q
```

After router documentation:

```powershell
uv run python apps/web/scripts/gen-openapi.py
cd apps/web
bun run codegen
bun run build
bun run test
```

Run `bun run e2e` only if ports 5173, 8000, 9000, and 9999 are free and time permits.

## Risks and Mitigations

- **Model behavior drift:** tool docstrings become tool descriptions. Review them as
  behavioral changes and run harness tests.
- **OpenAPI churn:** route docstrings change generated artifacts. Regenerate and review
  the diff instead of hand-editing.
- **Low-value noise:** enforce the "non-obvious only" rule for inline comments and keep
  simple docstrings to one line.
- **Large diff:** stage by package and verify each package before moving on.
- **Ruff friction:** `D417` can be awkward for wrapped functions. Use rare, justified
  suppressions rather than weakening the rule.
- **False confidence:** documentation must be based on code and tests, not names alone.
  Inspect call sites when behavior is ambiguous.

## Success Criteria

- All 100 source modules have docstrings.
- Every public class and public function/method is documented, except the explicit
  exemptions above.
- Non-obvious logic in touched modules has targeted inline comments.
- `uv run ruff check packages` passes with `D` enabled.
- `uv run ty check packages` passes.
- All four package test suites pass.
- Regenerated OpenAPI artifacts are reviewed and the frontend build/tests pass.
- `docs/contributing/python-documentation.md` exists and `AGENTS.md` links to it.
