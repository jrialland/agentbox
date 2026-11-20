from pydantic_ai.messages import ModelRequest, UserPromptPart

from agentbox_harness.messages import turns_to_messages
from agentbox_harness.session import InMemoryMessageLogStore, Session, Turn


def _session() -> Session:
    return Session(
        session_id="s1",
        project_root=".",
        agent_spec=None,
        store=InMemoryMessageLogStore(),
        head_id=None,
    )


def _turn(id: str, role: str, content: str, context_tokens=None) -> Turn:
    return Turn(
        id=id,
        role=role,
        content=content,
        parent_id=None,
        context_tokens=context_tokens,
    )


async def test_summary_is_a_history_boundary_and_rewires_retained_turns():
    session = _session()
    t1 = _turn("t1", "user", "one")
    t2 = _turn("t2", "assistant", "two", context_tokens=900)
    t3 = _turn("t3", "user", "three")
    t4 = _turn("t4", "assistant", "four")
    for turn in (t1, t2, t3, t4):
        await session.append(turn, parent_id=session.head_id)

    summary = _turn("sum", "summary", "the summary")
    await session.insert_summary(summary, cutoff_id=t2.id, retained_first=t3)

    history = await session.history()
    assert [turn.id for turn in history] == ["sum", "t3", "t4"]
    assert (await session.store.get("sum")).parent_id == "t2"
    assert (await session.store.get("t3")).parent_id == "sum"
    assert session.head_id == "t4"


async def test_fork_before_summary_does_not_include_it():
    session = _session()
    t1 = _turn("t1", "user", "one")
    t2 = _turn("t2", "assistant", "two")
    t3 = _turn("t3", "user", "three")
    t4 = _turn("t4", "assistant", "four")
    for turn in (t1, t2, t3, t4):
        await session.append(turn, parent_id=session.head_id)
    await session.insert_summary(
        _turn("sum", "summary", "summary"), cutoff_id=t2.id, retained_first=t3
    )

    forked = Session(
        session_id="s1",
        project_root=".",
        agent_spec=None,
        store=session.store,
        head_id=t2.id,
    )
    assert [turn.id for turn in await forked.history()] == ["t1", "t2"]


def test_summary_role_maps_to_user_context():
    messages = turns_to_messages([_turn("sum", "summary", "compressed")])
    assert isinstance(messages[0], ModelRequest)
    part = messages[0].parts[0]
    assert isinstance(part, UserPromptPart)
    assert "Earlier conversation summary" in part.content
    assert "compressed" in part.content
