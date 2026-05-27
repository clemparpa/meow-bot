"""Tests for the v0.1.0 worker entry point (`python -m meow.worker`)."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from meow.common.logging import get_logger


@pytest.fixture(autouse=True)
def _capture_worker_logs(caplog: pytest.LogCaptureFixture):
    # ``get_logger`` sets ``propagate=False``, so caplog's root handler never
    # sees these records — attach its handler directly to the meow logger.
    logger = get_logger("worker")
    logger.addHandler(caplog.handler)
    caplog.set_level(logging.INFO, logger="meow.worker")
    yield
    logger.removeHandler(caplog.handler)


def test_main_starts_worker(caplog: pytest.LogCaptureFixture) -> None:
    """``main()`` must emit the ``worker.started`` event and then call
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

    started: list[Any] = [r for r in caplog.records if r.message == "worker.started"]
    assert len(started) == 1
    assert started[0].workflows == ["GithubEventHandler"]
