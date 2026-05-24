"""Tests for the v0.1.0 worker entry point (`python -m meow.worker`)."""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

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


def test_main_starts_worker(_capture_worker_log: io.StringIO) -> None:
    """``main()`` must emit the ``worker.started`` JSON line and then call
    ``workflows.run_worker`` with the registered workflow classes. We patch
    ``run_worker`` so the test returns instead of polling forever — and
    assert it was awaited with the right workflows."""
    from meow.worker import __main__ as worker_main

    with patch(
        "mistralai.workflows.run_worker",
        new_callable=AsyncMock,
        return_value=None,
    ) as run_worker:
        worker_main.main()

    run_worker.assert_awaited_once_with(worker_main._WORKFLOWS)
    assert len(worker_main._WORKFLOWS) == 1
    assert worker_main._WORKFLOWS[0] is worker_main.GithubEventHandler

    lines = [line for line in _capture_worker_log.getvalue().splitlines() if line]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["svc"] == "worker"
    assert payload["event"] == "worker.started"
    assert payload["level"] == "info"
    assert payload["workflows"] == ["GithubEventHandler"]
