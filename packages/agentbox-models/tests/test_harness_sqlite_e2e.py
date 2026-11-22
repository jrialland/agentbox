from pydantic_ai.models.test import TestModel

from agentbox_harness.events import EventBus
from agentbox_harness.harness import Harness
from agentbox_harness.session import InMemoryMessageLogStore, Session
from agentbox_harness.spec import (
    DEFAULT_MODES,
    AgentSpec,
    ModelBinding,
    NativeToolBinding,
)
from agentbox_harness.tools.registry import ToolRegistry
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.repos.message_log import DatabaseMessageLogStore
from agentbox_models.tables.auth import User
from agentbox_models.tables.core import Agent, Model, Project, Provider, SessionRow


async def write_file(path: str, content: str) -> str:
    return "ok"


async def test_harness_session_persists_turns():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(User(id="u1", username="u", email="u@x", password_hash="h"))
        s.add(Provider(id="p1", name="test", kind="test"))
        await s.flush()
        s.add(Model(id="m1", provider_id="p1", name="test"))
        await s.flush()
        s.add(Agent(id="a1", name="coder", description="", instructions="", model_id="m1"))
        s.add(Project(id="pr1", name="p", path=".", owner_id="u1"))
        await s.flush()
        s.add(SessionRow(id="sess1", project_id="pr1", agent_id="a1"))
        await s.commit()

    spec = AgentSpec(
        name="coder",
        description="d",
        instructions="i",
        tool_bindings=[NativeToolBinding(name="write_file")],
        mode_definitions=list(DEFAULT_MODES),
        model_binding=ModelBinding(model="test", provider="test"),
    )
    reg = ToolRegistry()
    reg.register_native("write_file", write_file, required_flags=("write",))
    harness = Harness(registry=reg, model=TestModel(), store_factory=InMemoryMessageLogStore)

    store = DatabaseMessageLogStore(factory, "sess1")
    session = Session(
        session_id="sess1",
        project_root=".",
        agent_spec=spec,
        store=store,
        head_id=None,
    )
    session.mode_name = "agent"
    bus = EventBus()
    outcome = await harness.run_turn(
        session, "write a file", bus=bus, model_override=TestModel()
    )
    assert outcome.status == "success"
    roles = [t.role for t in await session.history()]
    assert roles == ["user", "assistant"]
    await engine.dispose()
