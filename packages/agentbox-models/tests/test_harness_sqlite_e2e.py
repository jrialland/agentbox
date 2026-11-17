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
from agentbox_models.repos.message_log import SQLiteMessageLogStore


async def write_file(path: str, content: str) -> str:
    return "ok"


async def test_harness_session_persists_turns():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)

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
    harness = Harness(registry=reg, model="test", store_factory=InMemoryMessageLogStore)

    async with factory() as s:
        store = SQLiteMessageLogStore(s, "sess1")
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
