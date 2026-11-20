from pydantic_ai.messages import ModelRequest, UserPromptPart
from pydantic_ai.models.test import TestModel
from pydantic_ai.profiles import ModelProfile

from agentbox_harness.compaction import CompactionConfig, CompactionMiddleware
from agentbox_harness.events import EventBus
from agentbox_harness.messages import turns_to_messages
from agentbox_harness.middleware import RunContext
from agentbox_harness.session import InMemoryMessageLogStore, Session, Turn


async def _session_with_history() -> Session:
    session = Session(
        session_id="s1",
        project_root=".",
        agent_spec=None,
        store=InMemoryMessageLogStore(),
        head_id=None,
    )
    for index in range(6):
        role = "user" if index % 2 == 0 else "assistant"
        await session.append(
            Turn(
                id=f"t{index}",
                role=role,
                content=f"turn {index}",
                parent_id=None,
                context_tokens=900 if role == "assistant" else None,
            ),
            parent_id=session.head_id,
        )
    return session


def _ctx(session: Session, window: int | None = 1000) -> RunContext:
    profile: ModelProfile | None = (
        {"context_window": window} if window else None
    )
    model = TestModel(custom_output_text="SUMMARY", profile=profile)
    return RunContext(
        session=session,
        model=model,
        bus=EventBus(),
        prompt="next",
    )


async def test_before_run_compacts_above_threshold():
    session = await _session_with_history()
    ctx = _ctx(session)
    middleware = CompactionMiddleware(
        CompactionConfig(keep_turns=2, input_budget_tokens=100_000)
    )
    await middleware.before_run(ctx)

    history = await session.history()
    assert history[0].role == "summary"
    assert history[0].content == "SUMMARY"
    assert [turn.id for turn in history[1:]] == ["t4", "t5"]


async def test_second_run_skips_when_summary_is_newer_than_usage():
    session = await _session_with_history()
    ctx = _ctx(session)
    middleware = CompactionMiddleware(
        CompactionConfig(keep_turns=2, input_budget_tokens=100_000)
    )
    await middleware.before_run(ctx)
    await middleware.before_run(ctx)
    history = await session.history()
    assert sum(1 for turn in history if turn.role == "summary") == 1


async def test_no_window_or_disabled_does_not_compact():
    session = await _session_with_history()
    ctx = _ctx(session, window=None)
    middleware = CompactionMiddleware(CompactionConfig(keep_turns=2))
    await middleware.before_run(ctx)
    history = await session.history()
    assert all(turn.role != "summary" for turn in history)

    ctx = _ctx(session)
    disabled = CompactionMiddleware(CompactionConfig(enabled=False))
    await disabled.before_run(ctx)
    history = await session.history()
    assert all(turn.role != "summary" for turn in history)


async def test_force_compaction_works_without_window():
    session = await _session_with_history()
    ctx = _ctx(session, window=None)
    middleware = CompactionMiddleware(CompactionConfig(keep_turns=2))
    history = await middleware.on_context_overflow(ctx)
    assert history is not None
    current = await session.history()
    assert current[0].role == "summary"


async def test_summary_maps_to_user_context():
    session = await _session_with_history()
    ctx = _ctx(session)
    middleware = CompactionMiddleware(
        CompactionConfig(keep_turns=2, input_budget_tokens=100_000)
    )
    await middleware.before_run(ctx)
    messages = turns_to_messages(await session.history())
    assert isinstance(messages[0], ModelRequest)
    part = messages[0].parts[0]
    assert isinstance(part, UserPromptPart)
    assert "Earlier conversation summary" in part.content
