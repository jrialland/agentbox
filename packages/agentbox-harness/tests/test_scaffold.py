import asyncio

import agentbox_harness


def test_package_imports():
    assert hasattr(agentbox_harness, "__version__")


def test_async_test_harness_works():
    async def inner():
        await asyncio.sleep(0)
        return 42

    assert asyncio.run(inner()) == 42
