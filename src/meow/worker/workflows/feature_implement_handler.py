"""Workflow ``FeatureImplementWorkflow``.

Implements a feature filed as a GitHub issue: clone the default branch
read-only, let the agent edit the working tree, extract its changeset, then
commit it worker-side (Git Data API) onto a feature branch and open a draft PR
linked to the issue. When the agent produces no changes (e.g. it judged the
feature infeasible, ran out of budget, or the diff was too large to ship), fall
back to posting an explanatory issue comment instead of opening an empty PR.

The agent never holds a write token and runs no git: every git write is a
separate, retryable worker activity (``commit_changeset``, ``open_pull_request``)
that operates on the changeset, not the sandbox.

The workflow body is pure orchestration — every side-effectful step lives in an
activity. The activity modules and the input model transitively import I/O
libraries (githubkit, koyeb) that the Temporal sandbox refuses by default; they
go through ``workflows.workflow.unsafe.imports_passed_through()``.

The input arrives as the JSON dump of an ``IssueEventInput`` (produced by the
receiver). We rebuild the typed model via ``model_validate`` — pydantic
validation is pure-Python and safe inside the deterministic sandbox; only the
from_* factory paths, which we don't touch here, would pull in githubkit.

Like ``FeatureScopeWorkflow`` and unlike ``PrReviewWorkflow`` there is no
``fetch_*_context`` activity: the ``issues`` payload already carries the issue
title/body and the repo's default branch.
"""

import mistralai.workflows as workflows

from meow.common.logging import get_logger
from meow.common.workflows import FEATURE_IMPLEMENT_WORKFLOW

with workflows.workflow.unsafe.imports_passed_through():
    from meow.common.webhooks_inputs.issues import IssueEventInput
    from meow.worker.activities.commit_changeset import commit_changeset
    from meow.worker.activities.fetch_meow_config import fetch_meow_config
    from meow.worker.activities.open_pull_request import open_pull_request
    from meow.worker.activities.post_issue_comment import post_issue_comment
    from meow.worker.activities.run_vibe import run_feature_implement_vibe
    from meow.worker.models import CloneSandboxSpec
    from meow.worker.sandbox.builder import feature_branch_name
    from meow.worker.vibe_tasks.tasks.feature_implement import make_feature_implement_task

logger = get_logger("worker")

# Issue-comment header/banner for the zero-diff fallback (no PR opened).
_NO_CHANGES_HEADER = "🐱 **meow-bot implement** — [docs](https://github.com/clemparpa/meow-bot)"
_NO_CHANGES_BANNER = "ℹ️ **No changes were produced — no pull request opened.**"


@workflows.workflow.define(
    name=FEATURE_IMPLEMENT_WORKFLOW,
    workflow_display_name="Feature Implement Handler",
    workflow_description="Implements a GitHub feature issue and opens a PR via the vibe sandbox.",
)
class FeatureImplementWorkflow:
    @workflows.workflow.entrypoint
    async def run(self, input: dict) -> str | None:
        webhook = IssueEventInput.model_validate(input)

        logger.info(
            "workflow.feature_implement.started",
            extra={"repo": webhook.repo_full_name, "issue": webhook.issue_number},
        )

        # Read the repo config off the default branch — same ref the agent
        # works from, so the budgets match the code under change.
        meow_config = await fetch_meow_config(
            webhook.installation_id, webhook.repo_full_name, webhook.default_branch
        )

        sandbox_spec = CloneSandboxSpec(
            installation_id=webhook.installation_id,
            repo_full_name=webhook.repo_full_name,
            ref=webhook.default_branch,
        )
        task = make_feature_implement_task(webhook, meow_config)

        result = await run_feature_implement_vibe(task, sandbox_spec)

        if not result.changeset.is_empty:
            branch = feature_branch_name(webhook.issue_number)
            await commit_changeset(
                webhook.installation_id,
                webhook.repo_full_name,
                webhook.default_branch,
                branch,
                f"meow: implement #{webhook.issue_number} — {webhook.issue_title}",
                result.changeset,
            )
            url = await open_pull_request(
                webhook.installation_id,
                webhook.repo_full_name,
                head_branch=branch,
                base_branch=webhook.default_branch,
                issue_number=webhook.issue_number,
                title=webhook.issue_title,
                result=result.vibe,
            )
            logger.info(
                "workflow.feature_implement.pr_opened",
                extra={
                    "repo": webhook.repo_full_name,
                    "issue": webhook.issue_number,
                    "branch": branch,
                    "pr_url": url,
                    "files": len(result.changeset.files),
                    "terminated_early": result.vibe.terminated_early,
                },
            )
            return url

        # No changes (infeasible / terminated early / too large): post a comment.
        url = await post_issue_comment(
            webhook.installation_id,
            webhook.repo_full_name,
            webhook.issue_number,
            result.vibe,
            header=_NO_CHANGES_HEADER,
            terminated_banner=_NO_CHANGES_BANNER,
        )
        logger.info(
            "workflow.feature_implement.no_changes",
            extra={
                "repo": webhook.repo_full_name,
                "issue": webhook.issue_number,
                "comment_url": url,
            },
        )
        return url
