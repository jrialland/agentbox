import pathlib

import pytest
from loguru import logger

from agentbox_harness.logging import log_exception


class UnpicklableError(Exception):
    def __reduce__(self):
        raise TypeError("cannot pickle this exception")


@pytest.mark.asyncio
async def test_log_exception_uses_text_for_unpicklable_exception(tmp_path: pathlib.Path):
    sink = tmp_path / "safe.log"
    sink_id = logger.add(sink, enqueue=True, format="{message}")
    try:
        try:
            raise UnpicklableError("auth failed")
        except UnpicklableError:
            log_exception("run failed id={}", "r1")
        await logger.complete()
    finally:
        logger.remove(sink_id)
    text = sink.read_text(encoding="utf-8")
    assert "run failed id=r1" in text
    assert "UnpicklableError: auth failed" in text
