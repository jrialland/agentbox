# LLM Provider Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `agentbox-providers` — resolve persisted `Provider`/`Model` records into live pydantic-ai `Model` instances, fetch model lists from provider endpoints, and change the harness to use a single `Model` type.

**Architecture:** A new workspace package `agentbox-providers` exposes `resolve_model(provider, model_name) -> Model` (a `kind` → pydantic-ai class mapping) and `list_models(provider) -> list[str]` (async `httpx` fetch, fetch-only). The harness's `model` parameters change from `str` to `Model`, and the dead `RunManager.model` field is removed.

**Tech Stack:** Python 3.11+, `pydantic-ai`, `agentbox-models` (workspace), `httpx`, `pytest` + `pytest-asyncio`, Ollama for a real local-model test.

## Global Constraints

- Python `>=3.11`.
- The harness uses a **single `Model` type** (pydantic-ai `Model`), never `str`.
- `list_models` is **fetch-only** (no persistence into the `models` table).
- Local models use **Ollama** (`OllamaModel`/`OllamaProvider`).
- No real network calls in unit tests — mock HTTP; the real-local-model test skips when Ollama is unavailable.
- Follow TDD: write the failing test, run it, implement, run it, commit.

**Reference docs (verify exact class names/import paths while implementing):**
- Pydantic AI Models & Providers — `https://ai.pydantic.dev/models/`; Ollama — `https://ai.pydantic.dev/models/ollama/`.

---

### Task 1: Harness — single `Model` type, drop dead `RunManager.model`

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/agent_factory.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/harness.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/run.py`
- Modify: `packages/agentbox-harness/tests/test_agent_factory.py`, `test_run_manager.py`, `test_cancel.py`, `test_run_outcome.py`, `test_harness_e2e.py`, `test_resume_e2e.py`, `test_run_turn.py`

**Interfaces:**
- Produces: `build_agent(spec, mode, registry, model: Model) -> Agent`; `Harness(registry, model: Model, store_factory, sub_agents=None)`; `RunManager()` (no args).

- [ ] **Step 1: Update the implementation**

`agent_factory.py` — import `Model`, type `model`:

```python
from pydantic_ai import Agent, Model

def build_agent(spec, mode, registry, model: Model) -> Agent:
    # ... unchanged body; model is passed straight to Agent(model=model, ...)
```

`run.py` — remove the `__init__` (drop `self.model`):

```python
class RunManager:
    def start(self, agent, prompt, run_id, bus, model_override=None, cancellation_token=None, message_history=None) -> Run:
        ...
```

`harness.py` — `model: Model`, `RunManager()`:

```python
from pydantic_ai import Model

class Harness:
    def __init__(self, registry, model: Model, store_factory, sub_agents=None):
        self.registry = registry
        self.model = model
        self.store_factory = store_factory
        self.sub_agents = sub_agents or {}
        self.run_manager = RunManager()
```

- [ ] **Step 2: Update tests** — `"test"` → `TestModel()`, `RunManager(model=...)` → `RunManager()`:

- `test_agent_factory.py`: `build_agent(spec, Mode(...), reg, "test")` → `build_agent(spec, Mode(...), reg, TestModel())` (both call sites).
- `test_run_manager.py`: `RunManager(model="test")` → `RunManager()`.
- `test_cancel.py`: `RunManager(model="test")` → `RunManager()`.
- `test_run_outcome.py`: `RunManager(model="test")` → `RunManager()` (both call sites).
- `test_harness_e2e.py`: `Harness(registry=reg, model="test", ...)` → `Harness(registry=reg, model=TestModel(), ...)`.
- `test_resume_e2e.py`: same change.
- `test_run_turn.py`: same change.

(Leave pydantic-ai's own `Agent("test", ...)` strings unchanged — they are pydantic-ai's API, not the harness's `model` type.)

- [ ] **Step 3: Run the harness suite**

Run (from `packages/agentbox-harness`): `uv run pytest -q`
Expected: 46 passed.

- [ ] **Step 4: Commit**

```bash
git add packages/agentbox-harness
git commit -m "refactor(harness): single Model type, drop dead RunManager.model"
```

---

### Task 2: `agentbox-providers` scaffold

**Files:**
- Create: `packages/agentbox-providers/pyproject.toml`
- Create: `packages/agentbox-providers/src/agentbox_providers/__init__.py`
- Test: `packages/agentbox-providers/tests/test_scaffold.py`

**Interfaces:**
- Produces: importable `agentbox_providers` package; a workspace member.

- [ ] **Step 1: Write the package files**

```toml
# packages/agentbox-providers/pyproject.toml
[project]
name = "agentbox-providers"
version = "0.1.0"
description = "LLM provider resolution for Agentbox"
requires-python = ">=3.11"
dependencies = [
    "pydantic-ai>=2.0",
    "httpx>=0.27",
    "agentbox-models",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/agentbox_providers"]

[tool.uv.sources]
agentbox-models = { workspace = true }

[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
```

```python
# packages/agentbox-providers/src/agentbox_providers/__init__.py
__version__ = "0.1.0"
```

```python
# packages/agentbox-providers/tests/test_scaffold.py
import agentbox_providers


def test_package_imports():
    assert hasattr(agentbox_providers, "__version__")
```

- [ ] **Step 2: Sync and run the test**

Run (from repo root): `uv sync`
Then (from `packages/agentbox-providers`): `uv run pytest -q`
Expected: 1 passed.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml packages/agentbox-providers uv.lock
git commit -m "feat(providers): add agentbox-providers package scaffold"
```

---

### Task 3: `resolve_model` (kind → pydantic-ai Model)

**Files:**
- Create: `packages/agentbox-providers/src/agentbox_providers/resolver.py`
- Test: `packages/agentbox-providers/tests/test_resolver.py`

**Interfaces:**
- Consumes: `Provider` table (from `agentbox_models.tables.core`).
- Produces: `resolve_model(provider: Provider, model_name: str) -> Model`; raises `ValueError` for an unknown `kind`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_resolver.py
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.models.anthropic import AnthropicModel

from agentbox_models.tables.core import Provider
from agentbox_providers.resolver import resolve_model


def test_resolve_ollama():
    m = resolve_model(Provider(id="p", name="ollama", kind="ollama", base_url="http://localhost:11434"), "gemma4:e2b")
    assert isinstance(m, OllamaModel)


def test_resolve_openai_legacy():
    m = resolve_model(Provider(id="p", name="openai", kind="openai_legacy"), "gpt-4o")
    assert isinstance(m, OpenAIChatModel)


def test_resolve_openai_responses():
    m = resolve_model(Provider(id="p", name="openai", kind="openai_responses"), "gpt-4o")
    assert isinstance(m, OpenAIResponsesModel)


def test_resolve_anthropic():
    m = resolve_model(Provider(id="p", name="anthropic", kind="anthropic"), "claude-x")
    assert isinstance(m, AnthropicModel)


def test_resolve_generic():
    m = resolve_model(Provider(id="p", name="gen", kind="generic", base_url="https://x/v1"), "m")
    assert isinstance(m, OpenAIChatModel)


def test_resolve_unknown_kind_raises():
    import pytest
    with pytest.raises(ValueError):
        resolve_model(Provider(id="p", name="x", kind="bogus"), "m")
```

- [ ] **Step 2: Run to fail**

Run (from `packages/agentbox-providers`): `uv run pytest tests/test_resolver.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement** (verify exact class/import names against the installed pydantic-ai first)

```python
# resolver.py
from pydantic_ai import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.ollama import OllamaModel, OllamaProvider
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider, OpenAICompatibleProvider

from agentbox_models.tables.core import Provider

from agentbox_providers.api_keys import resolve_api_key


def resolve_model(provider: Provider, model_name: str) -> Model:
    kind = provider.kind
    if kind == "openai_legacy":
        return OpenAIChatModel(model_name, provider=OpenAIProvider(api_key=resolve_api_key(provider)))
    if kind == "openai_responses":
        return OpenAIResponsesModel(model_name, provider=OpenAIProvider(api_key=resolve_api_key(provider)))
    if kind == "anthropic":
        return AnthropicModel(model_name, api_key=resolve_api_key(provider))
    if kind in ("generic", "moonshot", "deepseek"):
        return OpenAIChatModel(
            model_name,
            provider=OpenAICompatibleProvider(base_url=provider.base_url, api_key=resolve_api_key(provider)),
        )
    if kind == "ollama":
        return OllamaModel(model_name, provider=OllamaProvider(base_url=provider.base_url))
    raise ValueError(f"Unknown provider kind: {kind}")
```

- [ ] **Step 4: Run to pass**

Run (from `packages/agentbox-providers`): `uv run pytest tests/test_resolver.py -q`
Expected: PASS (6 passed). If a class/import name differs, adjust against the docs and re-run.

- [ ] **Step 5: Commit**

```bash
git add packages/agentbox-providers/src/agentbox_providers/resolver.py packages/agentbox-providers/tests/test_resolver.py
git commit -m "feat(providers): add resolve_model (kind -> Model)"
```

---

### Task 4: API-key resolution

**Files:**
- Create: `packages/agentbox-providers/src/agentbox_providers/api_keys.py`
- Test: `packages/agentbox-providers/tests/test_api_keys.py`

**Interfaces:**
- Produces: `resolve_api_key(provider: Provider) -> str | None` — stored key first, else `<NAME>_API_KEY` env var.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_keys.py
import os
from agentbox_models.tables.core import Provider
from agentbox_providers.api_keys import resolve_api_key


def test_stored_key_wins():
    p = Provider(id="p", name="moonshot", kind="generic", api_key="stored")
    assert resolve_api_key(p) == "stored"


def test_env_var_fallback(monkeypatch):
    monkeypatch.setenv("MOONSHOT_API_KEY", "envkey")
    p = Provider(id="p", name="moonshot", kind="generic")
    assert resolve_api_key(p) == "envkey"


def test_none_when_no_key(monkeypatch):
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    p = Provider(id="p", name="moonshot", kind="generic")
    assert resolve_api_key(p) is None
```

- [ ] **Step 2: Run to fail**

Run: `uv run pytest tests/test_api_keys.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# api_keys.py
import os

from agentbox_models.tables.core import Provider


def resolve_api_key(provider: Provider) -> str | None:
    if provider.api_key:
        return provider.api_key
    env_name = f"{provider.name.upper()}_API_KEY"
    return os.environ.get(env_name)
```

- [ ] **Step 4: Run to pass**

Run: `uv run pytest tests/test_api_keys.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add packages/agentbox-providers/src/agentbox_providers/api_keys.py packages/agentbox-providers/tests/test_api_keys.py
git commit -m "feat(providers): add api-key resolution"
```

---

### Task 5: `list_models` (model-list fetching)

**Files:**
- Create: `packages/agentbox-providers/src/agentbox_providers/models.py`
- Test: `packages/agentbox-providers/tests/test_list_models.py`

**Interfaces:**
- Produces: `async list_models(provider: Provider) -> list[str]` — GET `provider.models_url`, parse `data[].id`.

- [ ] **Step 1: Write the failing test** (mock HTTP)

```python
# tests/test_list_models.py
import httpx
from agentbox_models.tables.core import Provider
from agentbox_providers.models import list_models


async def test_list_models_parses_ids(monkeypatch):
    captured = {}

    async def fake_get(url, headers=None):
        captured["url"] = url
        return httpx.Response(
            200,
            json={"object": "list", "data": [{"id": "moonshot-v1-8k"}, {"id": "moonshot-v1-32k"}]},
        )

    monkeypatch.setattr("agentbox_providers.models._get_json", fake_get)
    p = Provider(id="p", name="moonshot", kind="generic", models_url="https://api.moonshot.cn/v1/models")
    assert await list_models(p) == ["moonshot-v1-8k", "moonshot-v1-32k"]
    assert captured["url"] == "https://api.moonshot.cn/v1/models"
```

- [ ] **Step 2: Run to fail**

Run: `uv run pytest tests/test_list_models.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# models.py
import httpx

from agentbox_models.tables.core import Provider

from agentbox_providers.api_keys import resolve_api_key


async def _get_json(url: str, headers: dict | None = None):
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=headers)
        r.raise_for_status()
        return r.json()


async def list_models(provider: Provider) -> list[str]:
    headers = {}
    key = resolve_api_key(provider)
    if key:
        headers["Authorization"] = f"Bearer {key}"
    data = await _get_json(provider.models_url, headers=headers)
    return [item["id"] for item in data.get("data", [])]
```

- [ ] **Step 4: Run to pass**

Run: `uv run pytest tests/test_list_models.py -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add packages/agentbox-providers/src/agentbox_providers/models.py packages/agentbox-providers/tests/test_list_models.py
git commit -m "feat(providers): add list_models (model-list fetching)"
```

---

### Task 6: Real local-model test via Ollama

**Files:**
- Create: `packages/agentbox-providers/tests/test_ollama_real.py`

**Interfaces:**
- Consumes: `resolve_model` (Task 3); `pydantic_ai.Agent`.
- Produces: a test that runs a trivial prompt against Ollama `gemma4:e2b` and skips when Ollama is unavailable.

- [ ] **Step 1: Write the test**

```python
# tests/test_ollama_real.py
import pytest
from pydantic_ai import Agent

from agentbox_models.tables.core import Provider
from agentbox_providers.resolver import resolve_model


@pytest.fixture
def ollama_model():
    try:
        model = resolve_model(
            Provider(id="p", name="ollama", kind="ollama", base_url="http://localhost:11434"),
            "gemma4:e2b",
        )
    except Exception:
        pytest.skip("Ollama not configured")
    return model


async def test_ollama_real_model_responds(ollama_model):
    agent = Agent(ollama_model)
    result = await agent.run("Reply with the single word: pong")
    assert result.output is not None
    assert "pong" in result.output.lower()
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/test_ollama_real.py -q`
Expected: PASS if Ollama is running with `gemma4:e2b`; SKIPPED otherwise. Verify it does not fail hard without Ollama.

- [ ] **Step 3: Commit**

```bash
git add packages/agentbox-providers/tests/test_ollama_real.py
git commit -m "test(providers): real local-model test via Ollama"
```

---

## Self-Review Notes

- **Spec coverage:** harness single-`Model` change + dead-field removal (Task 1), package scaffold (Task 2), `resolve_model` (Task 3), API-key resolution (Task 4), `list_models` (Task 5), real Ollama test (Task 6). All §1.1 items covered.
- **Type consistency:** `Model` (single type), `Provider`, `resolve_model`, `resolve_api_key`, `list_models` used consistently.
- **Verification note:** exact pydantic-ai import paths (`OpenAICompatibleProvider`, `OllamaProvider`, `AnthropicModel`) and constructor signatures must be checked against the installed library in Tasks 3 before finalizing; adjust names if they differ (as done for the harness/foundation).
