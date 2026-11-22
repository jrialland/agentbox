from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.core import PluginState


async def test_plugin_state_round_trip(tmp_path):
    engine, factory = create_engine_and_sessionmaker(
        "sqlite+aiosqlite:///:memory:"
    )
    await init_db(engine)
    try:
        async with factory() as s:
            s.add(
                PluginState(
                    id="global:acme",
                    plugin_name="acme",
                    scope="global",
                )
            )
            await s.commit()
        async with factory() as s:
            row = await s.get(PluginState, "global:acme")
            assert row is not None
            assert row.enabled is False
            assert row.project_id is None
    finally:
        await engine.dispose()
