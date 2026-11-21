import traceback

from loguru import logger


def log_exception(message: str, *args: object) -> None:
    """Log the active exception as traceback text, safe for enqueued sinks."""
    traceback_text = traceback.format_exc()
    logger.opt(exception=None).error("{} | {}", message.format(*args), traceback_text)
