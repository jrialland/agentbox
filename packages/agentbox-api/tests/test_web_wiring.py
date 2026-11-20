from agentbox_api.config import Settings
from agentbox_api.runtime import build_registry, web_config_from_settings
from agentbox_api.skills import prepare_agent
from agentbox_harness.spec import Mode
from agentbox_harness.tools.web import WebToolConfig
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.core import Agent, Model, Provider


def test_web_config_from_settings():
    settings = Settings(
        jwt_secret="s" * 32,
        web_search_provider="searxng",
        searxng_url="https://searx.example",
        web_search_max_results=7,
        web_fetch_max_chars=1234,
    )
    config = web_config_from_settings(settings)
    assert config == WebToolConfig(
        search_provider="searxng",
        search_max_results=7,
        searxng_url="https://searx.example",
        fetch_max_chars=1234,
    )


def test_web_tools_are_selectable_when_bound():
    reg = build_registry(".")
    ask = Mode(name="ask", flags={"write": False})
    names = {
        tool.__name__  # ty: ignore[missing-attribute]
        for tool in reg.select_tools(ask, names={"web_search", "fetch_url"})
    }
    assert names == {"web_search", "fetch_url"}
    assert reg.select_tools(ask, names=set()) == []


async def test_prepare_agent_exposes_bound_web_tools(tmp_path):
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
                    tool_bindings='[{"name": "web_search"}, {"name": "fetch_url"}]',
                )
            )
            await s.commit()
        prepared = await prepare_agent(
            factory,
            "bot",
            str(tmp_path),
            str(tmp_path / "skills"),
            web_config=WebToolConfig(search_provider="ddgs"),
        )
        tools = prepared.registry.select_tools(
            Mode(name="ask", flags={"write": False})
        )
        names = {tool.__name__ for tool in tools}  # ty: ignore[missing-attribute]
        assert {"web_search", "fetch_url"} <= names
    finally:
        await engine.dispose()
