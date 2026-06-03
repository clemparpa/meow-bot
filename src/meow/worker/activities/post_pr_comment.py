"""Activity ``post_pr_comment`` (story S10).

Publishes a review report as a PR comment via githubkit. Auth is
delegated to ``github_installation_auth``, which mints an
``issues:write`` installation token for the call.

Note on the endpoint: GitHub treats PR comments as *issue* comments
(``POST /repos/{owner}/{repo}/issues/{number}/comments``); the
``pull_requests`` REST namespace is reserved for in-line review-comments,
which v0.1.0 does not produce.
"""

from __future__ import annotations

from datetime import timedelta

import mistralai.workflows as workflows

from meow.common.github.auth import github_installation_auth
from meow.common.logging import get_logger
from meow.worker.models import ReviewReport

logger = get_logger("worker")

# Fixed header so reviewers can recognise the bot's comments at a glance
# and so future versions can grep them out of a PR (e.g. to edit-in-place
# instead of stacking).
_HEADER = "🐱 **meow-bot review** — [docs](https://github.com/clemparpa/meow-bot)"


def _scrub_secrets(body: str) -> str:
    """Placeholder for v0.1.0; real sanitisation lands in v0.2+ (spec §11.2).

    Kept as a named seam so the call site doesn't have to change later.
    """
    return body


# 15s is enough for a slow POST; longer is a GitHub outage we'd rather
# surface as a failure than block on. Idempotency at the delivery level is
# already enforced upstream by S6, so a retry storm here is harmless.
@workflows.activity(start_to_close_timeout=timedelta(seconds=15))
async def post_pr_comment(
    installation_id: int,
    repo_full_name: str,
    pr_number: int,
    report: ReviewReport,
) -> str:
    if repo_full_name.count("/") != 1:
        raise ValueError(f"repo_full_name must be 'owner/repo', got {repo_full_name!r}")
    owner, repo = repo_full_name.split("/", 1)

    scrubbed = _scrub_secrets(report.body)
    body = f"{_HEADER}\n\n---\n\n{scrubbed}"

    async with github_installation_auth(installation_id, permissions={"issues": "write"}) as gh:
        resp = await gh.client.rest.issues.async_create_comment(owner, repo, pr_number, body=body)
        comment = resp.parsed_data

        logger.info(
            "activity.post_pr_comment.done",
            extra={
                "repo": repo_full_name,
                "pr": pr_number,
                "comment_id": comment.id,
                "body_bytes": len(body),
            },
        )
        return comment.html_url
