# Context Editing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Status: Approved; implementation verified.

**Goal:** Reduce tokens sent to the model by clearing old heavy tool results and binary attachments when the context nears the model window, keeping recent results and complementing compaction.

**Architecture:** A pure `apply_context_edits` function plus a `make_context_editing_processor` wrapper. Pydantic-ai's `ProcessHistory` capability runs the processor before every model request. Agent/Harness/API wire the config; settings and docs expose thresholds.

**Tech Stack:** Python 3.11+, pydantic-ai 2.69 (`ProcessHistory`, `ModelMessage` dataclasses), pytest/pytest-asyncio, pydantic-settings.

## Global Constraints

- Python line length 100; Ruff target py311; first-party modules are `agentbox_*`.
- Do **not** commit unless the user explicitly asks.
- Context editing must fail open: any processor error returns the original messages.
- Never clear the last `keep_tool_results` tool returns or the last
  `keep_recent_messages` messages.
- Do not clear thinking parts or user/assistant text.
- Backend tests: run one package per invocation.
- Checks: `uv run ruff check --fix packages`, `uv run ty check packages`.

---

### Task 1: Pure context-editing module

**Files:**
- Create: `packages/agentbox-harness/src/agentbox_harness/context_editing.py`
- Test: `packages/agentbox-harness/tests/test_context_editing.py`

**Interfaces:**
- Produces: `ContextEditingConfig`, `ContextEditingStats`,
  `estimate_messages_tokens(messages) -> int`,
  `apply_context_edits(messages, *, trigger_tokens, config) -> tuple[list[ModelMessage], ContextEditingStats]`,
  `make_context_editing_processor(config)`.
- Consumes: `pydantic_ai.messages` (`ModelMessage`, `ModelRequest`,
  `ModelResponse`, `ToolReturnPart`, `ToolCallPart`, `UserPromptPart`,
  `BinaryContent`, `TextPart`, `ThinkingPart`, `SystemPromptPart`,
  `RetryPromptPart`).

- [ ] **Step 1: Write failing tests**

Create `test_context_editing.py` with helpers that build pydantic-ai messages:

```python
from pydantic_ai.messages import (
    BinaryContent,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from agentbox_harness.context_editing import (
    ContextEditingConfig,
    apply_context_edits,
    estimate_messages_tokens,
    make_context_editing_processor,
)


def _tool_pair(call_id: str, name: str, result: str) -> list:
    return [
        ModelResponse(parts=[ToolCallPart(tool_name=name, args={"q": "x"}, tool_call_id=call_id)]),
        ModelRequest(parts=[ToolReturnPart(tool_name=name, content=result, tool_call_id=call_id)]),
    ]


def test_no_trigger_below_threshold():
    messages = _tool_pair("1", "read_file", "x" * 1000)
    config = ContextEditingConfig(trigger_tokens=10_000)
    edited, stats = apply_context_edits(messages, trigger_tokens=10_000, config=config)
    assert edited == messages
    assert stats.triggered is False
```

Add tests for:

- `test_clears_oldest_and_keeps_last_three`;
- `test_keep_recent_messages_protects_tool_return`;
- `test_exclude_tools`;
- `test_already_cleared_is_skipped`;
- `test_clear_tool_inputs` (assert `args == {}` and provider fields preserved);
- `test_clears_old_binary_but_keeps_recent` (build a `UserPromptPart` with
  `BinaryContent` + text);
- `test_target_ratio_stops_clearing`;
- `test_estimates_tokens` (text + binary > text only);
- `test_processor_fails_open` (monkeypatch `apply_context_edits` to raise).

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest packages/agentbox-harness/tests/test_context_editing.py -q --timeout=60`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement the module**

Key pieces:

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
```

`estimate_messages_tokens`:

- Traverse `ModelRequest.parts` and `ModelResponse.parts`.
- Text parts: `max(1, len(text) // 4)`.
- `BinaryContent`: `max(1_000, len(data) // 4)`.
- Tool-call args / structured returns: `len(json.dumps(value, default=str)) // 4`.
- Add 4 tokens per message.

`apply_context_edits`:

1. `before = estimate_messages_tokens(messages)`; if `before <= trigger_tokens`,
   return unchanged.
2. Build `recent_cutoff = max(0, len(messages) - config.keep_recent_messages)`.
3. Collect `(message_index, part_index, part)` for every `ToolReturnPart` where
   `message_index < recent_cutoff`, not excluded, and not already marked
   `metadata["context_editing"]["cleared"]`.
4. Protect the last `config.keep_tool_results` of that candidate list; iterate
   the rest oldest-first.
5. For each candidate, replace the part with a base `ToolReturnPart` carrying
   the placeholder and metadata marker; optionally replace the matching
   `ToolCallPart.args` with `{}` in a preceding `ModelResponse`.
6. After each clear, recompute the estimate; stop when
   `estimate <= trigger_tokens * config.target_ratio`.
7. If still above target and `clear_binary`, walk `UserPromptPart` content
   sequences before `recent_cutoff`, replacing `BinaryContent` with the binary
   placeholder.
8. Return the new list + stats.

`make_context_editing_processor`:

```python
def make_context_editing_processor(config: ContextEditingConfig):
    def process(ctx, messages):
        window = getattr(ctx.model, "profile", {}).get("context_window")
        trigger = config.trigger_tokens
        if window:
            trigger = min(trigger, int(window * config.trigger_ratio))
        try:
            return apply_context_edits(messages, trigger_tokens=trigger, config=config)[0]
        except Exception:
            logger.exception("context editing failed; keeping history unchanged")
            return messages
    return process
```

- [ ] **Step 4: Run the unit tests**

Run: `uv run pytest packages/agentbox-harness/tests/test_context_editing.py -q --timeout=60`
Expected: PASS.

---

### Task 2: Agent and Harness integration

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/agent_factory.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/harness.py`
- Test: `packages/agentbox-harness/tests/test_agent_factory.py`
- Test: `packages/agentbox-harness/tests/test_context_editing.py`

**Interfaces:**
- Produces: `build_agent(..., context_editing: ContextEditingConfig | None = None)`.
- Produces: `Harness(..., context_editing: ContextEditingConfig | None = None)`.

- [ ] **Step 1: Write failing integration tests**

```python
def test_build_agent_attaches_context_editing_capability():
    reg = ToolRegistry()
    agent = build_agent(
        _spec(), Mode(name="agent", flags={"write": True}), reg, TestModel(),
        context_editing=ContextEditingConfig(enabled=True),
    )
    assert any(type(c).__name__ == "ProcessHistory" for c in agent.capabilities)


def test_build_agent_skips_context_editing_when_disabled():
    ...
    assert not any(type(c).__name__ == "ProcessHistory" for c in agent.capabilities)
```

Check the actual public attribute for capabilities; if it is not
`agent.capabilities`, inspect the `Agent` object and adjust the assertion
(e.g. `agent._capabilities` or run a fake model and assert the processor ran).

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest packages/agentbox-harness/tests/test_agent_factory.py -q --timeout=60`
Expected: FAIL (unexpected keyword `context_editing`).

- [ ] **Step 3: Implement**

In `agent_factory.py`:

```python
from pydantic_ai.capabilities import ProcessHistory

from agentbox_harness.context_editing import (
    ContextEditingConfig,
    make_context_editing_processor,
)

def build_agent(..., context_editing: ContextEditingConfig | None = None) -> Agent:
    ...
    capabilities = []
    if context_editing is not None and context_editing.enabled:
        capabilities.append(ProcessHistory(make_context_editing_processor(context_editing)))
    return Agent(..., capabilities=capabilities or None)
```

In `harness.py`, add the constructor field, `self.context_editing`, and pass it
to `build_agent`.

- [ ] **Step 4: Run harness tests**

Run: `uv run pytest packages/agentbox-harness/tests/test_agent_factory.py packages/agentbox-harness/tests/test_context_editing.py -q --timeout=60`
Expected: PASS.

---

### Task 3: Settings, API wiring, docs, ROADMAP

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/config.py`
- Modify: `packages/agentbox-api/src/agentbox_api/runtime.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/sessions.py`
- Modify: `packages/agentbox-api/src/agentbox_api/acp_server.py`
- Modify: `packages/agentbox-api/src/agentbox_api/a2a_executor.py`
- Modify: `packages/agentbox-api/src/agentbox_api/subagent_sessions.py`
- Test: `packages/agentbox-api/tests/test_context_editing_wiring.py`
- Docs: `docs/architecture/03-backend.md`, `docs/ROADMAP.md`

**Interfaces:**
- Produces: `context_editing_config_from_settings(settings) -> ContextEditingConfig`.

- [ ] **Step 1: Write failing wiring test**

```python
def test_context_editing_config_from_settings():
    settings = SimpleNamespace(
        context_editing_enabled=True,
        context_editing_trigger_tokens=50_000,
        context_editing_trigger_ratio=0.75,
        context_editing_target_ratio=0.5,
        context_editing_keep_tool_results=4,
        context_editing_keep_recent_messages=8,
        context_editing_clear_tool_inputs=True,
        context_editing_clear_binary=True,
        context_editing_exclude_tools="todo_list, lsp_diagnostics",
        context_editing_placeholder="[cleared]",
        context_editing_binary_placeholder="[file omitted]",
    )
    config = context_editing_config_from_settings(settings)
    assert config.trigger_tokens == 50_000
    assert config.exclude_tools == ("todo_list", "lsp_diagnostics")
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest packages/agentbox-api/tests/test_context_editing_wiring.py -q --timeout=60`
Expected: FAIL (missing function/settings).

- [ ] **Step 3: Implement**

- Add the settings block from the spec to `config.py`.
- Add `context_editing_config_from_settings` to `runtime.py`:

```python
def context_editing_config_from_settings(settings) -> ContextEditingConfig:
    excluded = tuple(
        name.strip()
        for name in (settings.context_editing_exclude_tools or "").split(",")
        if name.strip()
    )
    return ContextEditingConfig(
        enabled=settings.context_editing_enabled,
        trigger_tokens=settings.context_editing_trigger_tokens,
        trigger_ratio=min(1.0, max(0.05, settings.context_editing_trigger_ratio)),
        target_ratio=min(1.0, max(0.05, settings.context_editing_target_ratio)),
        keep_tool_results=max(0, settings.context_editing_keep_tool_results),
        keep_recent_messages=max(0, settings.context_editing_keep_recent_messages),
        clear_tool_inputs=settings.context_editing_clear_tool_inputs,
        clear_binary=settings.context_editing_clear_binary,
        exclude_tools=excluded,
        placeholder=settings.context_editing_placeholder,
        binary_placeholder=settings.context_editing_binary_placeholder,
    )
```

- Pass `context_editing=context_editing_config_from_settings(...)` to every
  `Harness(...)` construction (sessions router, ACP, A2A, subagent sessions).
- Update `docs/architecture/03-backend.md` settings table with a Context editing
  row and a short explanation.
- Update `docs/ROADMAP.md`: add sub-project 43
  (`2026-11-22-context-editing-design.md` / plan) and move D9 from deferred to
  DONE/sub-project history.

- [ ] **Step 4: Run API tests**

Run: `uv run pytest packages/agentbox-api/tests/test_context_editing_wiring.py -q --timeout=60`
Expected: PASS.

---

### Task 4: End-to-end verification

- [ ] **Step 1: Add an end-to-end processor test**

In `test_context_editing.py`, build a long message list with several tool pairs
and binary attachments; use a fake `RunContext` whose model profile has
`context_window=10_000`; assert the processor clears old parts, keeps the last
three tool returns and recent messages, and returns a list.

- [ ] **Step 2: Run checks and tests**

```powershell
uv run ruff check --fix packages
uv run ty check packages
uv run pytest packages/agentbox-harness -q
uv run pytest packages/agentbox-api -q
uv run pytest packages/agentbox-models -q
uv run pytest packages/agentbox-providers -q
```

Expected: clean checks; tests pass or skip.

- [ ] **Step 3: Measure**

Log the `before/after` token estimates from the processor on a synthetic
long-history test and record the reduction in the PR/commit notes when the user
asks to commit.
