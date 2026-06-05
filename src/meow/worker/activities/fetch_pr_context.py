"""Activity ``fetch_pr_context``.

Fetches PR metadata needed by the review pipeline (title, body, base/head
SHAs). Auth is delegated to ``github_installation_auth``, which mints a
``contents:read`` installation token for the call.
"""

from __future__ import annotations

from datetime import timedelta

import mistralai.workflows as workflows
from githubkit.rest import PullRequest

from meow.common.github.auth import github_installation_auth
from meow.common.logging import get_logger
from meow.worker.models.pr_context import PrContext

logger = get_logger("worker")


@workflows.activity(start_to_close_timeout=timedelta(seconds=30))
async def fetch_pr_context(
    installation_id: int,
    repo_full_name: str,
    pr_number: int,
) -> PrContext:
    owner, repo = repo_full_name.split("/", maxsplit=1)

    async with github_installation_auth(
        installation_id,
        permissions={"contents": "read"},
        repositories=[repo_full_name],
    ) as gh:
        pr: PullRequest = (
            await gh.client.rest.pulls.async_get(
                owner=owner,
                repo=repo,
                pull_number=pr_number,
            )
        ).parsed_data

    logger.info(
        "activity.fetch_pr_context.done",
        extra={"repo": repo_full_name, "pr": pr_number, "head_sha": pr.head.sha},
    )
    return PrContext.from_pr(pr)
