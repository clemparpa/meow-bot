"""Activity ``open_pull_request``.

Opens (or, on re-run, updates) the draft PR for an implementation run. The
feature branch has already been created by ``commit_changeset`` (worker-side,
via the Git Data API); this activity just creates the PR pointing at it, linking
the issue via a ``Closes #N`` line so merging closes the issue. Auth is delegated
to ``github_installation_auth`` with ``pull_requests:write``.

Idempotency: a deterministic one-branch-per-issue scheme means a re-trigger
force-updates the same head, so a PR may already exist. GitHub answers the
duplicate ``create`` with a 422; we then look the open PR up by head, refresh
its body, and return its URL — the force-update already refreshed the diff.
"""

from __future__ import annotations

from datetime import timedelta

import mistralai.workflows as workflows
from githubkit.exception import RequestFailed

from meow.common.github.auth import github_installation_auth
from meow.common.logging import get_logger
from meow.worker.activities._comment_body import build_comment_body
from meow.worker.models import VibeResult

logger = get_logger("worker")

# Distinct header so an implementation PR reads differently from a review/scope
# comment and future versions can grep these out.
_HEADER = "🐱 **meow-bot implement** — [docs](https://github.com/clemparpa/meow-bot)"

_TERMINATED_BANNER = "⚠️ **Implementation terminated early.**"


def _pr_body(result: VibeResult, issue_number: int) -> str:
    """Header + the agent's PR description + a ``Closes #N`` link."""
    description = build_comment_body(result, banner=_TERMINATED_BANNER)
    return f"{_HEADER}\n\n---\n\n{description}\n\nCloses #{issue_number}"


@workflows.activity(start_to_close_timeout=timedelta(seconds=30))
async def open_pull_request(
    installation_id: int,
    repo_full_name: str,
    head_branch: str,
    base_branch: str,
    issue_number: int,
    title: str,
    result: VibeResult,
    draft: bool = True,
) -> str:
    if repo_full_name.count("/") != 1:
        raise ValueError(f"repo_full_name must be 'owner/repo', got {repo_full_name!r}")
    owner, repo = repo_full_name.split("/", 1)

    body = _pr_body(result, issue_number)

    async with github_installation_auth(
        installation_id,
        permissions={"pull_requests": "write"},
        repositories=[repo_full_name],
    ) as gh:
        try:
            resp = await gh.client.rest.pulls.async_create(
                owner,
                repo,
                title=title,
                head=head_branch,
                base=base_branch,
                body=body,
                draft=draft,
            )
        except RequestFailed as e:
            if e.response.status_code != 422:
                raise
            # A PR for this head already exists (re-run force-pushed onto it).
            # Find it, refresh its body, and return its URL — the diff is
            # already up to date thanks to the force-push.
            existing = await gh.client.rest.pulls.async_list(
                owner, repo, head=f"{owner}:{head_branch}", state="open"
            )
            prs = existing.parsed_data
            if not prs:
                raise
            pr = prs[0]
            updated = await gh.client.rest.pulls.async_update(owner, repo, pr.number, body=body)
            url = updated.parsed_data.html_url
            logger.info(
                "activity.open_pull_request.updated",
                extra={"repo": repo_full_name, "pr": pr.number, "head": head_branch},
            )
            return url

        pr = resp.parsed_data
        logger.info(
            "activity.open_pull_request.created",
            extra={
                "repo": repo_full_name,
                "pr": pr.number,
                "head": head_branch,
                "draft": draft,
                "terminated_early": result.terminated_early,
            },
        )
        return pr.html_url
