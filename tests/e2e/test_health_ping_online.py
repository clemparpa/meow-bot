"""Online smoke test for the Mistral Workflows pipe.

Spins up a real worker against `api.mistral.ai`, registers a trivial
`HealthPing` workflow + activity, triggers an execution via the SDK
(same code path as the receiver), and waits for completion. Skipped
unless both `MEOW_E2E_MISTRAL_API_KEY` and `MEOW_E2E_ENABLED=1` are
set, so the suite is a no-op locally and on developer pre-push hooks.

Why a custom env var instead of reading `MISTRAL_API_KEY` directly:
`tests/conftest.py` force-overwrites that var with a fake value at
module load (needed so the receiver's Settings model doesn't crash
during collection of the other tests). Crucially, `pydantic-settings`
reads the env *once* at module import time, so the SDK's
`config.common.mistral_api_key` is already frozen with the fake value
by the time this test runs. Rebinding `os.environ` would be a no-op
— instead we mutate `config.common.mistral_api_key` directly, plus
the two siblings that `inject_defaults` copied it into.

Goal: catch breakage in the SDK / control plane / worker plumbing
*before* the review pipeline depends on it (S17 dogfood). Does not
exercise `PrReviewWorkflow` — that's covered offline by
`tests/integration/workflows/test_pr_review.py`.
"""

from __future__ import annotations

import asyncio
import contextlib
import os

import httpx
import mistralai.workflows as workflows
import pytest
from mistralai.client import Mistral
from mistralai.workflows.core.config.config import config as mistral_config
from mistralai.workflows.testing.workflow_helpers import (
    poll_worker_activity_status,
    wait_for_workflow_completion,
)
from pydantic import SecretStr

from tests.e2e.workflows.health_ping import HEALTH_PING_WORKFLOW, HealthPingWorkflow

pytestmark = pytest.mark.skipif(
    not os.getenv("MEOW_E2E_MISTRAL_API_KEY") or not os.getenv("MEOW_E2E_ENABLED"),
    reason="online e2e test requires MEOW_E2E_MISTRAL_API_KEY and MEOW_E2E_ENABLED=1",
)

# How long we wait for the worker to publish its workflow definitions
# to the control plane before triggering the execution. Empirical —
# bumped if flaky.
_WORKER_REGISTRATION_TIMEOUT_SECONDS = 30

# Per-execution budget (start → COMPLETED). 30s covers a cold control
# plane dispatch + the trivial echo activity; well under the 60s job
# timeout in `e2e.yml`.
_EXECUTION_TIMEOUT_SECONDS = 30


@pytest.mark.asyncio
async def test_health_ping_online() -> None:
    # The SDK's config is frozen with the fake key pinned by
    # `tests/conftest.py`. `AppConfig.inject_defaults` propagates
    # `common.mistral_api_key` into `temporal.api_key` and the agent
    # client at construction time only, so we mirror the three writes
    # here. `run_worker` saves & restores `config` so the mutation
    # stays scoped to this test.
    # `.strip()` guards against a trailing newline that GitHub Secrets
    # often appends when the value is pasted via the web UI — invisible
    # locally but enough to make `Authorization: Bearer <key>\n` 401.
    api_key = os.environ["MEOW_E2E_MISTRAL_API_KEY"].strip()
    secret = SecretStr(api_key)
    mistral_config.common.mistral_api_key = secret
    mistral_config.temporal.api_key = secret
    mistral_config.worker.agent.mistral_client_api_key = secret

    # Reuse the deployment_name already loaded by `tests/conftest.py`
    # (`"test-deployment"`). Concurrent CI runs would share the same
    # task queue, but with `allow_multiple_workers=True` (SDK default)
    # and a stateless HealthPing activity, cross-talk is harmless.
    deployment_name = mistral_config.worker.deployment_name

    worker_task = await workflows.run_worker([HealthPingWorkflow], detach=True)
    try:
        async with httpx.AsyncClient(
            base_url="https://api.mistral.ai",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(_EXECUTION_TIMEOUT_SECONDS + 5),
        ) as http_client:
            # Wait for the worker to publish the workflow definition to the
            # control plane — execution would otherwise race a not-yet-registered
            # workflow.
            await poll_worker_activity_status(
                client=http_client,
                expected_active_status=True,
                workflow_identifier=HEALTH_PING_WORKFLOW,
                timeout_seconds=_WORKER_REGISTRATION_TIMEOUT_SECONDS,
            )

            # Use the production SDK's `execute_workflow` (same code path the
            # receiver uses) rather than the test helper, whose `/execute`
            # endpoint targets a Mistral *test server*, not `api.mistral.ai`.
            mistral_client = Mistral(api_key=api_key)
            # Let the SDK generate a unique execution_id — passing a fixed
            # one would clash on a second run within the same deployment.
            execution = mistral_client.workflows.execute_workflow(
                workflow_identifier=HEALTH_PING_WORKFLOW,
                deployment_name=deployment_name,
                input={"input": {"message": "hello"}},
            )

            status = await wait_for_workflow_completion(
                client=http_client,
                execution_id=execution.execution_id,
                max_retries=_EXECUTION_TIMEOUT_SECONDS,
                delay=1.0,
            )
            assert status["status"] == "COMPLETED"
            assert status["result"] == {"result": "echo: hello"}
    finally:
        if worker_task is not None:
            worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker_task
