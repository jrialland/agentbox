from sqlmodel import select

import agentbox_models.tables.auth  # noqa: F401  (registers User in metadata)
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.core import Agent, Model, Provider, TurnRow


async def test_agent_and_turn_roundtrip():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(
            Provider(
                id="prov1",
                name="openai",
                kind="openai_responses",
                base_url="https://api.openai.com/v1",
            )
        )
        s.add(Model(id="m1", provider_id="prov1", name="gpt-4o"))
        s.add(
            Agent(
                id="a1",
                name="coder",
                description="d",
                instructions="i",
                model_id="m1",
                tool_bindings='[{"name":"write_file"}]',
                mode_definitions='[{"name":"agent","flags":{"write":true}}]',
                sub_agent_ids="[]",
            )
        )
        s.add(TurnRow(id="t1", session_id="s1", role="user", content="hi", parent_id=None))
        await s.commit()
        agent = (await s.execute(select(Agent).where(Agent.id == "a1"))).scalars().first()
        assert agent.model_id == "m1"
        turns = (
            await s.execute(select(TurnRow).where(TurnRow.session_id == "s1"))
        ).scalars().all()
        assert len(turns) == 1
    await engine.dispose()
