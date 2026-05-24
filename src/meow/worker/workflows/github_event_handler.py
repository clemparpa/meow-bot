"""Top-level GitHub event router workflow.

Receives a small, flat payload from the receiver and dispatches to the
right activity chain based on the intent detected in the comment body.

v0.1.0 phase C: only ``MENTION_REVIEW`` is recognised. The activity chain
(``fetch_pr_context`` → ``run_review_in_sandbox`` → ``post_pr_comment``)
lands in S8/S9/S10; until then the workflow just logs the match.

Sandbox-clean by construction: this module imports nothing that the
Temporal determinism sandbox forbids. ``githubkit`` parsing happens in
the receiver (which is not a workflow); the workflow only sees primitive
``str``/``bool`` fields it needs to decide the route. The full webhook
``payload`` is still forwarded as a ``dict`` for downstream activities
(S8+) — activities run outside the sandbox and may re-parse it via
``githubkit.webhooks.parse_obj`` freely.
"""

from __future__ import annotations

from typing import Any

import mistralai.workflows as workflows
from pydantic import BaseModel

from meow.common.logging import get_logger
from meow.worker.intent import detect_intent

logger = get_logger("worker")


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
        # TODO(S8/S9/S10): fetch_pr_context → run_review_in_sandbox → post_pr_comment
        return None
