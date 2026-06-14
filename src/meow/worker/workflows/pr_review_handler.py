"""Workflow ``PrReviewWorkflow``.

Reviews a pull request end-to-end: fetch PR metadata + repo config,
build the review prompt, run vibe in a sandbox, post the result back as
a PR comment.

The workflow body is pure orchestration — every side-effectful step
lives in an activity. The activity modules and the input model all
transitively import I/O libraries (githubkit, koyeb) that the Temporal
sandbox refuses by default; they go through
``workflows.workflow.unsafe.imports_passed_through()``.

The input arrives as the JSON dump of an ``IssueCommentInput``
(produced by the receiver). We rebuild the typed model via
``model_validate`` — pydantic validation is pure-Python and safe
inside the deterministic sandbox; only the from_* factory paths,
which we don't touch here, would pull in githubkit at runtime.
"""

import mistralai.workflows as workflows

from meow.common.logging import get_logger
from meow.common.workflows import PR_REVIEW_WORKFLOW

with workflows.workflow.unsafe.imports_passed_through():
    from meow.common.webhooks_inputs.issue_comment import IssueCommentInput
    from meow.worker.activities.fetch_meow_config import fetch_meow_config
    from meow.worker.activities.fetch_pr_context import fetch_pr_context
    from meow.worker.activities.post_pr_comment import post_pr_comment
    from meow.worker.activities.run_vibe import run_pr_review_vibe
    from meow.worker.models import PrSandboxSpec
    from meow.worker.vibe_tasks.tasks.pr_review import make_pr_review_task

logger = get_logger("worker")


@workflows.workflow.define(
    name=PR_REVIEW_WORKFLOW,
    workflow_display_name="PR Review Handler",
    workflow_description="Reviews a GitHub pull request via the vibe sandbox.",
)
class PrReviewWorkflow:
    @workflows.workflow.entrypoint
    async def run(self, input: dict) -> str | None:
        webhook = IssueCommentInput.model_validate(input)
        # GitHub treats PRs as issues for the comments namespace, so the
        # webhook payload calls the PR number `issue_number`.
        pr_number = webhook.issue_number

        logger.info(
            "workflow.pr_review.started",
            extra={"repo": webhook.repo_full_name, "pr": pr_number},
        )

        pr_context = await fetch_pr_context(
            webhook.installation_id, webhook.repo_full_name, pr_number
        )
        meow_config = await fetch_meow_config(
            webhook.installation_id, webhook.repo_full_name, pr_context.base_sha
        )

        sandbox_spec = PrSandboxSpec(
            installation_id=webhook.installation_id,
            repo_full_name=webhook.repo_full_name,
            pr_number=pr_number,
            base_sha=pr_context.base_sha,
            head_sha=pr_context.head_sha,
        )
        task = make_pr_review_task(
            pr_context,
            meow_config,
            repo_full_name=webhook.repo_full_name,
            pr_number=pr_number,
        )

        result = await run_pr_review_vibe(task, sandbox_spec)
        url = await post_pr_comment(
            webhook.installation_id, webhook.repo_full_name, pr_number, result
        )

        logger.info(
            "workflow.pr_review.done",
            extra={
                "repo": webhook.repo_full_name,
                "pr": pr_number,
                "comment_url": url,
                "terminated_early": result.terminated_early,
            },
        )
        return url
