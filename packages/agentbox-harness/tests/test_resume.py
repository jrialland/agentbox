from agentbox_harness.session import InMemoryMessageLogStore, Session, Turn


async def test_history_returns_ordered_chain_to_head():
    store = InMemoryMessageLogStore()
    session = Session(
        session_id="s1", project_root=".", agent_spec=None, store=store, head_id=None
    )
    t1 = Turn(id="t1", role="user", content="q1", parent_id=None)
    t2 = Turn(id="t2", role="assistant", content="a1", parent_id="t1")
    t3 = Turn(id="t3", role="user", content="q2", parent_id="t2")
    for t, p in [(t1, None), (t2, "t1"), (t3, "t2")]:
        await session.append(t, parent_id=p)

    assert [t.id for t in await session.history()] == ["t1", "t2", "t3"]


async def test_history_after_fork_follows_new_branch():
    store = InMemoryMessageLogStore()
    session = Session(
        session_id="s1", project_root=".", agent_spec=None, store=store, head_id=None
    )
    t1 = Turn(id="t1", role="user", content="q1", parent_id=None)
    t2 = Turn(id="t2", role="assistant", content="a1", parent_id="t1")
    t3 = Turn(id="t3", role="assistant", content="a2", parent_id="t1")
    for t, p in [(t1, None), (t2, "t1"), (t3, "t1")]:
        await session.append(t, parent_id=p)

    assert [t.id for t in await session.history()] == ["t1", "t3"]
