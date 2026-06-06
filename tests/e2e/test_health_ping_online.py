"""Online smoke test for the Mistral Workflows pipe.

Spins up a real worker against `api.mistral.ai`, registers a trivial
`HealthPing` workflow + activity, triggers an execution via the SDK,
and waits for completion under a 60s budget. Skipped unless both
`MISTRAL_API_KEY` and `MEOW_E2E_ENABLED=1` are set, so the suite is a
no-op locally and on developer pre-push hooks.

Goal: catch breakage in the SDK / control plane / worker plumbing
*before* the review pipeline depends on it (S17 dogfood). Does not
exercise `PrReviewWorkflow` — that's covered offline by
`tests/integration/workflows/test_pr_review.py`.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import uuid

import httpx
import mistralai.workflows as workflows
import pytest
from mistralai.workflows.testing import execute_workflow_and_wait

from tests.e2e.workflows.health_ping import HEALTH_PING_WORKFLOW, HealthPingWorkflow

pytestmark = pytest.mark.skipif(
    not os.getenv("MISTRAL_API_KEY") or not os.getenv("MEOW_E2E_ENABLED"),
    reason="online e2e test requires MISTRAL_API_KEY and MEOW_E2E_ENABLED=1",
)

# How long we give the worker to register itself with the control plane
# before triggering the execution. Empirical — bumped if flaky.
_WORKER_BOOTSTRAP_SECONDS = 5

# Per-execution budget (start → COMPLETED). 30s covers a cold control
# plane dispatch + the trivial echo activity; well under the 60s job
# timeout in `e2e.yml`.
_EXECUTION_TIMEOUT_SECONDS = 30


@pytest.mark.asyncio
async def test_health_ping_online() -> None:
    # Per-run task queue so concurrent CI jobs don't collide on the
    # control plane's queue dispatch.
    deployment_name = f"meow-bot-e2e-{uuid.uuid4().hex[:8]}"
    os.environ["DEPLOYMENT_NAME"] = deployment_name

    worker_task = await workflows.run_worker([HealthPingWorkflow], detach=True)
    try:
        await asyncio.sleep(_WORKER_BOOTSTRAP_SECONDS)

        api_key = os.environ["MISTRAL_API_KEY"]
        async with httpx.AsyncClient(
            base_url="https://api.mistral.ai",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(_EXECUTION_TIMEOUT_SECONDS + 5),
        ) as client:
            status = await execute_workflow_and_wait(
                client=client,
                workflow_name=HEALTH_PING_WORKFLOW,
                input_data={"input": {"message": "hello"}},
                task_queue=deployment_name,
                timeout_seconds=_EXECUTION_TIMEOUT_SECONDS,
            )
            assert status["status"] == "COMPLETED"
            assert status["result"] == {"result": "echo: hello"}
    finally:
        if worker_task is not None:
            worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker_task
