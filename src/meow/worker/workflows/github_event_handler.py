"""Top-level GitHub event router workflow.

Receives a small, flat payload from the receiver and dispatches to the
right activity chain based on the intent detected in the comment body.

v0.1.0 phase C: only ``MENTION_REVIEW`` is recognised, which fans out to
the chain ``fetch_pr_context`` → ``run_review_in_sandbox`` → ``post_pr_comment``.

Sandbox-clean by construction: this module imports nothing that the
Temporal determinism sandbox forbids. ``githubkit`` parsing happens in
the receiver (which is not a workflow) and in activities (which run
outside the sandbox); the workflow itself only reads primitive
``str``/``bool`` fields plus the raw ``payload`` dict — the latter is
parsed via ``_extract_pr_coords`` (pure dict access, no I/O).
"""

from __future__ import annotations

from typing import Any

import mistralai.workflows as workflows
from pydantic import BaseModel

from meow.common.logging import get_logger
from meow.worker.intent import detect_intent

# The three activities transitively import githubkit → httpx → urllib.request,
# which the Temporal sandbox refuses to validate at workflow registration time.
# ``imports_passed_through`` tells the sandbox these modules are only used
# from activities (which run outside the sandbox) — the workflow itself
# never executes their code, it just dispatches. ``parse_meow_yml`` is pure
# but pulls in pyyaml, which transitively touches I/O modules — same fix.
with workflows.workflow.unsafe.imports_passed_through():
    from meow.common.meow_yml import parse_meow_yml
    from meow.worker.activities.fetch_pr_context import fetch_pr_context
    from meow.worker.activities.post_pr_comment import post_pr_comment
    from meow.worker.activities.run_review_in_sandbox import run_review_in_sandbox

logger = get_logger("worker")


def _extract_pr_coords(payload: dict[str, Any]) -> tuple[int, str, int]:
    """Pull installation_id, repo_full_name, pr_number from a webhook payload.

    All three keys are guaranteed for ``issue_comment`` events from a GitHub
    App installation — the receiver already filters non-PR comments via
    ``is_pr``, and GitHub Apps always include ``installation`` and
    ``repository`` blocks. A ``KeyError`` here is a contract violation worth
    failing loudly on, not silencing.
    """
    return (
        int(payload["installation"]["id"]),
        str(payload["repository"]["full_name"]),
        int(payload["issue"]["number"]),
    )


class GithubEventInput(BaseModel):
    """Payload passed by the receiver to a ``GithubEventHandler`` execution.

    The receiver pre-parses the webhook (typed via ``githubkit``) and
    extracts only the primitives the workflow needs to decide what to
    do. The full ``payload`` dict is also forwarded so future activities
    can rebuild the typed model when they actually need the fields.
    """

    event: str
    delivery: str
    bot_login: str | None
    comment_body: str | None
    is_pr: bool
    payload: dict[str, Any]


@workflows.workflow.define(
    name="GithubEventHandler",
    workflow_display_name="GitHub Event Handler",
    workflow_description="Routes incoming GitHub webhooks to intent handlers.",
)
class GithubEventHandler:
    @workflows.workflow.entrypoint
    async def run(self, input: GithubEventInput) -> None:
        if input.event != "issue_comment":
            # Receiver should have filtered this out — log and exit cleanly
            # rather than crashing into the workflow retry loop.
            logger.warning(
                "workflow.github_event.unexpected_event",
                extra={"gh_event": input.event, "delivery": input.delivery},
            )
            return None

        if not input.bot_login:
            logger.warning(
                "workflow.github_event.no_bot_login",
                extra={"delivery": input.delivery},
            )
            return None

        intent = detect_intent(
            input.comment_body,
            is_pr=input.is_pr,
            bot_login=input.bot_login,
        )
        if intent is None:
            logger.info(
                "workflow.github_event.no_intent",
                extra={"delivery": input.delivery},
            )
            return None

        logger.info(
            "workflow.intent.detected",
            extra={"intent": intent.value, "delivery": input.delivery},
        )

        installation_id, repo_full_name, pr_number = _extract_pr_coords(input.payload)
        owner, repo = repo_full_name.split("/", 1)

        ctx = await fetch_pr_context(installation_id, owner, repo, pr_number)
        config = parse_meow_yml(ctx.meow_yml_raw)
        report = await run_review_in_sandbox(ctx, config)
        comment_url = await post_pr_comment(installation_id, repo_full_name, pr_number, report)

        logger.info(
            "workflow.review_posted",
            extra={
                "delivery": input.delivery,
                "comment_url": comment_url,
                "terminated_early": report.terminated_early,
            },
        )
        return None
