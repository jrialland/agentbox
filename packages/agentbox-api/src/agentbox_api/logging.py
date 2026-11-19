"""Loguru sink configuration: console + rotating file, stdlib interception."""

import logging
import sys
from pathlib import Path

from loguru import logger

from agentbox_api.config import Settings

_CONSOLE_FORMAT = (
    "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)
_FILE_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} - {message}"


class InterceptHandler(logging.Handler):
    """Route stdlib logging records into loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame is not None and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def configure_logging(settings: Settings) -> None:
    """Install loguru sinks (stderr + rotating file); never writes to stdout."""
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        colorize=True,
        format=_CONSOLE_FORMAT,
        diagnose=False,
    )
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_dir / "agentbox.log",
        level=settings.log_level,
        format=_FILE_FORMAT,
        rotation=settings.log_rotation,
        retention=settings.log_retention,
        compression=settings.log_compression,
        enqueue=True,
        diagnose=False,
    )
    if not settings.log_intercept:
        return
    logging.basicConfig(handlers=[InterceptHandler()], level=logging.DEBUG, force=True)
    for name in ("uvicorn", "uvicorn.error", "starlette", "sqlalchemy", "asyncio"):
        stdlib_logger = logging.getLogger(name)
        stdlib_logger.handlers = [InterceptHandler()]
        stdlib_logger.propagate = False
    logging.getLogger("uvicorn.access").propagate = False
