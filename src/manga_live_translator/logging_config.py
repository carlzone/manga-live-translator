"""Application logging setup."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from manga_live_translator.paths import logs_dir

LOGGER_NAME = "manga_live_translator"


def configure_logging(directory: Path | None = None) -> logging.Logger:
    """Configure and return the application logger once per process."""
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger

    target = directory or logs_dir()
    target.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        target / "manga-live-translator.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.propagate = False
    return logger
