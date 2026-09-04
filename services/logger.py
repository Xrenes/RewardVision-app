"""Logging service for RewardVision.

Wraps Loguru with a console sink and a rotating file sink. The file sink
is created lazily via :func:`setup_logging` so the ``logs/`` directory is
only touched once, at startup.
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

# Project root = parent of the ``services`` package directory.
from core.paths import data_path

_LOG_DIR = data_path("logs")

_CONSOLE_FORMAT = (
    "<green>{time:HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan> - <level>{message}</level>"
)
_FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
    "{name}:{function}:{line} - {message}"
)

_configured = False


def setup_logging(*, level: str = "INFO", save_to_file: bool = True) -> "logger":
    """Configure the global logger. Safe to call once at application start.

    Args:
        level: Minimum level for the console sink.
        save_to_file: When True, also write a rotating log file under ``logs/``.

    Returns:
        The configured Loguru logger instance.
    """
    global _configured
    if _configured:
        return logger

    logger.remove()
    # In a windowed PyInstaller build there is no console, so sys.stderr is None.
    if sys.stderr is not None:
        logger.add(sys.stderr, level=level, format=_CONSOLE_FORMAT, enqueue=True)

    if save_to_file:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        logger.add(
            _LOG_DIR / "rewardvision_{time:YYYY-MM-DD}.log",
            level="DEBUG",
            format=_FILE_FORMAT,
            rotation="5 MB",
            retention="14 days",
            compression="zip",
            enqueue=True,
            backtrace=False,
            diagnose=False,
        )

    _configured = True
    logger.debug("Logging initialised (level={}, file={})", level, save_to_file)
    return logger


def get_logger() -> "logger":
    """Return the shared logger, configuring it with defaults if needed."""
    if not _configured:
        setup_logging()
    return logger
