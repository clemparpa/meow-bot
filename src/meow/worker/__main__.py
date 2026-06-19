"""Entry point for ``python -m meow.worker``.

Starts a Mistral Workflows worker (spec §7) that registers the workflows
listed in ``_WORKFLOWS`` and polls for tasks. Requires ``MISTRAL_API_KEY``
and ``DEPLOYMENT_NAME`` in the environment.

Also binds a no-op TCP listener on ``MEOW_WORKER_LIVENESS_PORT`` (default
8000) so PaaS hosts (Koyeb, Fly, Render…) can liveness-probe the container.
The worker itself is outbound-only — without the listener, the host has
nothing to probe and the service is reaped as unhealthy.
"""

from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

import mistralai.workflows as workflows

from meow.common.logging import get_logger
from meow.worker.workflows.feature_implement_handler import FeatureImplementWorkflow
from meow.worker.workflows.feature_scope_handler import FeatureScopeWorkflow
from meow.worker.workflows.pr_review_handler import PrReviewWorkflow

_WORKFLOWS = [PrReviewWorkflow, FeatureScopeWorkflow, FeatureImplementWorkflow]

# Matches the port Koyeb pre-configures on Worker services. Overridable so
# the same image runs on hosts that probe a different port.
_DEFAULT_LIVENESS_PORT = 8000

# The koyeb SDK runs every sync HTTP call through ``loop.run_in_executor(None,
# …)`` — i.e. the loop's *default* ThreadPoolExecutor, capped at
# ``min(32, cpu+4)`` (~5 on a 1-CPU instance) and shared process-wide. With
# many concurrent reviews, that bound could serialise sandbox launches. The
# polling exec path already keeps each thread-borrow to milliseconds; a larger
# dedicated pool removes the cap entirely as cheap insurance.
_KOYEB_EXECUTOR_WORKERS = 32


async def _liveness_listener(port: int) -> None:
    """Bind a no-op TCP listener so PaaS hosts can liveness-probe the worker.

    Accepts incoming connections and closes them immediately — purely to
    satisfy the platform's TCP probe. Not used for HTTP, so no payload is
    written.
    """
    server = await asyncio.start_server(
        lambda _reader, writer: writer.close(),
        host="0.0.0.0",
        port=port,
    )
    async with server:
        await server.serve_forever()


async def _run() -> None:
    # Size the default executor for concurrent koyeb SDK calls (see constant).
    asyncio.get_running_loop().set_default_executor(
        ThreadPoolExecutor(
            max_workers=_KOYEB_EXECUTOR_WORKERS,
            thread_name_prefix="koyeb-sdk",
        )
    )
    port = int(os.environ.get("MEOW_WORKER_LIVENESS_PORT", _DEFAULT_LIVENESS_PORT))
    worker_task = asyncio.create_task(workflows.run_worker(_WORKFLOWS))
    listener_task = asyncio.create_task(_liveness_listener(port))
    try:
        done, _ = await asyncio.wait(
            {worker_task, listener_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        # Re-raise the first exception (or surface a clean return) so the
        # process exits with the right status code. If the listener fails
        # to bind, we'd rather crash fast than run a worker the platform
        # will reap as unhealthy.
        for task in done:
            task.result()
    finally:
        worker_task.cancel()
        listener_task.cancel()
        await asyncio.gather(worker_task, listener_task, return_exceptions=True)


def main() -> None:
    logger = get_logger("worker")
    logger.info("worker.started", extra={"workflows": [w.__name__ for w in _WORKFLOWS]})
    asyncio.run(_run())


if __name__ == "__main__":
    main()
