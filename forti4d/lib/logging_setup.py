"""
logging_setup.py
Central loguru configuration for forti4d.

Library callers stay silent by default — forti4d/__init__.py calls
logger.disable("forti4d") on import, so nothing forti4d logs is emitted
unless a consumer explicitly opts in (either by calling configure_logging()
below, or by calling logger.enable("forti4d") themselves and adding their
own sinks). The CLI (pipeline.py::main()) always calls configure_logging().
"""

import sys
from pathlib import Path

from loguru import logger

DEFAULT_LOG_FILENAME = "forti4d.log"

_CONSOLE_FORMAT = "<level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
_FILE_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}"

# Sink ids added by the last configure_logging() call — tracked so a
# second call is idempotent (doesn't accumulate duplicate sinks) without
# ever touching sinks a host application added on its own.
_added_sink_ids = []


def _clear_previous_sinks() -> None:
    """
    Removes only what a previous configure_logging() call added, plus —
    once — loguru's own default stderr sink (id 0, auto-added on import).
    Never logger.remove() with no arguments: that would destroy sinks a
    host application configured for itself.
    """
    try:
        logger.remove(0)
    except ValueError:
        pass
    for sink_id in _added_sink_ids:
        try:
            logger.remove(sink_id)
        except ValueError:
            pass
    _added_sink_ids.clear()


def configure_logging(results_dir, *, console_level="INFO", quiet=False, log_file=True, log_path=None):
    """
    Opt-in logging setup for forti4d. The CLI calls this unconditionally;
    a library caller only gets it if they call it explicitly.

    Console (stderr): WARNING+ if quiet else console_level (INFO by
    default) — --quiet's new meaning is a level filter, not all-or-nothing.
    File (<results_dir>/forti4d.log by default, or log_path if given):
    always DEBUG+ regardless of `quiet` — full detail is never silently
    lost. Pass log_file=False to skip the file sink entirely.

    Returns the resolved log file Path, or None if log_file=False.
    """
    logger.enable("forti4d")
    _clear_previous_sinks()

    resolved_console_level = "WARNING" if quiet else console_level
    _added_sink_ids.append(
        logger.add(sys.stderr, level=resolved_console_level, format=_CONSOLE_FORMAT, colorize=True, filter="forti4d")
    )

    resolved_log_path = None
    if log_file:
        resolved_log_path = Path(log_path) if log_path else Path(results_dir) / DEFAULT_LOG_FILENAME
        resolved_log_path.parent.mkdir(parents=True, exist_ok=True)
        _added_sink_ids.append(
            logger.add(
                resolved_log_path,
                level="DEBUG",
                format=_FILE_FORMAT,
                encoding="utf-8",
                mode="w",
                enqueue=True,
                filter="forti4d",
            )
        )

    return resolved_log_path
