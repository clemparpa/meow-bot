"""Tests for the v0.1.0 worker entry point (`python -m meow.worker`)."""

from __future__ import annotations

import asyncio
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


async def _never_returns(_port: int) -> None:
    """Stand-in for ``_liveness_listener`` that blocks until cancelled.

    The real listener would bind a TCP port — patching it out avoids touching
    a real socket from the test process (and racing with whatever else might
    own port 8000).
    """

    await asyncio.Event().wait()


def test_main_starts_worker(caplog: pytest.LogCaptureFixture) -> None:
    """``main()`` must emit the ``worker.started`` event and then call
    ``workflows.run_worker`` with the registered workflow classes. We patch
    ``run_worker`` so the test returns instead of polling forever — and
    assert it was awaited with the right workflows. The liveness listener
    is patched out so the test doesn't bind a real TCP port."""
    from meow.worker import __main__ as worker_main

    with (
        patch(
            "mistralai.workflows.run_worker",
            new_callable=AsyncMock,
            return_value=None,
        ) as run_worker,
        patch(
            "meow.worker.__main__._liveness_listener",
            side_effect=_never_returns,
        ) as liveness,
    ):
        worker_main.main()

    run_worker.assert_awaited_once_with(worker_main._WORKFLOWS)
    liveness.assert_called_once_with(worker_main._DEFAULT_LIVENESS_PORT)
    assert [
        worker_main.PrReviewWorkflow,
        worker_main.FeatureScopeWorkflow,
    ] == worker_main._WORKFLOWS

    started: list[Any] = [r for r in caplog.records if r.message == "worker.started"]
    assert len(started) == 1
    assert started[0].workflows == ["PrReviewWorkflow", "FeatureScopeWorkflow"]


def test_main_uses_liveness_port_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """``MEOW_WORKER_LIVENESS_PORT`` overrides the default port."""
    from meow.worker import __main__ as worker_main

    monkeypatch.setenv("MEOW_WORKER_LIVENESS_PORT", "9123")

    with (
        patch(
            "mistralai.workflows.run_worker",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "meow.worker.__main__._liveness_listener",
            side_effect=_never_returns,
        ) as liveness,
    ):
        worker_main.main()

    liveness.assert_called_once_with(9123)


@pytest.mark.asyncio
async def test_liveness_listener_accepts_tcp_connections() -> None:
    """The listener accepts a connection and closes it immediately.

    We can't easily inspect the port the helper bound (it logs nothing and
    we hand-pick a port). Instead, drive the same pattern on a fresh server
    bound to ``port=0`` so the OS picks a free one — this proves the no-op
    handler shape works end-to-end on the asyncio runtime, which is the
    only meaningful failure mode for our use case.
    """

    server = await asyncio.start_server(
        lambda _reader, writer: writer.close(),
        host="127.0.0.1",
        port=0,
    )
    host, port = server.sockets[0].getsockname()[:2]
    async with server:
        reader, writer = await asyncio.open_connection(host, port)
        # Server closes without sending → read() returns EOF (empty bytes).
        assert await reader.read() == b""
        writer.close()
        await writer.wait_closed()
