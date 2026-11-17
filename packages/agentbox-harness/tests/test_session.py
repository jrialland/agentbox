from agentbox_harness.session import InMemoryMessageLogStore, Session, Turn


def test_branching_edit_keeps_history():
    store = InMemoryMessageLogStore()
    session = Session(
        session_id="s1", project_root=".", agent_spec=None, store=store, head_id=None
    )

    t1 = Turn(id="t1", role="user", content="q1", parent_id=None)
    t2 = Turn(id="t2", role="assistant", content="a1", parent_id="t1")
    session.append(t1, parent_id=None)
    session.append(t2, parent_id="t1")

    # Edit t1: fork a new branch (keep t1, add a new child) without deleting t2
    t3 = Turn(id="t3", role="assistant", content="a2", parent_id="t1")
    session.append(t3, parent_id="t1")

    assert session.head_id == "t3"
    ids = [t.id for t in store.list_turns()]
    assert set(ids) == {"t1", "t2", "t3"}  # nothing deleted
