"""Activity ``post_issue_comment``.

Publishes a vibe result as a comment on a GitHub *issue* (the feature-scoping
report) via githubkit. Auth is delegated to ``github_installation_auth``,
which mints an installation token scoped to ``issues:write`` for the call.

Unlike ``post_pr_comment``, the target is a real issue, not a PR riding the
shared issue-comments namespace — so ``issues:write`` alone is sufficient and
``pull_requests:write`` is not requested. Body rendering is shared via
``_comment_body``; only the header and terminated-early banner differ.

The 65535-char GitHub comment limit is not enforced here — the activity will
surface a 422 from the API if vibe ever produces an over-long body.
"""

from __future__ import annotations

from datetime import timedelta

import mistralai.workflows as workflows

from meow.common.github.auth import github_installation_auth
from meow.common.logging import get_logger
from meow.worker.activities._comment_body import build_comment_body
from meow.worker.models import VibeResult

logger = get_logger("worker")

# Distinct header so the scoping report reads differently from a PR review and
# future versions can grep these out of an issue thread.
_HEADER = "🔍 **meow-bot scope** — [docs](https://github.com/clemparpa/meow-bot)"

_TERMINATED_BANNER = "⚠️ **Scoping terminated early.**"


@workflows.activity(start_to_close_timeout=timedelta(seconds=15))
async def post_issue_comment(
    installation_id: int,
    repo_full_name: str,
    issue_number: int,
    result: VibeResult,
) -> str:
    if repo_full_name.count("/") != 1:
        raise ValueError(f"repo_full_name must be 'owner/repo', got {repo_full_name!r}")
    owner, repo = repo_full_name.split("/", 1)

    body = f"{_HEADER}\n\n---\n\n{build_comment_body(result, banner=_TERMINATED_BANNER)}"

    async with github_installation_auth(
        installation_id,
        permissions={"issues": "write"},
        repositories=[repo_full_name],
    ) as gh:
        resp = await gh.client.rest.issues.async_create_comment(
            owner, repo, issue_number, body=body
        )
        comment = resp.parsed_data

        logger.info(
            "activity.post_issue_comment.done",
            extra={
                "repo": repo_full_name,
                "issue": issue_number,
                "comment_id": comment.id,
                "body_bytes": len(body),
                "terminated_early": result.terminated_early,
            },
        )
        return comment.html_url
