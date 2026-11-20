# Automatic Compaction - Design

Date: 2026-11-20
Status: Approved (design), spec awaiting review.

## Goal

Keep long sessions usable by summarizing older conversation turns when context
usage approaches the model's window, and by recovering from provider
context-window errors. Compaction must be branch-aware, visible to the user,
and separated from chat/ACP/A2A transport code.

## Research summary

- `AgentRunResult.response.usage` exposes the **last request's**
  `input_tokens`, `output_tokens`, and `total_tokens`; this is the context size
  after the run. `RunUsage` is cumulative across requests, so it is not the
  context size.
- Providers that omit usage increment `RequestUsage.unmeasured_requests`;
  `RequestUsage.has_values()` distinguishes measured usage.
- `model.profile["context_window"]` is populated by pydantic-ai for many known
  models (e.g. 128k for GPT-4o, 200k for Claude Sonnet 4.5), and is `None` for
  custom/local models. All model constructors accept an explicit
  `profile={"context_window": N}` override.
- `Model.count_tokens()` is not implemented for OpenAI or Anthropic and is not
  portable, so pre-request token counting is not used.
- pydantic-ai raises `ModelContextWindowExceededError` for OpenAI-compatible,
  Anthropic, Google, Bedrock, Cohere, Mistral, and xAI overflows. Ollama uses
  the OpenAI-compatible model path. This is the reactive fallback.
- LiteLLM's registry is ~5 MB / 7,078 entries; it is not vendored. pydantic-ai
  profiles plus a per-model override cover the practical cases.

## Decisions

- **Context source**: pydantic-ai's model profile when available, plus an
  optional per-model `context_window` override.
- **Trigger**: usage-driven proactive compaction when the window is known;
  reactive compaction and one retry on `ModelContextWindowExceededError`.
- **Summary storage**: a branch-aware `summary` turn in the existing turn
  chain, not SessionRow columns or a separate summary table.
- **Summarizer**: the agent's own model, with a fixed structured prompt and no
  tools.
- **Architecture**: a harness-level `RunMiddleware` pipeline around
  `Harness.run`, not compaction logic woven into chat/ACP/A2A and not a
  pydantic-ai capability. pydantic-ai capabilities remain for request-level
  behavior; typed `deps` are preferred over contextvars if a future
  capability needs application state.
- **UI**: a collapsible “Earlier conversation summarized” notice in chat.

## Data model

### `Model.context_window`

`agentbox_models/tables/core.py`:

```python
class Model(SQLModel, table=True):
    ...
    context_window: int | None = None
```

Alembic revision `compaction_context` adds nullable
`model.context_window` and `turnrow.context_tokens` columns.

`resolve_model(provider, model_name, context_window=None)` passes:

```python
profile={"context_window": context_window} if context_window else None
```

to the model constructor. `resolve_agent_runtime` passes the selected Model's
override. Known models continue to use pydantic-ai's built-in profile when no
override is set.

### `TurnRow.context_tokens`

```python
class TurnRow(SQLModel, table=True):
    ...
    context_tokens: int | None = None
```

`Turn` gains `context_tokens: int | None = None` and
`created_at: datetime | None = None`. `SQLiteMessageLogStore` reads/writes
both. Assistant turns record `result.response.usage.total_tokens` when
`usage.has_values()` is true; otherwise the value is `None`. `created_at` is used
to tell whether a summary was produced after the latest usage sample.

### Summary turns

A summary is a normal `TurnRow` with `role="summary"` and `context_tokens=None`.
It is inserted into the current branch with `parent_id` equal to the cut-off
turn, and the first retained turn's `parent_id` is rewired to the summary. The
summary's parent pointer preserves branch provenance, but **history traversal
stops at a summary turn**: the summary is a root for model history.

This insertion is not a normal append:

- append the summary row with `parent_id = cutoff.id`;
- set the first retained turn's `parent_id = summary.id`;
- keep `session.head_id` at the latest retained turn (or use the summary when
  there are no retained turns).

The store therefore needs `append` plus `set_parent(turn_id, parent_id)`.
`Session.history()` walks from the head and breaks after adding a summary
turn, so summarized ancestors are not replayed.

This makes the summary branch-aware: a fork before the cut-off never sees it;
a fork after the summary includes it and stops there.

`turns_to_messages` maps roles:

- `user` → `ModelRequest(parts=[UserPromptPart(...)])`
- `assistant` → `ModelResponse(parts=[TextPart(...)])`
- `summary` → `ModelRequest` with a `UserPromptPart` prefixed by
  `"Earlier conversation summary:\n\n"`.

The model sees the summary as session context; it is not an assistant claim.

## Middleware architecture

`agentbox_harness/middleware.py`:

```python
@dataclass
class RunContext:
    session: Session
    model: Model
    bus: EventBus
    prompt: str
    prompt_override: list | None = None
    message_history: list[ModelMessage] = field(default_factory=list)
    outcome: RunOutcome | None = None

class RunMiddleware(Protocol):
    async def before_run(self, ctx: RunContext) -> None: ...
    async def on_context_overflow(
        self, ctx: RunContext
    ) -> list[ModelMessage] | None: ...

class MiddlewarePipeline:
    def __init__(self, middleware: list[RunMiddleware]): ...
    async def prepare(self, ctx: RunContext) -> None: ...
    async def recover(self, ctx: RunContext) -> list[ModelMessage] | None: ...
```

- `prepare` runs `before_run` in order; middleware may append summary turns to
  the session.
- `recover` runs `on_context_overflow` in order; the first middleware that can
  compact updates the session and returns the new message history.
- `Harness` owns a pipeline, defaulting to
  `[CompactionMiddleware(config)]`; callers may pass a custom pipeline.
- `Harness.run` builds the `RunContext`, calls `prepare`, appends the new user
  turn, computes `message_history`, and starts the run.
- `RunManager._drive` catches `ModelContextWindowExceededError`; if a pipeline
  is present and the run has not already retried, it calls `recover`, replaces
  the history, and retries once on the same bus/run id.
- The retry is best-effort: if the overflow happened after current-run tool
  messages, those messages are not persisted and are re-derived on retry. This
  limitation is documented; proactive compaction makes it rare.

## Compaction

`agentbox_harness/compaction.py`:

```python
@dataclass(frozen=True)
class CompactionConfig:
    enabled: bool = True
    ratio: float = 0.8
    keep_turns: int = 4
    input_budget_tokens: int = 16_000
    max_summary_chars: int = 8_000
```

### Proactive compaction

`CompactionMiddleware.before_run`:

1. Return if compaction is disabled or the model has no `context_window`.
2. Load the current history.
3. Find the latest assistant turn with `context_tokens`. If a summary turn was
   **created after** that turn, skip (its usage predates the last compaction).
4. Return if `context_tokens < int(context_window * ratio)`.
5. Call `compact(force=False)`.

### Cut-off and input budget

`compact(force: bool)`:

- Load `history = await session.history()`.
- Keep the last `keep_turns` turns; candidates are the turns before them.
- If there are no candidates, return `False`.
- Select the oldest candidates whose estimated tokens (`len(text) // 4`) fit
  within `input_budget_tokens`, capped at half the context window when known.
  Always include at least one candidate.
- Format the selected turns (including prior summary turns) as labelled text.
- Ask the summarizer for a structured summary. If it fails or returns empty,
  log a warning and return `False`.
- Insert the `summary` turn as described above: append it with `parent_id` =
  the cut-off turn id, rewire the first retained turn to it, and leave the
  head on the latest retained turn (or on the summary when there are none).
  Truncate the summary to `max_summary_chars`.
- Return `True`.

When `force=True` (reactive path), skip the ratio and “summary after usage”
checks but still keep the last `keep_turns` turns.

### Summarizer prompt

System prompt:

> You compress conversation history for an AI coding agent. Produce a concise
> summary under these headings: Goal, Decisions, Work completed, Files and
> commands, Current state, Open tasks. Preserve exact file paths, commands,
> errors, identifiers, and user constraints. Do not invent details. Output
> only the summary.

The user message is the labelled selected-turn transcript. The summarizer is a
plain `Agent(model, system_prompt=...)` with no tools. It uses the same model
as the agent.

### History after compaction

The summary turn is inserted before the retained recent turns. On the next
run, `turns_to_messages` replays the summary followed by the recent turns. The
next assistant turn records the new, lower `context_tokens`.

## Reactive recovery

- `normalize_error` sets `RunOutcome.code="context_window"` for
  `ModelContextWindowExceededError`.
- `RunManager._drive` catches that exception and asks the pipeline to recover.
- If compaction succeeds, the run retries once with the new history and no
  duplicate user turn.
- If compaction is impossible or the retry fails, the run ends with the normal
  error outcome, now carrying `code="context_window"`.

## API and settings

`Settings` gains:

| Setting | Default |
|---|---|
| `compaction_enabled` | `True` |
| `compaction_ratio` | `0.8` |
| `compaction_keep_turns` | `4` |
| `compaction_input_budget_tokens` | `16000` |
| `compaction_max_summary_chars` | `8000` |

The API builds a `CompactionConfig` and passes it when constructing `Harness`
in chat, ACP, and A2A.

`ModelCreate`/`ModelRead` include optional `context_window`. The provider
model form gains an optional “Context window” number input.

`GET /sessions/{sid}/messages` returns the active chain and **stops at a
summary turn**, so the UI shows the summary notice plus retained turns rather
than the summarized transcript. Summary turns have `role="summary"`.

ACP `load_session` skips summary turns (internal context). A2A does not load
history.

## UI

- `SessionPage` renders a `SummaryNotice` card for summary turns: collapsed by
  default, titled “Earlier conversation summarized”, with an expand/collapse
  control and the summary text. It is not rendered as a normal assistant
  bubble.
- The provider model form shows the optional context window field.
- No compaction settings UI; environment/settings only.

## Tests

- Model/migration: `Model.context_window` and `TurnRow.context_tokens`
  roundtrip; Alembic upgrade on a scratch DB.
- Resolver: explicit context window becomes `profile["context_window"]`;
  known model profile remains the fallback.
- Store: assistant context tokens persist and reload.
- Compaction: proactive trigger, skip when disabled/unknown window/no usage,
  skip when a summary was created after the last usage sample, cut-off/keep
  behavior, input budget, summary insertion/rewiring, history stopping at the
  summary, and `turns_to_messages` mapping.
- Fork: a summary before a fork point is not included in the forked history;
  a summary before retained turns is included and terminates history traversal.
- Reactive: a fake model raises `ModelContextWindowExceededError` once, the
  pipeline compacts, and the run retries successfully once.
- Middleware: hook order, first successful recovery wins, no recovery returns
  `None`.
- API: model create/read context window; messages include summary role.
- Frontend: `SummaryNotice` renders/expands; provider model form accepts a
  context window.

## Out of scope

- Vendoring the LiteLLM registry or real tokenizer preflight.
- pydantic-ai provider-native compaction capabilities (OpenAI/Anthropic).
- Per-agent summarizer models or manual summary editing.
- Persisting full pydantic-ai tool-call history (D9 can revisit this).
- Recursive multi-pass summarization; the input budget is one pass.
- Compaction settings UI.

## Risks

- Summarization costs an extra model call and adds latency, especially on the
  reactive path.
- The summarizer input budget is estimated from characters; it is used only to
  choose a safe summarizer input, not to trigger compaction.
- Unknown models without a `context_window` override rely on reactive
  recovery, which may lose current-run tool context on retry.
- Summary quality varies by model; the prompt asks for exact identifiers and
  forbids invention.
- A single summary turn applies to the branch it was appended to; forks before
  the cut-off naturally exclude it.
