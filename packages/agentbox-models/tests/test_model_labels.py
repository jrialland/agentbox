from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.repos.model_labels import canonical_label, resolve_model_label
from agentbox_models.tables.core import Label, Model, ModelLabelLink, Provider


async def _db():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    return engine, factory


def test_canonical_label():
    assert canonical_label("  Fast  ") == "fast"
    assert canonical_label("High   End") == "high end"
    assert canonical_label("   ") == ""


async def test_resolve_model_label_priority_and_provider_tiebreak():
    engine, factory = await _db()
    try:
        async with factory() as s:
            s.add(Provider(id="p1", name="alpha", kind="test"))
            s.add(Provider(id="p2", name="beta", kind="test"))
            await s.flush()
            s.add(Model(id="m1", provider_id="p1", name="slow"))
            s.add(Model(id="m2", provider_id="p2", name="cheap"))
            s.add(Model(id="m3", provider_id="p2", name="fast"))
            s.add(Label(id="l", name="fast"))
            await s.flush()
            s.add(ModelLabelLink(model_id="m1", label_id="l", priority=0))
            s.add(ModelLabelLink(model_id="m2", label_id="l", priority=1))
            s.add(ModelLabelLink(model_id="m3", label_id="l", priority=1))
            await s.commit()

            resolved = await resolve_model_label(s, " FAST ")
            assert resolved is not None and resolved.id == "m1"

            await s.delete(await s.get(ModelLabelLink, ("m1", "l")))
            await s.commit()
            resolved = await resolve_model_label(s, "fast")
            assert resolved is not None and resolved.id == "m2"
    finally:
        await engine.dispose()


async def test_resolve_unknown_label_returns_none():
    engine, factory = await _db()
    try:
        async with factory() as s:
            assert await resolve_model_label(s, "missing") is None
    finally:
        await engine.dispose()
