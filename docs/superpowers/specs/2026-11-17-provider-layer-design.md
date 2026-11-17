# LLM Provider Layer — Design Specification

- **Date:** 2026-11-17
- **Status:** Draft (brainstormed, pending implementation plan)
- **Sub-project:** LLM provider layer — resolve persisted providers/models into live pydantic-ai `Model` instances, and fetch model lists from provider endpoints.

## 1. Context and Scope

This specification covers the provider layer, which bridges the persisted `providers`/`models` tables (in `agentbox-models`) and the pydantic-ai runtime. It turns a stored provider configuration into a runnable model.

### 1.1 What this sub-project encompasses

- **Provider resolution** — map a `Provider` record (kind, base URL, API key, models URL) plus a model name into a live pydantic-ai `Model` instance.
- **Model-list fetching** — retrieve the available model names from a provider's endpoint (fetch-only; no persistence).
- **A small harness change** — broaden the `model` parameter from `str` to `str | Model` so resolved instances can be injected.

### 1.2 Boundaries (out of scope)

- Persistence of providers/models (already in `agentbox-models`; the `models` table + `ProviderRepository` exist).
- Model-list *persistence* — `list_models` fetches and returns names; upserting into the `models` table is left to the backend/UI layer.
- The backend HTTP layer and the frontend.
- RBAC / authentication.

### 1.3 Dependencies

- `agentbox-models` — for the `Provider`/`Model` tables and repositories.
- `pydantic-ai` — for `Model` classes and providers.
- `httpx` — for model-list fetching (transitive dep of pydantic-ai).

## 2. Decisions and Rationale

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Local models via **Ollama** (`OllamaModel`), not a custom `transformers` adapter. | Pydantic AI natively supports Ollama; `transformers` has no native local chat/generation integration and would require a custom `Model` subclass. Ollama serves GGUF models (gemma, lfm) downloaded from HuggingFace, key-free. |
| D2 | New **`agentbox-providers`** package. | Keeps persistence (`agentbox-models`) separate from live-model resolution; resolution depends on pydantic-ai and the tables. |
| D3 | **`list_models` fetch-only** (no persistence). | Separation of concerns; the backend/UI decides whether to upsert fetched names. |
| D4 | Broaden harness `model` type to **`str \| Model`**. | pydantic-ai's `Agent(model=...)` accepts both; generic/base-URL providers require a `Model` instance, not just a string. |
| D5 | Built-in providers use **environment-variable API keys** (e.g. `MOONSHOT_API_KEY`); generic providers use the stored key (env fallback). | Matches the initial spec ("variable d'environnement Moonshot API Key"). |

## 3. Package: `agentbox-providers`

- New workspace member `packages/agentbox-providers`.
- Depends on `agentbox-models` (workspace) and `pydantic-ai`.
- Exposes the resolver and the model-list fetcher.

## 4. Provider Resolution

`resolve_model(provider: Provider, model_name: str) -> Model`

Maps `Provider.kind` to a pydantic-ai `Model`:

| `kind` | Construction |
|---|---|
| `openai_legacy` | `OpenAIChatModel(model_name, OpenAIProvider(api_key=...))` |
| `openai_responses` | `OpenAIResponsesModel(model_name, ...)` |
| `anthropic` | `AnthropicModel(model_name, ...)` |
| `generic` (OpenAI-compatible) | `OpenAIChatModel(model_name, OpenAICompatibleProvider(base_url, api_key))` |
| `moonshot` | `OpenAIChatModel(model_name, OpenAICompatibleProvider(base_url=MOONSHOT_BASE_URL, api_key=env))` |
| `deepseek` | `OpenAIChatModel(model_name, OpenAICompatibleProvider(base_url=DEEPSEEK_BASE_URL, api_key=env))` |
| `ollama` | `OllamaModel(model_name, OllamaProvider(base_url))` |

`resolve_model` returns a `Model` instance. Exact pydantic-ai class names and constructor signatures are verified against the installed library during implementation (as with the harness).

## 5. API-key Resolution

- `_resolve_api_key(provider) -> str | None`:
  - If `provider.api_key` is set, use it.
  - Else, look up `<NAME>_API_KEY` in the environment (upper-snake-case of `provider.name`, e.g. `MOONSHOT_API_KEY`, `DEEPSEEK_API_KEY`).
- Ollama uses no key.

## 6. Model-list Fetching

- `list_models(provider: Provider) -> list[str]` (async):
  - GET `provider.models_url` (e.g. `https://api.moonshot.cn/v1/models`, `https://api.deepseek.com/v1/models`) via `httpx`.
  - Sends `Authorization: Bearer <api_key>` when a key is present.
  - Parses the OpenAI-style `{"object": "list", "data": [{"id": ...}, ...]}` response and returns the `id` values.
- Fetch-only; the caller (backend/UI) persists results into the `models` table.

## 7. Harness Integration

- Change `build_agent`, `Harness`, and `RunManager` to accept `model: str | Model` (pydantic-ai `Model`).
- The harness already passes `model` straight to `Agent(model=...)`, which accepts both types.
- Tests keep passing `"test"` / `TestModel()`.

## 8. Testing

- **Resolver unit tests** — each `kind` maps to the correct pydantic-ai model class (verified via `isinstance`), using `TestModel`/`FunctionModel` where a live model isn't needed.
- **`list_models` unit tests** — mock the HTTP response (no network/API key); assert model names are extracted correctly.
- **Real local model test** — a pytest fixture runs a trivial prompt against **Ollama `gemma4:e2b`**; it `skip`s cleanly when Ollama is unavailable or the model isn't pulled, so CI stays green without a local model.
- API-key resolution is unit-tested with injected env values.

## 9. Open Items / Future Work

- Model-list *persistence* (upsert into `models`) — backend/UI concern.
- A custom `transformers` adapter, if ever needed, slots in as an additional `kind` mapping (D1 chose Ollama as the local path).
- Other providers (Mistral, Groq, Bedrock, etc.) can be added as additional `kind` values.

## References

- Pydantic AI Models & Providers — `https://ai.pydantic.dev/models/`; Ollama — `https://ai.pydantic.dev/models/ollama/`; custom `Model` interface — `https://ai.pydantic.dev/api/models/base/`.
- Foundation design — `docs/superpowers/specs/2026-11-17-foundation-design.md`.
- Initial platform spec — `docs/initial_spec.md`.
