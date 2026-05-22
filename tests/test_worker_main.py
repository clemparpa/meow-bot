"""Tests for the v0.0.x worker stub (`python -m meow.worker`)."""

from __future__ import annotations

import io
import json
import logging
import signal
from collections.abc import Iterator
from unittest.mock import patch

import pytest

from meow.common.logging import _HANDLER_SENTINEL, JsonFormatter


@pytest.fixture
def _capture_worker_log() -> Iterator[io.StringIO]:
    """Replace the JSON handler attached to the ``meow.worker`` logger with
    one writing to an in-memory stream, so the test can inspect the line
    emitted by ``main()`` without touching stdout."""
    buffer = io.StringIO()
    logger = logging.getLogger("meow.worker")

    saved = list(logger.handlers)
    logger.handlers.clear()

    handler = logging.StreamHandler(buffer)
    handler.setFormatter(JsonFormatter("worker"))
    setattr(handler, _HANDLER_SENTINEL, True)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    try:
        yield buffer
    finally:
        logger.handlers.clear()
        logger.handlers.extend(saved)


def test_main_logs_worker_started_then_blocks(_capture_worker_log: io.StringIO) -> None:
    """``main()`` must emit the ``worker.started`` JSON line and then call
    ``signal.pause()``. We patch ``signal.pause`` to a no-op so the test
    returns instead of blocking forever — and assert it was invoked."""
    from meow.worker import __main__ as worker_main

    with patch.object(signal, "pause", return_value=None) as pause:
        worker_main.main()

    pause.assert_called_once()

    lines = [line for line in _capture_worker_log.getvalue().splitlines() if line]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["svc"] == "worker"
    assert payload["event"] == "worker.started"
    assert payload["level"] == "info"
    assert payload["mode"] == "stub"
