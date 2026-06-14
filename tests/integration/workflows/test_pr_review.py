"""Offline workflow test for `PrReviewWorkflow`.

Runs the workflow against the in-memory Temporal environment provided by
`mistralai.workflows.testing` (autouse fixtures wired in this folder's
conftest), with the four production activities swapped for the fakes
under `tests/_fakes`. Verifies the orchestration: the workflow chains
all four activities and returns the URL produced by `post_pr_comment`.
"""

from __future__ import annotations

import pytest
from mistralai.workflows.testing import create_test_worker
from temporalio.testing import WorkflowEnvironment

from meow.common.webhooks_inputs.issue_comment import IssueCommentInput
from meow.common.workflows import PR_REVIEW_WORKFLOW
from meow.worker.workflows.pr_review_handler import PrReviewWorkflow
from tests._fakes import pr_review as fakes

# Activities scheduled from the workflow body land on the task queue
# returned by `config.get_effective_task_queue()`. The SDK's autouse
# `setup_test_config` fixture sets that config to `"test-task-queue"`,
# which is also `create_test_worker`'s default — keep them aligned so
# the worker actually picks up the activities.
_TASK_QUEUE = "test-task-queue"


@pytest.mark.asyncio
async def test_pr_review_workflow_chains_activities(temporal_env: WorkflowEnvironment) -> None:
    webhook = IssueCommentInput(
        action="created",
        installation_id=42,
        repo_full_name="owner/repo",
        issue_number=7,
        is_pr=True,
        locked=False,
        comment_body="@meow-bot review",
        sender_login="someone",
        delivery="test-delivery-uuid",
    )

    async with create_test_worker(
        env=temporal_env,
        workflows=[PrReviewWorkflow],
        activities=[
            fakes.fetch_pr_context,
            fakes.fetch_meow_config,
            fakes.run_pr_review_vibe,
            fakes.post_pr_comment,
        ],
        task_queue=_TASK_QUEUE,
    ):
        handle = await temporal_env.client.start_workflow(
            PR_REVIEW_WORKFLOW,
            {"input": webhook.model_dump(mode="json")},
            id=f"test-{webhook.delivery}",
            task_queue=_TASK_QUEUE,
        )
        # The SDK wraps the workflow return value in {"result": ...}
        # (symmetric to the {"input": ...} wrapping on the way in).
        result = await handle.result()

    assert result == {"result": fakes.FAKE_COMMENT_URL}
