"""Activity ``post_pr_comment``.

Publishes a vibe result as a PR comment via githubkit. Auth is delegated
to ``github_installation_auth``, which mints an installation token scoped
to ``issues:write`` + ``pull_requests:write`` for the call.

Note on the endpoint: GitHub treats PR comments as *issue* comments
(``POST /repos/{owner}/{repo}/issues/{number}/comments``); the
``pull_requests`` REST namespace is reserved for in-line review-comments,
which v0.1.0 does not produce. Even so, commenting on a *pull request* via
that shared endpoint requires the ``pull_requests:write`` permission (GitHub
checks the underlying resource type) — ``issues:write`` alone yields a 403.
Both scopes are granted by the app manifest, so we request both.

The 65535-char GitHub comment limit is not enforced here — the activity
will surface a 422 from the API if vibe ever produces an over-long body.
"""

from __future__ import annotations

from datetime import timedelta

import mistralai.workflows as workflows

from meow.common.github.auth import github_installation_auth
from meow.common.logging import get_logger
from meow.worker.models import VibeResult

logger = get_logger("worker")

# Fixed header so reviewers can recognise the bot's comments at a glance
# and so future versions can grep them out of a PR (e.g. to edit-in-place
# instead of stacking).
_HEADER = "🐱 **meow-bot review** — [docs](https://github.com/clemparpa/meow-bot)"

_TERMINATED_BANNER = "⚠️ **Review terminated early.**"
_NO_OUTPUT_NOTE = "_No partial output was produced._"


def _scrub_secrets(body: str) -> str:
    """Placeholder for v0.1.0; real sanitisation lands in v0.2+ (spec §11.2).

    Kept as a named seam so the call site doesn't have to change later.
    """
    return body


def _build_body(result: VibeResult) -> str:
    """Render the markdown body for a vibe result.

    Three cases:
    - Clean run with output: post the body as-is.
    - Terminated early with a partial body: prepend a banner (+ optional
      stop_reason) above the partial output, separated by an HR.
    - Terminated early with no body: just the banner + stop_reason; no
      partial output to show.
    """
    if not result.terminated_early and result.body is not None:
        return _scrub_secrets(result.body)

    parts = [_TERMINATED_BANNER]
    if result.stop_reason:
        parts.append(f"Reason: {_scrub_secrets(result.stop_reason)}")
    if result.body is not None:
        parts.append("---")
        parts.append(_scrub_secrets(result.body))
    else:
        parts.append(_NO_OUTPUT_NOTE)
    return "\n\n".join(parts)


# 15s is enough for a slow POST; longer is a GitHub outage we'd rather
# surface as a failure than block on. Idempotency at the delivery level is
# already enforced upstream by S6, so a retry storm here is harmless.
@workflows.activity(start_to_close_timeout=timedelta(seconds=15))
async def post_pr_comment(
    installation_id: int,
    repo_full_name: str,
    pr_number: int,
    result: VibeResult,
) -> str:
    if repo_full_name.count("/") != 1:
        raise ValueError(f"repo_full_name must be 'owner/repo', got {repo_full_name!r}")
    owner, repo = repo_full_name.split("/", 1)

    body = f"{_HEADER}\n\n---\n\n{_build_body(result)}"

    async with github_installation_auth(
        installation_id,
        permissions={"issues": "write", "pull_requests": "write"},
        repositories=[repo_full_name],
    ) as gh:
        resp = await gh.client.rest.issues.async_create_comment(owner, repo, pr_number, body=body)
        comment = resp.parsed_data

        logger.info(
            "activity.post_pr_comment.done",
            extra={
                "repo": repo_full_name,
                "pr": pr_number,
                "comment_id": comment.id,
                "body_bytes": len(body),
                "terminated_early": result.terminated_early,
            },
        )
        return comment.html_url
