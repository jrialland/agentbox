# Context Editing (Heavy-Result Reduction) — Design

Date: 2026-11-22
Status: Approved (design); implementation verified.
Roadmap: D9 — Automatic session shrinking.

## Goal

Reduce the tokens sent to the model by clearing heavy tool results and old
multimodal content that the model has already consumed, once the conversation is
near the model's context limit. Keep the most recent tool results and messages
intact. This is complementary to compaction:

- **Compaction** replaces old user/assistant turns with an LLM summary.
- **Context editing** leaves the conversation structure intact but replaces
  heavy, already-exploited parts (tool returns, binary attachments) with a short
  placeholder.

## Research summary

### LangChain `ContextEditingMiddleware`

Source: `langchain.agents.middleware.context_editing` (LangChain v1).

- `ContextEditingMiddleware(edits=[...], token_count_method="approximate")`.
- `ClearToolUsesEdit` defaults:
  - `trigger = 100_000` input tokens;
  - `keep = 3` most recent tool results;
  - `clear_at_least = 0`;
  - `clear_tool_inputs = False`;
  - `exclude_tools = ()`;
  - `placeholder = "[cleared]"`.
- On trigger, it clears tool messages from oldest to newest, skipping the last
  `keep`, skipping already-cleared results, and skipping excluded tools. Clearing
  replaces the tool message content with the placeholder (and optionally the
  originating tool-call arguments with `{}`).
- Clearing happens in the model-call middleware, so it applies to the history
  sent for that request and persists thereafter.

### pydantic-ai

pydantic-ai 2.69 exposes exactly the needed seam:

- `pydantic_ai.capabilities.ProcessHistory(processor)`.
- The processor runs in `before_model_request`, once per model step, receives
  the current `ModelRequestContext.messages`, and can return a new list.
- `ProcessHistory` writes the result back into `ctx.messages`, so the edit
  persists for later steps in the same run.
- A processor may accept `RunContext` as its first argument, which provides
  `ctx.model` (and therefore `ctx.model.profile["context_window"]`).
- We do **not** need a custom agent loop or a new `Agent` constructor kwarg.

## Decisions

- **Use `ProcessHistory`**, not a custom middleware or a pre-run-only pass. The
  trigger is evaluated before each model request, so a long single run with many
  tool calls is handled.
- **Token trigger is model-aware:**
  `trigger = min(context_editing_trigger_tokens,
  int(context_window * context_editing_trigger_ratio))` when the model profile
  exposes `context_window`; otherwise use `context_editing_trigger_tokens`.
  Defaults: 100_000 tokens, ratio 0.8.
- **Clear to a target, not everything.** After the trigger, clear the oldest
  candidates until the estimate falls to
  `trigger * context_editing_target_ratio` (default 0.6) or there are no more
  candidates. This leaves headroom and avoids clearing every historical result.
- **Keep recency.** Preserve the last `keep_tool_results` tool returns (default
  3) and never modify the last `keep_recent_messages` messages (default 6).
- **Clear tool returns in place.** Replace `ToolReturnPart.content` with a short
  placeholder. Preserve `tool_name`, `tool_call_id`, `timestamp`, `outcome`, and
  mark `metadata.context_editing.cleared = true`. Use a base `ToolReturnPart`
  with `tool_kind=None` so typed tool parts are not re-validated against a shape
  their placeholder does not satisfy.
- **Optional tool-input clearing.** `clear_tool_inputs` (default false) replaces
  the matching `ToolCallPart.args` with `{}`, preserving provider metadata. This
  targets large `write_file`-style arguments. Off by default because arguments
  are also useful context.
- **Clear old binary content.** Replace `BinaryContent` items in old
  `UserPromptPart.content` sequences with a text placeholder when
  `clear_binary` is true (default true). Keep recent messages and keep text,
  URL, and file-reference content.
- **Do not clear text turns.** Old user/assistant text is left to compaction. Do
  not clear thinking parts in this cycle; provider thinking blocks may carry
  signatures that must remain paired.
- **Idempotent.** Already-cleared tool returns have the metadata marker and are
  skipped. Binary placeholders are detected by their exact text.
- **Excluded tools.** `exclude_tools` is a comma-separated setting. Excluded
  tool returns are never cleared (useful for tiny, always-relevant tools).
- **Fail open.** Any error in the processor is logged and returns the original
  messages; context editing must never fail a run.
- **Observability.** Log a single info line when an edit triggers, with
  before/after token estimates and cleared counts. No UI in this cycle.

## Architecture

### New module: `agentbox_harness/context_editing.py`

```python
@dataclass(frozen=True)
class ContextEditingConfig:
    enabled: bool = True
    trigger_tokens: int = 100_000
    trigger_ratio: float = 0.8
    target_ratio: float = 0.6
    keep_tool_results: int = 3
    keep_recent_messages: int = 6
    clear_tool_inputs: bool = False
    clear_binary: bool = True
    exclude_tools: tuple[str, ...] = ()
    placeholder: str = "[tool result cleared to save context; re-run the tool if needed]"
    binary_placeholder: str = "[attachment omitted to save context]"


@dataclass(frozen=True)
class ContextEditingStats:
    triggered: bool
    before_tokens: int
    after_tokens: int
    trigger_tokens: int
    cleared_tool_results: int
    cleared_tool_inputs: int
    cleared_binary_items: int


def estimate_messages_tokens(messages: list[ModelMessage]) -> int: ...
def apply_context_edits(
    messages: list[ModelMessage],
    *,
    trigger_tokens: int,
    config: ContextEditingConfig,
) -> tuple[list[ModelMessage], ContextEditingStats]: ...
def make_context_editing_processor(config: ContextEditingConfig):
    def process(ctx: RunContext, messages: list[ModelMessage]) -> list[ModelMessage]: ...
    return process
```

`apply_context_edits` is pure and testable. It:

1. Estimates tokens. If `<= trigger_tokens`, returns the input unchanged with
   `triggered=False`.
2. Collects tool-return parts in message order. Protects the last
   `keep_tool_results` and any part inside the last `keep_recent_messages`
   messages. Filters excluded tools and already-cleared parts.
3. Clears candidates oldest-first, recomputing the estimate after each clear,
   until `after <= trigger * target_ratio` or no candidates remain.
4. If still above target and `clear_binary`, replaces old `BinaryContent` items
   in user prompts (outside the recent window) with `binary_placeholder` until
   the target is reached or no candidates remain.
5. Returns a new message list (unmodified messages are reused) and stats.

### Token estimation

Approximate, no tokenizer dependency:

- Text: `max(1, len(text) // 4)`.
- Binary: `max(1_000, len(data) // 4)` (images/audio/video are expensive).
- Structured tool-return content / tool-call args: `len(json.dumps(..., default=str)) // 4`.
- Add 4 tokens per message for role/framing overhead.
- This is intentionally conservative enough to decide when to prune, not to
  report billing usage.

### Agent integration

- `build_agent(..., context_editing: ContextEditingConfig | None = None)`:
  - when enabled, add
    `ProcessHistory(make_context_editing_processor(config))` to
    `Agent(capabilities=[...])`.
  - no other agent-loop changes.
- `Harness(..., context_editing: ContextEditingConfig | None = None)` forwards it
  to `build_agent`.
- API Harness construction sites pass
  `context_editing=context_editing_config_from_settings(settings)`.

### Settings (`config.py`)

```python
context_editing_enabled: bool = True
context_editing_trigger_tokens: int = 100_000
context_editing_trigger_ratio: float = 0.8
context_editing_target_ratio: float = 0.6
context_editing_keep_tool_results: int = 3
context_editing_keep_recent_messages: int = 6
context_editing_clear_tool_inputs: bool = False
context_editing_clear_binary: bool = True
context_editing_exclude_tools: str = ""   # comma-separated
context_editing_placeholder: str = "[tool result cleared to save context; re-run the tool if needed]"
context_editing_binary_placeholder: str = "[attachment omitted to save context]"
```

`context_editing_config_from_settings(settings)` lives in
`agentbox_api/runtime.py` next to `compaction_config_from_settings`, parses the
comma-separated exclude list, and clamps ratios to `(0, 1]`.

## Interaction with compaction

- Context editing runs **inside** a run, before each model request.
- Compaction runs **before** a run, based on the last turn's context usage.
- Context editing can reduce the context enough that compaction is delayed; it
  does not remove or summarize turns, so compaction remains the fallback for
  text-heavy histories.
- Both are independently configurable and can be disabled separately.

## Testing

### Unit (`packages/agentbox-harness/tests/test_context_editing.py`)

- No trigger below threshold: messages unchanged, `triggered=False`.
- Trigger clears the oldest tool returns beyond `keep_tool_results` and the
  recent-message window; the last N returns remain intact.
- `exclude_tools` is honored.
- Already-cleared returns are skipped and counted as zero.
- `clear_tool_inputs` clears the matching `ToolCallPart.args` and preserves
  provider fields.
- Old `BinaryContent` in user prompts is replaced; recent attachments and text
  are kept.
- `target_ratio` stops clearing once the estimate is low enough.
- Token estimate decreases and stats are accurate.
- Processor errors return the original list (fail-open).
- The processor picks up `context_window` from a fake `RunContext` and uses the
  ratio (tested through `make_context_editing_processor`).

### Integration

- `build_agent(..., context_editing=...)` attaches a `ProcessHistory`
  capability; disabled config attaches none.
- `Harness` forwards the config to `build_agent`.
- API wiring test asserts `context_editing_config_from_settings` maps settings
  and that a configured Harness builds an agent with the capability.

## Out of scope

- Summarizing or rewriting user/assistant text (compaction owns that).
- Clearing thinking/reasoning parts.
- Persisting edited messages back to the database (the edit applies to the
  in-flight pydantic-ai history; persisted turns are text-only).
- UI for context-editing metrics.
- Tokenizer-exact counting.
- Provider-specific cache-prefix optimizations.
