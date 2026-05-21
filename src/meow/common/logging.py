"""Structured JSON logging for meow services.

Each log record is emitted as a single JSON line on stdout, following the
schema defined in `spec.md` §13.1:

    {"ts": "...", "svc": "...", "level": "...", "event": "...", ...extra}

- `ts` is an ISO-8601 timestamp in UTC with a `+00:00` offset.
- `svc` is the service name passed to :func:`get_logger`.
- `level` is the lowercase log level (``info``, ``warning``, ...).
- `event` is the message argument passed to the logger
  (e.g. ``logger.info("webhook.received")``).
- Any extra fields provided via ``logger.info("...", extra={...})`` are
  merged at the top level of the JSON object.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

# Standard ``LogRecord`` attributes — anything not in this set that lives on a
# record was provided by the caller via ``extra=`` and should be surfaced in
# the JSON output.
_STANDARD_LOGRECORD_ATTRS: frozenset[str] = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)

# Sentinel attribute set on the stdout handler to detect previously installed
# handlers and guarantee idempotence of :func:`get_logger`.
_HANDLER_SENTINEL = "_meow_json_handler"


class JsonFormatter(logging.Formatter):
    """Formatter that renders a :class:`logging.LogRecord` as one JSON line."""

    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds")
        payload: dict[str, Any] = {
            "ts": ts,
            "svc": self._service,
            "level": record.levelname.lower(),
            "event": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key in _STANDARD_LOGRECORD_ATTRS:
                continue
            if key.startswith("_"):
                continue
            if key in payload:
                # Don't let caller-supplied fields overwrite the schema keys.
                continue
            payload[key] = value

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str, ensure_ascii=False)


def get_logger(service: str) -> logging.Logger:
    """Return a logger that emits structured JSON lines on stdout.

    Calling this function multiple times with the same ``service`` is safe:
    handlers are de-duplicated so a single log call results in a single
    emitted line.
    """

    logger = logging.getLogger(f"meow.{service}")
    logger.setLevel(logging.INFO)
    # Prevent double-emission via the root logger if it has handlers.
    logger.propagate = False

    for existing in logger.handlers:
        if getattr(existing, _HANDLER_SENTINEL, False):
            return logger

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter(service))
    setattr(handler, _HANDLER_SENTINEL, True)
    logger.addHandler(handler)
    return logger
