"""File logging for the widget.

The log records lifecycle events and exception tracebacks. It never writes
transcript contents, prompts, credentials or database rows.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import default_config_dir

LOGGER_NAME = "ai_token_widget"
MAX_BYTES = 256_000
BACKUP_COUNT = 2


def log_path() -> Path:
    return default_config_dir() / "widget.log"


def configure_logging(path: Path | None = None) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False
    target = path or log_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            target,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
    except OSError:
        return logger
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(handler)

    previous_hook = sys.excepthook

    def _hook(exc_type, exc_value, exc_traceback) -> None:
        logger.critical(
            "Unhandled exception",
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        previous_hook(exc_type, exc_value, exc_traceback)

    sys.excepthook = _hook
    return logger


__all__ = ["configure_logging", "log_path"]
