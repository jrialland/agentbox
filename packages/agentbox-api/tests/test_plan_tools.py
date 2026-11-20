import pytest
from pydantic_ai import ModelRetry
from sqlmodel import select

from agentbox_api.plan_tools import make_plan_tools
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.core import PlanItem, SessionRow


async def _tools():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    return engine, factory, make_plan_tools(factory, "s1")


async def _items(factory):
    async with factory() as s:
        return (
            await s.execute(select(PlanItem).order_by(PlanItem.position))  # ty: ignore[invalid-argument-type]
        ).scalars().all()


async def test_add_list_update_complete_and_clear():
    engine, factory, tools = await _tools()
    try:
        await tools["todo_add"]("first")
        await tools["todo_add"]("second")
        items = await _items(factory)
        assert [item.position for item in items] == [0, 1]
        listing = await tools["todo_list"]()
        assert "first" in listing
        assert "second" in listing
        await tools["todo_update"](
            items[0].id, content="renamed", status="in_progress"
        )
        assert (await _items(factory))[0].content == "renamed"
        await tools["todo_complete"](items[1].id)
        assert (await _items(factory))[1].status == "completed"
        await tools["todo_clear"]()
        assert await _items(factory) == []
        assert await tools["todo_list"]() == "TODO list is empty."
    finally:
        await engine.dispose()


async def test_remove_compacts_and_reorder_validates():
    engine, factory, tools = await _tools()
    try:
        for text in ("a", "b", "c"):
            await tools["todo_add"](text)
        items = await _items(factory)
        await tools["todo_remove"](items[1].id)
        remaining = await _items(factory)
        assert [item.position for item in remaining] == [0, 1]
        await tools["todo_reorder"]([remaining[1].id, remaining[0].id])
        assert [item.content for item in await _items(factory)] == ["c", "a"]
        with pytest.raises(ModelRetry):
            await tools["todo_reorder"]([remaining[0].id])
    finally:
        await engine.dispose()


async def test_invalid_operations_raise_model_retry():
    engine, factory, tools = await _tools()
    try:
        with pytest.raises(ModelRetry):
            await tools["todo_add"]("   ")
        with pytest.raises(ModelRetry):
            await tools["todo_update"]("missing", content="x")
        await tools["todo_add"]("x")
        item = (await _items(factory))[0]
        with pytest.raises(ModelRetry):
            await tools["todo_update"](item.id, status="nope")
    finally:
        await engine.dispose()


async def test_delete_session_data_removes_plan():
    from agentbox_api.runtime import delete_session_data

    engine, factory, tools = await _tools()
    try:
        async with factory() as s:
            s.add(SessionRow(id="s1", project_id="p", agent_id="a"))
            await s.commit()
        await tools["todo_add"]("x")
        await delete_session_data(factory, "s1")
        assert await _items(factory) == []
    finally:
        await engine.dispose()
