"""Structured JSON logging for meow services.

Each log record is emitted as a single JSON line on stdout with the
following keys (SPEC §13.1, with minor divergence: ``level`` is
uppercase, ``ts`` has microsecond precision):

    {"ts": "...", "svc": "...", "level": "...", "event": "...", ...extras}

JSON serialization is delegated to ``python-json-logger``.
"""

from __future__ import annotations

import logging
import sys

from pythonjsonlogger.json import JsonFormatter as _LibJsonFormatter

# Sentinel attribute set on the stdout handler to detect previously installed
# handlers and guarantee idempotence of :func:`get_logger`.
_HANDLER_SENTINEL = "_meow_json_handler"


def _build_formatter(service: str) -> _LibJsonFormatter:
    """Return the JSON formatter used by every meow handler."""
    return _LibJsonFormatter(
        fmt=["levelname", "message"],
        rename_fields={"levelname": "level", "message": "event", "timestamp": "ts"},
        static_fields={"svc": service},
        timestamp=True,
    )


def get_logger(service: str) -> logging.Logger:
    """Return a logger that emits structured JSON lines on stdout.

    Calling this function multiple times with the same ``service`` is safe:
    handlers are de-duplicated so a single log call results in a single
    emitted line.
    """
    logger = logging.getLogger(f"meow.{service}")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for handler in logger.handlers:
        if getattr(handler, _HANDLER_SENTINEL, False):
            return logger

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(_build_formatter(service))
    setattr(handler, _HANDLER_SENTINEL, True)
    logger.addHandler(handler)
    return logger
