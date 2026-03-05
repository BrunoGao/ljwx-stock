import logging
from typing import Final

from pythonjsonlogger.json import JsonFormatter


DEFAULT_LOG_FORMAT: Final[str] = "%(asctime)s %(levelname)s %(name)s %(message)s"


def setup_logging(log_level: str) -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level.upper())

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter(DEFAULT_LOG_FORMAT))

    root_logger.handlers.clear()
    root_logger.addHandler(handler)
