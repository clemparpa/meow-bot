"""Workflow ``FeatureScopeWorkflow``.

Scopes a feature request filed as a GitHub issue: clone the default branch,
let the agent explore the code, post a feasibility/scoping report back as an
issue comment.

The workflow body is pure orchestration — every side-effectful step lives in
an activity. The activity modules and the input model transitively import I/O
libraries (githubkit, koyeb) that the Temporal sandbox refuses by default;
they go through ``workflows.workflow.unsafe.imports_passed_through()``.

The input arrives as the JSON dump of an ``IssueEventInput`` (produced by the
receiver). We rebuild the typed model via ``model_validate`` — pydantic
validation is pure-Python and safe inside the deterministic sandbox; only the
from_* factory paths, which we don't touch here, would pull in githubkit.

Unlike ``PrReviewWorkflow`` there is no ``fetch_*_context`` activity: the
``issues`` payload already carries the issue title/body and the repo's default
branch, so the receiver hands them straight through on the input model.
"""

import mistralai.workflows as workflows

from meow.common.logging import get_logger
from meow.common.workflows import FEATURE_SCOPE_WORKFLOW

with workflows.workflow.unsafe.imports_passed_through():
    from meow.common.webhooks_inputs.issues import IssueEventInput
    from meow.worker.activities.fetch_meow_config import fetch_meow_config
    from meow.worker.activities.post_issue_comment import post_issue_comment
    from meow.worker.activities.run_vibe import run_feature_scope_vibe
    from meow.worker.models import CloneSandboxSpec
    from meow.worker.vibe_tasks.tasks.feature_scope import make_feature_scope_task

logger = get_logger("worker")


@workflows.workflow.define(
    name=FEATURE_SCOPE_WORKFLOW,
    workflow_display_name="Feature Scope Handler",
    workflow_description="Scopes a GitHub feature issue via the vibe sandbox.",
)
class FeatureScopeWorkflow:
    @workflows.workflow.entrypoint
    async def run(self, input: dict) -> str | None:
        webhook = IssueEventInput.model_validate(input)

        logger.info(
            "workflow.feature_scope.started",
            extra={"repo": webhook.repo_full_name, "issue": webhook.issue_number},
        )

        # Read the repo config off the default branch — same ref the agent
        # clones, so the budgets match the code under analysis.
        meow_config = await fetch_meow_config(
            webhook.installation_id, webhook.repo_full_name, webhook.default_branch
        )

        sandbox_spec = CloneSandboxSpec(
            installation_id=webhook.installation_id,
            repo_full_name=webhook.repo_full_name,
            ref=webhook.default_branch,
        )
        task = make_feature_scope_task(webhook, meow_config)

        result = await run_feature_scope_vibe(task, sandbox_spec)
        url = await post_issue_comment(
            webhook.installation_id, webhook.repo_full_name, webhook.issue_number, result
        )

        logger.info(
            "workflow.feature_scope.done",
            extra={
                "repo": webhook.repo_full_name,
                "issue": webhook.issue_number,
                "comment_url": url,
                "terminated_early": result.terminated_early,
            },
        )
        return url
