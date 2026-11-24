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
uv run ruff check packages
uv run ruff check --fix packages
uv run ty check packages
```
