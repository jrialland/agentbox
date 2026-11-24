# Python Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add accurate Google-style documentation to all production Python under `packages/*/src` and enforce it with Ruff.

**Architecture:** Document one package at a time in dependency order (`providers` -> `harness` -> `models` -> `api`). Use `ruff check --select D` as the failing/passing verification loop for every task, then run the package tests, type checks, and finally regenerate OpenAPI artifacts for router docstrings. Ruff `D` enforcement is enabled only in the final task so untouched packages stay lint-clean during the rollout.

**Tech Stack:** Python 3.11, uv, Ruff (pydocstyle/Google), ty, pytest, FastAPI, SQLModel, pydantic-ai, Bun/Vite/React.

## Global Constraints

- Scope is only `packages/*/src`. Do not document tests, Alembic migrations, or `apps/web/scripts`.
- Do not change runtime behavior, signatures, schemas, imports, or control flow.
- Use Google-style docstrings. Line length is 100.
- Every source module needs a module docstring. Every public class and public function/method needs a docstring, except the explicit exemptions below.
- Document non-obvious model/schema fields with `Attributes:` or a short inline comment. Do not restate self-describing fields.
- Inline comments only for non-obvious intent or algorithm subtleties: retries, timeouts, cancellation, concurrency, ownership, transaction boundaries, path/security checks, database portability workarounds, and protocol/event translation.
- Exemptions: dunders (`D105` ignored), `__init__` (`D107` ignored), Protocol stub methods (`# noqa: D102` on the stub), and private one-line helpers whose name and signature are sufficient.
- Private helpers longer than one line still get a docstring when the behavior is non-obvious. Ruff does not flag private helpers, so apply judgement.
- Protocol classes still require a class docstring. Prefer a real one-line method docstring over `# noqa: D102` when the contract is non-obvious.
- If a docstring includes an `Args:` section, document every parameter (`D417`). Otherwise omit the section. Use `# noqa: D417` only for intentionally generic decorator wrappers, with an adjacent reason comment.
- Follow the Agent/Session/Subagent vocabulary in `AGENTS.md`. Do not introduce `sub_session` or `delegate_*` wording.
- Harness tool docstrings are model-facing tool descriptions consumed by pydantic-ai. Keep them accurate, concise, action-oriented, and free of internals or secrets.
- FastAPI route docstrings are OpenAPI operation descriptions. Write them for API consumers and regenerate artifacts after router changes.
- Never hand-edit `apps/web/openapi.json` or `apps/web/src/api/schema.d.ts`; regenerate them.
- Do not commit, stage, amend, or push anything. The user has not requested commits.
- Run commands from the repo root unless a step explicitly changes directory.
- Per-task rule: run `uv run ruff check <targets> --select D` first; it must fail with missing-docstring rules. After documenting, rerun and require a clean result.

### Standard examples

Module docstring:

```python
"""Resolve stored provider configurations into pydantic-ai models.

The module maps Agentbox provider kinds to pydantic-ai model classes, resolves
credentials through the API-key helper, and applies an optional context-window
profile. Test-only provider kinds return deterministic fixture models used by
the API and end-to-end suites.
"""
```

Public function with non-obvious inputs and failure:

```python
def resolve_model(
    provider: Provider, model_name: str, context_window: int | None = None
) -> Model:
    """Build a pydantic-ai model for a stored provider configuration.

    Args:
        provider: Provider row containing kind, base URL, and API-key source.
        model_name: Provider-specific model identifier.
        context_window: Optional context-window override for the model profile.

    Returns:
        A configured pydantic-ai model instance.

    Raises:
        ValueError: If the provider kind is not supported.
    """
```

Class docstring with non-obvious attributes:

```python
class Job:
    """A running or completed terminal command owned by one session.

    Attributes:
        output: Captured bytes, capped by the job manager's output limit.
        drain_task: Background reader task responsible for draining the process;
            it must be awaited or cancelled before the job is considered closed.
    """
```

Inline comments:

```python
# The first attempt fails intentionally so retry tests can exercise recovery.
# This state is process-local because the fixture provider is test-only.
attempts = _flaky_attempts.get(model_name, 0) + 1
```

### Task 1: Documentation guide and pydocstyle convention

**Files:**
- Create: `docs/contributing/python-documentation.md`
- Modify: `pyproject.toml`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: the approved standard in `docs/superpowers/specs/2026-11-24-python-documentation-design.md`.
- Produces: a written guide and Ruff configuration that later tasks rely on.

- [ ] **Step 1: Create the contributor guide**

Create `docs/contributing/python-documentation.md` with this content:

````markdown
# Python Documentation

Production Python under `packages/*/src` uses Google-style docstrings.

## Required documentation

- Every module starts with a purpose docstring. Mention relevant side effects:
  filesystem, database, subprocess, network, concurrency, authentication, or
  protocol translation.
- Every public class explains its role, collaborators, lifecycle, and any
  non-obvious invariants. Use `Attributes:` only for non-obvious fields.
- Every public function and method gets a docstring with an imperative summary.
  Add `Args:`, `Returns:`/`Yields:`, `Raises:`, and `Note:`/`Warning:` only when
  they add information.
- Inline comments explain non-obvious intent: retries, timeouts, cancellation,
  locking, ownership, transaction boundaries, path/security checks, database
  portability workarounds, and protocol/state translation. Do not narrate obvious
  code.

## Exemptions

- Dunder methods and `__init__` do not require docstrings.
- Protocol stub methods use `# noqa: D102`; the Protocol class itself still needs
  a class docstring. Prefer a one-line docstring when the contract is non-obvious.
- Private one-line helpers do not require docstrings when the name and signature
  fully describe the behavior.

## Google style example

```python
def resolve_api_key(provider: Provider) -> str | None:
    """Return the configured API key for a provider.

    Prefers the key stored on the provider row, then falls back to the
    ``{PROVIDER_NAME}_API_KEY`` environment variable.

    Args:
        provider: Provider row whose credentials should be resolved.

    Returns:
        The API key, or ``None`` when neither source is configured.
    """
```

## Model-facing tool docstrings

Harness tool functions become pydantic-ai tool descriptions. Their first line
should tell the model what the tool does and when to use it. Keep the wording
accurate and concise; never include secrets or internal implementation details.

## OpenAPI route docstrings

FastAPI route docstrings become operation descriptions. Write them for API
consumers. After changing router docstrings, regenerate the API artifacts:

```powershell
uv run python apps/web/scripts/gen-openapi.py
cd apps/web
bun run codegen
```

## Vocabulary

Follow `AGENTS.md`: an Agent is a configuration, a Session is a live instance,
and a Subagent is the configuration selected for a child subagent session.

## Checks

```powershell
uv run ruff check packages --select D
uv run ruff check --fix packages
uv run ty check packages
```
````

- [ ] **Step 2: Add the Google pydocstyle convention and exemptions to Ruff**

In `pyproject.toml`, update the lint settings to exactly:

```toml
[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "SIM", "N"]
ignore = ["B009", "D105", "D107"]

[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.ruff.lint.per-file-ignores]
"packages/**/tests/**" = ["D"]
"packages/agentbox-models/alembic/**" = ["D"]
"apps/web/scripts/**" = ["D"]
```

Do not add `"D"` to `select` yet. Later tasks run Ruff with `--select D`
explicitly, and the final task enables it globally.

- [ ] **Step 3: Link the guide from AGENTS.md**

Add this section to `AGENTS.md` under `## Repo conventions`:

```markdown
## Python documentation

- Production Python under `packages/*/src` uses Google-style docstrings for
  modules, public classes, and public functions/methods.
- See `docs/contributing/python-documentation.md`.
- Enforce with `uv run ruff check packages --select D`.
```

- [ ] **Step 4: Confirm the check is wired**

Run:

```powershell
uv run ruff check packages/agentbox-providers/src --select D
```

Expected: FAIL with `D100`, `D101`, `D102`, and/or `D103` missing-docstring
diagnostics. This is the baseline for the next task.

### Task 2: Document the providers package

**Files:**
- Modify: `packages/agentbox-providers/src/agentbox_providers/__init__.py`
- Modify: `packages/agentbox-providers/src/agentbox_providers/api_keys.py`
- Modify: `packages/agentbox-providers/src/agentbox_providers/models.py`
- Modify: `packages/agentbox-providers/src/agentbox_providers/resolver.py`

**Interfaces:**
- Consumes: the standard and Ruff configuration from Task 1.
- Produces: fully documented providers package; no signature changes.

- [ ] **Step 1: Run the failing documentation check**

```powershell
uv run ruff check packages/agentbox-providers/src --select D
```

Expected: FAIL with missing module/class/function docstrings.

- [ ] **Step 2: Document the package module and API-key helper**

In `__init__.py`, add a one-line package docstring.

In `api_keys.py`, add a module docstring and document `resolve_api_key`. Use this
exact docstring shape:

```python
def resolve_api_key(provider: Provider) -> str | None:
    """Return the configured API key for a provider.

    The provider row takes precedence; otherwise the key is read from the
    ``{PROVIDER_NAME}_API_KEY`` environment variable.

    Args:
        provider: Provider row whose credentials should be resolved.

    Returns:
        The API key, or ``None`` when neither source is configured.
    """
```

- [ ] **Step 3: Document model listing**

In `models.py`, add a module docstring plus docstrings for `_get_json` and
`list_models`. `list_models` must document the `ValueError` for a missing
`models_url` and the HTTP failure propagated by `raise_for_status`.

- [ ] **Step 4: Document model resolution and fixture providers**

In `resolver.py`, add a module docstring and document `resolve_model`. The module
docstring must explain that `test`, `test_tool`, `test_*` kinds are deterministic
fixtures, and that API keys are resolved through `resolve_api_key`.

Add inline comments for:

- The module-level `_flaky_attempts` state and why it exists.
- Why the `test_*` branches return fixture models rather than production models.
- The unknown-kind `ValueError` at the end of the dispatch chain.

- [ ] **Step 5: Verify documentation, lint, types, and tests**

```powershell
uv run ruff check packages/agentbox-providers/src --select D
uv run ruff check --fix packages/agentbox-providers
uv run ty check packages
uv run pytest packages/agentbox-providers -q
```

Expected: Ruff D clean, ty clean, and all provider tests pass.

### Task 3: Document harness core types and session state

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/__init__.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/spec.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/messages.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/events.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/errors.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/logging.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/middleware.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/usage.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/session.py`

**Interfaces:**
- Consumes: the standard and Ruff configuration from Task 1.
- Produces: documented core harness types, events, errors, and session log behavior.

- [ ] **Step 1: Run the failing documentation check**

```powershell
uv run ruff check packages/agentbox-harness/src/agentbox_harness/__init__.py packages/agentbox-harness/src/agentbox_harness/spec.py packages/agentbox-harness/src/agentbox_harness/messages.py packages/agentbox-harness/src/agentbox_harness/events.py packages/agentbox-harness/src/agentbox_harness/errors.py packages/agentbox-harness/src/agentbox_harness/logging.py packages/agentbox-harness/src/agentbox_harness/middleware.py packages/agentbox-harness/src/agentbox_harness/usage.py packages/agentbox-harness/src/agentbox_harness/session.py --select D
```

Expected: FAIL with missing docstrings.

- [ ] **Step 2: Document the domain types and protocols**

Document `AgentSpec`, modes, bindings, and related dataclasses in `spec.py` with
role-level class docstrings. Document Protocol classes in `middleware.py` and
`session.py`, and put `# noqa: D102` on each stub method.

Document the message/event/error/logging/usage types in their modules. Keep model
class docstrings to one or two lines when fields are self-describing.

- [ ] **Step 3: Document the session message log**

In `session.py`, document `Turn`, `MessageLogStore`, `InMemoryMessageLogStore`,
and `Session`. `Session.history` must explain the parent-linked branch walk:

```python
async def history(self) -> list[Turn]:
    """Return the active conversation branch from root to head.

    The store is a parent-linked log, so the head is walked backwards until a
    summary turn or a root turn is reached, then the chain is reversed into
    chronological order.
    """
```

Add inline comments for the head update in `append`, the summary re-parenting in
`insert_summary`, and the two stop conditions in `history`.

- [ ] **Step 4: Verify documentation, lint, types, and harness tests**

```powershell
uv run ruff check packages/agentbox-harness/src/agentbox_harness/__init__.py packages/agentbox-harness/src/agentbox_harness/spec.py packages/agentbox-harness/src/agentbox_harness/messages.py packages/agentbox-harness/src/agentbox_harness/events.py packages/agentbox-harness/src/agentbox_harness/errors.py packages/agentbox-harness/src/agentbox_harness/logging.py packages/agentbox-harness/src/agentbox_harness/middleware.py packages/agentbox-harness/src/agentbox_harness/usage.py packages/agentbox-harness/src/agentbox_harness/session.py --select D
uv run ruff check --fix packages/agentbox-harness
uv run ty check packages
uv run pytest packages/agentbox-harness -q
```

Expected: Ruff D clean, type check clean, and harness tests pass.

### Task 4: Document harness orchestration, run loop, and compaction

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/agent_factory.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/compaction.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/context_editing.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/harness.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/run.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/subagent_sessions.py`

**Interfaces:**
- Consumes: the documented core types from Task 3.
- Produces: documented orchestration and lifecycle behavior; no signature changes.

- [ ] **Step 1: Run the failing documentation check**

```powershell
uv run ruff check packages/agentbox-harness/src/agentbox_harness/agent_factory.py packages/agentbox-harness/src/agentbox_harness/compaction.py packages/agentbox-harness/src/agentbox_harness/context_editing.py packages/agentbox-harness/src/agentbox_harness/harness.py packages/agentbox-harness/src/agentbox_harness/run.py packages/agentbox-harness/src/agentbox_harness/subagent_sessions.py --select D
```

Expected: FAIL with missing docstrings.

- [ ] **Step 2: Document orchestration and lifecycle**

Document `build_agent`/agent factory functions, the harness session lifecycle,
run manager behavior, cancellation, retries, compaction, context editing, and
subagent-session orchestration. Each public entry point needs a role summary and
its expected failures.

Add inline comments for:

- Retry/backoff and cancellation boundaries in the run loop.
- Compaction cutoff selection and summary insertion.
- Context-editing budget calculation and what is retained.
- Subagent-session creation, waiting, completion, and cancellation ownership.
- Tool-hook wrapping order in `agent_factory` if present.

- [ ] **Step 3: Verify documentation, lint, types, and tests**

```powershell
uv run ruff check packages/agentbox-harness/src/agentbox_harness/agent_factory.py packages/agentbox-harness/src/agentbox_harness/compaction.py packages/agentbox-harness/src/agentbox_harness/context_editing.py packages/agentbox-harness/src/agentbox_harness/harness.py packages/agentbox-harness/src/agentbox_harness/run.py packages/agentbox-harness/src/agentbox_harness/subagent_sessions.py --select D
uv run ruff check --fix packages/agentbox-harness
uv run ty check packages
uv run pytest packages/agentbox-harness -q
```

Expected: Ruff D clean, type check clean, and harness tests pass.

### Task 5: Document harness tools (model-facing docstrings)

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/tools/__init__.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/tools/filesystem.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/tools/grep.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/tools/mcp.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/tools/mcp_session.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/tools/paths.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/tools/registry.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/tools/terminal.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/tools/web.py`

**Interfaces:**
- Consumes: the standard from Task 1 and harness core docs from Task 3.
- Produces: model-facing tool descriptions and documented tool internals.

- [ ] **Step 1: Run the failing documentation check**

```powershell
uv run ruff check packages/agentbox-harness/src/agentbox_harness/tools --select D
```

Expected: FAIL with missing docstrings.

- [ ] **Step 2: Document tool entry points for the model**

Document the public tool functions that pydantic-ai exposes. Their docstrings
must tell the model what the tool does, when to use it, and what the result
contains. Keep failure behavior explicit when tools return error text instead of
raising.

Use this shape for `run_command`:

```python
async def run_command(
    command: str,
    cwd: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    background: bool = False,
) -> str:
    """Run a shell command in the project workspace.

    Args:
        command: Shell command to execute.
        cwd: Working directory relative to the project root.
        timeout: Maximum foreground runtime in seconds, capped internally.
        background: Start the command as a job and return immediately.

    Returns:
        Human-readable status and captured output. Failures are returned as text
        prefixed with ``Command failed:`` rather than raised.
    """
```

Document internal classes and helpers in `filesystem.py`, `grep.py`, `mcp.py`,
`mcp_session.py`, `paths.py`, `registry.py`, and `web.py` as well. The registry
hook wrapper needs a comment explaining why arguments are rebound from the
signature.

- [ ] **Step 3: Add comments for security and platform subtleties**

Add inline comments for:

- Path resolution and sandbox/extra-root checks in `paths.py`.
- Windows PowerShell wrapping and exit-code propagation in `terminal.py`.
- Job output caps, truncation, and background drain behavior.
- URL validation, localhost-only HTTP, redirect handling, and llms.txt fallback
  in `web.py`.
- MCP stdio/HTTP transport selection and session toolset lifecycle.

- [ ] **Step 4: Verify documentation, lint, types, and tool tests**

```powershell
uv run ruff check packages/agentbox-harness/src/agentbox_harness/tools --select D
uv run ruff check --fix packages/agentbox-harness
uv run ty check packages
uv run pytest packages/agentbox-harness -q
```

Expected: Ruff D clean, type check clean, and harness tests pass.

### Task 6: Document harness LSP integration

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/lsp/__init__.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/lsp/client.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/lsp/detect.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/lsp/diagnostics.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/lsp/hooks.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/lsp/manager.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/lsp/quiescence.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/lsp/stacks.py`

**Interfaces:**
- Consumes: documented harness core types from Task 3.
- Produces: documented LSP process, diagnostics, quiescence, and hook behavior.

- [ ] **Step 1: Run the failing documentation check**

```powershell
uv run ruff check packages/agentbox-harness/src/agentbox_harness/lsp --select D
```

Expected: FAIL with missing docstrings.

- [ ] **Step 2: Document LSP lifecycle and diagnostics**

Document the LSP client transport, initialize/shutdown handshake, process
spawning, stack detection, diagnostics collection, quiescence detection, hook
entry points, and manager lifecycle. Note which operations are async, which spawn
subprocesses, and which have timeouts.

- [ ] **Step 3: Add comments for protocol and timing subtleties**

Add inline comments for:

- JSON-RPC framing and request/notification correlation.
- Initialization capabilities and shutdown ordering.
- Quiescence windows and debounce decisions.
- Diagnostic request sequencing and stale-result handling.
- Subprocess cleanup and error propagation.

- [ ] **Step 4: Verify documentation, lint, types, and LSP-aware tests**

```powershell
uv run ruff check packages/agentbox-harness/src/agentbox_harness/lsp --select D
uv run ruff check --fix packages/agentbox-harness
uv run ty check packages
uv run pytest packages/agentbox-harness -q
```

Expected: Ruff D clean, type check clean, and harness tests pass (real LSP tests
may self-skip when servers are absent).

### Task 7: Document models tables, config, and database setup

**Files:**
- Modify: `packages/agentbox-models/src/agentbox_models/__init__.py`
- Modify: `packages/agentbox-models/src/agentbox_models/config.py`
- Modify: `packages/agentbox-models/src/agentbox_models/db.py`
- Modify: `packages/agentbox-models/src/agentbox_models/tables/__init__.py`
- Modify: `packages/agentbox-models/src/agentbox_models/tables/auth.py`
- Modify: `packages/agentbox-models/src/agentbox_models/tables/core.py`

**Interfaces:**
- Consumes: the standard from Task 1.
- Produces: documented tables and database configuration used by repositories and the API.

- [ ] **Step 1: Run the failing documentation check**

```powershell
uv run ruff check packages/agentbox-models/src --select D
```

Expected: FAIL with missing docstrings.

- [ ] **Step 2: Document tables and schema roles**

Give each SQLModel table class a one-line purpose docstring. Add `Attributes:`
only for non-obvious columns such as nullable status, cascade/restrict rules, or
UTC timestamps. Do not document every self-describing column.

Add inline comments for:

- `utcnow` and why timezone-aware UTC is used.
- Foreign-key `ondelete` choices (`RESTRICT`, `CASCADE`) and indexes.
- Any column whose database type or length is portability-sensitive.
- The table module re-exports in `tables/__init__.py`.

- [ ] **Step 3: Document configuration and database lifecycle**

Document `config.py` and `db.py`: settings precedence, TOML/env resolution,
engine creation, session/transaction lifecycle, and `create_all` seeding behavior.
Note which helpers are safe for concurrent use.

- [ ] **Step 4: Verify documentation, lint, types, and model tests**

```powershell
uv run ruff check packages/agentbox-models/src --select D
uv run ruff check --fix packages/agentbox-models
uv run ty check packages
uv run pytest packages/agentbox-models -q
```

Expected: Ruff D clean, type check clean, and model tests pass (container tests
may skip when Docker is unavailable).

### Task 8: Document models repositories

**Files:**
- Modify: `packages/agentbox-models/src/agentbox_models/repos/__init__.py`
- Modify: `packages/agentbox-models/src/agentbox_models/repos/agents.py`
- Modify: `packages/agentbox-models/src/agentbox_models/repos/api_key_scopes.py`
- Modify: `packages/agentbox-models/src/agentbox_models/repos/crud.py`
- Modify: `packages/agentbox-models/src/agentbox_models/repos/message_log.py`
- Modify: `packages/agentbox-models/src/agentbox_models/repos/model_labels.py`
- Modify: `packages/agentbox-models/src/agentbox_models/repos/project_roots.py`

**Interfaces:**
- Consumes: documented tables and DB helpers from Task 7.
- Produces: documented repository APIs used by the API package.

- [ ] **Step 1: Run the failing documentation check**

```powershell
uv run ruff check packages/agentbox-models/src/agentbox_models/repos --select D
```

Expected: FAIL with missing docstrings.

- [ ] **Step 2: Document repository responsibilities**

Each repository module gets a purpose docstring. Document public query/mutation
methods with their filters, ordering, return shape, and expected domain errors.
Mention whether the caller owns the session/transaction.

Add inline comments for:

- Commit/flush ordering and transaction boundaries.
- Message-log branch semantics and retention/cutoff behavior.
- Scoped API-key filtering and label ordering.
- Project-root resolution and duplicate handling.

- [ ] **Step 3: Verify documentation, lint, types, and tests**

```powershell
uv run ruff check packages/agentbox-models/src/agentbox_models/repos --select D
uv run ruff check --fix packages/agentbox-models
uv run ty check packages
uv run pytest packages/agentbox-models -q
```

Expected: Ruff D clean, type check clean, and model tests pass.

### Task 9: Document API app, config, auth, security, and validation

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/__init__.py`
- Modify: `packages/agentbox-api/src/agentbox_api/app.py`
- Modify: `packages/agentbox-api/src/agentbox_api/config.py`
- Modify: `packages/agentbox-api/src/agentbox_api/deps.py`
- Modify: `packages/agentbox-api/src/agentbox_api/logging.py`
- Modify: `packages/agentbox-api/src/agentbox_api/auth_backend.py`
- Modify: `packages/agentbox-api/src/agentbox_api/security.py`
- Modify: `packages/agentbox-api/src/agentbox_api/validation.py`
- Modify: `packages/agentbox-api/src/agentbox_api/templating.py`

**Interfaces:**
- Consumes: the standard from Task 1 and documented model/DB helpers.
- Produces: documented application construction, settings, auth, and validation behavior.

- [ ] **Step 1: Run the failing documentation check**

```powershell
uv run ruff check packages/agentbox-api/src/agentbox_api/__init__.py packages/agentbox-api/src/agentbox_api/app.py packages/agentbox-api/src/agentbox_api/config.py packages/agentbox-api/src/agentbox_api/deps.py packages/agentbox-api/src/agentbox_api/logging.py packages/agentbox-api/src/agentbox_api/auth_backend.py packages/agentbox-api/src/agentbox_api/security.py packages/agentbox-api/src/agentbox_api/validation.py packages/agentbox-api/src/agentbox_api/templating.py --select D
```

Expected: FAIL with missing docstrings.

- [ ] **Step 2: Document app construction and settings**

Document `create_app`, settings resolution, logging setup, dependency providers,
RBAC checks, JWT/bcrypt helpers, validation helpers, and template rendering.
Clearly state security-sensitive preconditions and expected failures.

Add inline comments for:

- Settings precedence and environment overrides.
- JWT secret/length and token lifetime decisions.
- Password hashing/verification boundaries.
- Permission checks and tenant/ownership assumptions.
- Template autoescaping or trust boundaries.

- [ ] **Step 3: Verify documentation, lint, types, and tests**

```powershell
uv run ruff check packages/agentbox-api/src/agentbox_api/__init__.py packages/agentbox-api/src/agentbox_api/app.py packages/agentbox-api/src/agentbox_api/config.py packages/agentbox-api/src/agentbox_api/deps.py packages/agentbox-api/src/agentbox_api/logging.py packages/agentbox-api/src/agentbox_api/auth_backend.py packages/agentbox-api/src/agentbox_api/security.py packages/agentbox-api/src/agentbox_api/validation.py packages/agentbox-api/src/agentbox_api/templating.py --select D
uv run ruff check --fix packages/agentbox-api
uv run ty check packages
uv run pytest packages/agentbox-api -q
```

Expected: Ruff D clean, type check clean, and API tests pass.

### Task 10: Document API runtime, sessions, streaming, media, and skills

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/runtime.py`
- Modify: `packages/agentbox-api/src/agentbox_api/runs.py`
- Modify: `packages/agentbox-api/src/agentbox_api/streaming.py`
- Modify: `packages/agentbox-api/src/agentbox_api/activity.py`
- Modify: `packages/agentbox-api/src/agentbox_api/subagent_sessions.py`
- Modify: `packages/agentbox-api/src/agentbox_api/lsp_runtime.py`
- Modify: `packages/agentbox-api/src/agentbox_api/mcp_relay.py`
- Modify: `packages/agentbox-api/src/agentbox_api/sandbox.py`
- Modify: `packages/agentbox-api/src/agentbox_api/media.py`
- Modify: `packages/agentbox-api/src/agentbox_api/avatars.py`
- Modify: `packages/agentbox-api/src/agentbox_api/skills.py`

**Interfaces:**
- Consumes: documented app/auth/DB helpers and harness runtime.
- Produces: documented run orchestration, event streaming, media, and skill behavior.

- [ ] **Step 1: Run the failing documentation check**

```powershell
uv run ruff check packages/agentbox-api/src/agentbox_api/runtime.py packages/agentbox-api/src/agentbox_api/runs.py packages/agentbox-api/src/agentbox_api/streaming.py packages/agentbox-api/src/agentbox_api/activity.py packages/agentbox-api/src/agentbox_api/subagent_sessions.py packages/agentbox-api/src/agentbox_api/lsp_runtime.py packages/agentbox-api/src/agentbox_api/mcp_relay.py packages/agentbox-api/src/agentbox_api/sandbox.py packages/agentbox-api/src/agentbox_api/media.py packages/agentbox-api/src/agentbox_api/avatars.py packages/agentbox-api/src/agentbox_api/skills.py --select D
```

Expected: FAIL with missing docstrings.

- [ ] **Step 2: Document runtime and streaming behavior**

Document run registration/cancellation, AG-UI/event translation, activity
mapping, subagent-session lifecycle, LSP runtime wiring, MCP relay behavior,
sandbox policy, media persistence, avatar generation, and skill discovery.

Add inline comments for:

- Run ownership and cancellation propagation.
- Event ordering and terminal-event emission.
- Subagent-session completion/wait/cancel boundaries.
- Sandbox path checks and allowed roots.
- Media storage layout, checksums, and cleanup expectations.
- Skill/plugin discovery precedence.

- [ ] **Step 3: Verify documentation, lint, types, and tests**

```powershell
uv run ruff check packages/agentbox-api/src/agentbox_api/runtime.py packages/agentbox-api/src/agentbox_api/runs.py packages/agentbox-api/src/agentbox_api/streaming.py packages/agentbox-api/src/agentbox_api/activity.py packages/agentbox-api/src/agentbox_api/subagent_sessions.py packages/agentbox-api/src/agentbox_api/lsp_runtime.py packages/agentbox-api/src/agentbox_api/mcp_relay.py packages/agentbox-api/src/agentbox_api/sandbox.py packages/agentbox-api/src/agentbox_api/media.py packages/agentbox-api/src/agentbox_api/avatars.py packages/agentbox-api/src/agentbox_api/skills.py --select D
uv run ruff check --fix packages/agentbox-api
uv run ty check packages
uv run pytest packages/agentbox-api -q
```

Expected: Ruff D clean, type check clean, and API tests pass.

### Task 11: Document API plugins, dev tooling, plan tools, and project instructions

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/dev_prepare.py`
- Modify: `packages/agentbox-api/src/agentbox_api/dev_seed.py`
- Modify: `packages/agentbox-api/src/agentbox_api/dev_server.py`
- Modify: `packages/agentbox-api/src/agentbox_api/plan_tools.py`
- Modify: `packages/agentbox-api/src/agentbox_api/plugin_catalog.py`
- Modify: `packages/agentbox-api/src/agentbox_api/plugin_hook_config.py`
- Modify: `packages/agentbox-api/src/agentbox_api/plugin_hooks.py`
- Modify: `packages/agentbox-api/src/agentbox_api/plugin_service.py`
- Modify: `packages/agentbox-api/src/agentbox_api/plugin_validation.py`
- Modify: `packages/agentbox-api/src/agentbox_api/project_instructions.py`

**Interfaces:**
- Consumes: documented app/auth/DB helpers.
- Produces: documented plugin lifecycle, hook execution, dev seeding, plan, and instruction behavior.

- [ ] **Step 1: Run the failing documentation check**

```powershell
uv run ruff check packages/agentbox-api/src/agentbox_api/dev_prepare.py packages/agentbox-api/src/agentbox_api/dev_seed.py packages/agentbox-api/src/agentbox_api/dev_server.py packages/agentbox-api/src/agentbox_api/plan_tools.py packages/agentbox-api/src/agentbox_api/plugin_catalog.py packages/agentbox-api/src/agentbox_api/plugin_hook_config.py packages/agentbox-api/src/agentbox_api/plugin_hooks.py packages/agentbox-api/src/agentbox_api/plugin_service.py packages/agentbox-api/src/agentbox_api/plugin_validation.py packages/agentbox-api/src/agentbox_api/project_instructions.py --select D
```

Expected: FAIL with missing docstrings.

- [ ] **Step 2: Document plugin and dev behavior**

Document plugin catalog loading, validation rules, hook configuration, hook
execution/order/failure isolation, plugin lifecycle/state, dev preparation and
seeding, plan-tool state transitions, and project instruction discovery.

Add inline comments for:

- Hook execution order and error isolation.
- Plugin validation/security assumptions.
- Dev seeding idempotency.
- Plan-state transitions and persistence.
- Instruction file discovery precedence and path safety.

- [ ] **Step 3: Verify documentation, lint, types, and tests**

```powershell
uv run ruff check packages/agentbox-api/src/agentbox_api/dev_prepare.py packages/agentbox-api/src/agentbox_api/dev_seed.py packages/agentbox-api/src/agentbox_api/dev_server.py packages/agentbox-api/src/agentbox_api/plan_tools.py packages/agentbox-api/src/agentbox_api/plugin_catalog.py packages/agentbox-api/src/agentbox_api/plugin_hook_config.py packages/agentbox-api/src/agentbox_api/plugin_hooks.py packages/agentbox-api/src/agentbox_api/plugin_service.py packages/agentbox-api/src/agentbox_api/plugin_validation.py packages/agentbox-api/src/agentbox_api/project_instructions.py --select D
uv run ruff check --fix packages/agentbox-api
uv run ty check packages
uv run pytest packages/agentbox-api -q
```

Expected: Ruff D clean, type check clean, and API tests pass.

### Task 12: Document API protocol adapters

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/a2a_executor.py`
- Modify: `packages/agentbox-api/src/agentbox_api/a2a_server.py`
- Modify: `packages/agentbox-api/src/agentbox_api/acp_client_tools.py`
- Modify: `packages/agentbox-api/src/agentbox_api/acp_server.py`
- Modify: `packages/agentbox-api/src/agentbox_api/acp_terminals.py`

**Interfaces:**
- Consumes: documented runtime, sessions, auth, and database helpers.
- Produces: documented A2A/ACP protocol behavior; no protocol changes.

- [ ] **Step 1: Run the failing documentation check**

```powershell
uv run ruff check packages/agentbox-api/src/agentbox_api/a2a_executor.py packages/agentbox-api/src/agentbox_api/a2a_server.py packages/agentbox-api/src/agentbox_api/acp_client_tools.py packages/agentbox-api/src/agentbox_api/acp_server.py packages/agentbox-api/src/agentbox_api/acp_terminals.py --select D
```

Expected: FAIL with missing docstrings.

- [ ] **Step 2: Document protocol adapters**

Document A2A card construction/dispatch/execution, ACP session lifecycle, client
tool proxying, terminal handling, and protocol error translation. State which
methods are called by external protocol peers rather than internal code.

Add inline comments for:

- A2A task/message translation and ownership.
- ACP capability negotiation and session updates.
- Client tool path/argument validation.
- Terminal output/exit-code translation.
- Cancellation and cleanup ordering.

- [ ] **Step 3: Verify documentation, lint, types, and tests**

```powershell
uv run ruff check packages/agentbox-api/src/agentbox_api/a2a_executor.py packages/agentbox-api/src/agentbox_api/a2a_server.py packages/agentbox-api/src/agentbox_api/acp_client_tools.py packages/agentbox-api/src/agentbox_api/acp_server.py packages/agentbox-api/src/agentbox_api/acp_terminals.py --select D
uv run ruff check --fix packages/agentbox-api
uv run ty check packages
uv run pytest packages/agentbox-api -q
```

Expected: Ruff D clean, type check clean, and API tests pass.

### Task 13: Document API routers and regenerate OpenAPI artifacts

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/routers/__init__.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/agents.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/api_keys.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/auth.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/labels.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/llms.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/models.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/permissions.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/plugins.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/projects.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/prompts.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/providers.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/roles.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/sessions.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/skills.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/users.py`
- Regenerate: `apps/web/openapi.json`
- Regenerate: `apps/web/src/api/schema.d.ts`

**Interfaces:**
- Consumes: documented API helpers from Tasks 9-12.
- Produces: user-facing OpenAPI operation descriptions and regenerated client schema.

- [ ] **Step 1: Run the failing documentation check**

```powershell
uv run ruff check packages/agentbox-api/src/agentbox_api/routers --select D
```

Expected: FAIL with missing docstrings.

- [ ] **Step 2: Document route handlers for API consumers**

Write route docstrings as user-facing operation descriptions. Include:

- The resource and action.
- Permission or authentication expectations.
- Notable validation rules or expected `HTTPException` statuses.
- Any streaming or long-running behavior.

Example shape:

```python
@router.get("", response_model=list[AgentRead])
async def list_agents(...):
    """List agent configurations visible to the caller.

    Returns:
        Agent configurations ordered by name. Requires the ``agents:read``
        permission.
    """
```

Do not describe internal implementation. Document request/response models with
concise class docstrings and non-obvious field notes.

Add inline comments for:

- Permission dependencies and ownership checks.
- Validation branches that produce specific HTTP errors.
- Session run/stream orchestration and cleanup.
- Any workaround for generated schema or compatibility behavior.

- [ ] **Step 3: Verify documentation, lint, types, and tests**

```powershell
uv run ruff check packages/agentbox-api/src/agentbox_api/routers --select D
uv run ruff check --fix packages/agentbox-api
uv run ty check packages
uv run pytest packages/agentbox-api -q
```

Expected: Ruff D clean, type check clean, and API tests pass.

- [ ] **Step 4: Regenerate OpenAPI artifacts and review the diff**

```powershell
uv run python apps/web/scripts/gen-openapi.py
bun --cwd apps/web run codegen
git diff --stat apps/web/openapi.json apps/web/src/api/schema.d.ts
```

Expected: generated files change to include the new operation descriptions. Review
the diff and confirm the descriptions are accurate and consumer-appropriate. Do
not hand-edit these files.

### Task 14: Enable Ruff D enforcement and run the final gate

**Files:**
- Modify: `pyproject.toml`
- Verify: `apps/web/openapi.json`
- Verify: `apps/web/src/api/schema.d.ts`

**Interfaces:**
- Consumes: all documentation tasks and the guide from Task 1.
- Produces: repo-wide documentation enforcement and final verification.

- [ ] **Step 1: Enable Ruff D globally**

In `pyproject.toml`, add `"D"` to `[tool.ruff.lint].select`:

```toml
select = ["E", "F", "W", "I", "UP", "B", "SIM", "N", "D"]
```

The `ignore` and per-file-ignore entries from Task 1 remain in place.

- [ ] **Step 2: Run the full Python checks**

```powershell
uv run ruff check --fix packages
uv run ty check packages
```

Expected: both commands pass with no findings.

- [ ] **Step 3: Run every package test suite separately**

```powershell
uv run pytest packages/agentbox-api -q
uv run pytest packages/agentbox-models -q
uv run pytest packages/agentbox-harness -q
uv run pytest packages/agentbox-providers -q
```

Expected: all tests pass. Do not combine package directories in one pytest run.

- [ ] **Step 4: Confirm generated artifacts are stable**

```powershell
$before = Get-FileHash apps/web/openapi.json, apps/web/src/api/schema.d.ts
uv run python apps/web/scripts/gen-openapi.py
bun --cwd apps/web run codegen
$after = Get-FileHash apps/web/openapi.json, apps/web/src/api/schema.d.ts
Compare-Object $before $after
```

Expected: `Compare-Object` prints nothing, proving the generator is stable. If it
prints differences, inspect them and confirm they are caused by intended
docstrings only.

- [ ] **Step 5: Run frontend verification**

```powershell
bun --cwd apps/web run build
bun --cwd apps/web run test
```

Expected: TypeScript/Vite build and Vitest pass.

- [ ] **Step 6: Optional end-to-end verification**

Only if ports 5173, 8000, 9000, and 9999 are free:

```powershell
bun --cwd apps/web run e2e
```

Expected: end-to-end suite passes. Skip this step if ports are occupied or time is
limited, and report that it was skipped.

- [ ] **Step 7: Final scope check**

Run:

```powershell
git status --short
```

Confirm that only intended source files, the guide, `AGENTS.md`, `pyproject.toml`,
and regenerated API artifacts changed. Do not commit or stage anything.

## Self-Review

- Spec coverage: module docs, class docs, function/method docs, inline comments,
  model-facing tool caveats, OpenAPI caveats, enforcement, guide, package rollout,
  and verification all map to Tasks 1-14.
- Placeholder scan: every task names exact files and commands; the only optional
  step is the explicitly labelled e2e check.
- Type consistency: no signatures or types change; documented examples use the
  existing names `resolve_api_key`, `resolve_model`, `list_models`, `Turn`,
  `Session.history`, and `run_command`.
- Commit policy: no commit steps, matching the user's instruction.
