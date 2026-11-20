from agentbox_api.skills import prepare_agent
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.core import Agent, Model, Provider


async def test_prepare_agent_returns_sub_session_runner(tmp_path):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    try:
        async with factory() as s:
            s.add(Provider(id="prov", name="prov", kind="test"))
            s.add(Model(id="m1", provider_id="prov", name="test-model"))
            s.add(
                Agent(
                    id="ag",
                    name="bot",
                    description="d",
                    instructions="i",
                    model_id="m1",
                    sub_agent_ids='["child"]',
                )
            )
            await s.commit()
        prepared = await prepare_agent(
            factory,
            "bot",
            str(tmp_path),
            str(tmp_path / "skills"),
            session_id="s1",
        )
        assert prepared.sub_session_runner is not None
    finally:
        await engine.dispose()
