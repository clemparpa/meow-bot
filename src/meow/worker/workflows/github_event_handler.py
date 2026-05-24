"""Top-level GitHub event router workflow.

Receives the webhook payload from the receiver, rebuilds the typed
githubkit model, and dispatches to the right activity chain based on the
intent detected in the comment body.

v0.1.0 phase C: only ``MENTION_REVIEW`` is recognised. The activity chain
(``fetch_pr_context`` → ``run_review_in_sandbox`` → ``post_pr_comment``)
lands in S8/S9/S10; until then the workflow just logs the match.

Sandbox notes — workflows run inside Temporal's determinism sandbox:

- ``githubkit`` transitively imports ``urllib.request`` (via httpx), which
  the sandbox blocks at import time. We use it strictly for in-memory
  Pydantic model rehydration — no network — so the imports are wrapped in
  ``workflow.unsafe.imports_passed_through()``. This is the use case the
  context manager is documented for ("third-party library performs side
  effects at import time"); runtime restrictions stay active.
- Settings()` (and any other ``os.environ`` read) cannot run here.
  Anything the workflow needs is injected by the receiver via the
  ``GithubEventInput`` payload — ``bot_login`` in particular.
"""

from __future__ import annotations

from typing import Any

import mistralai.workflows as workflows
from pydantic import BaseModel

from meow.common.logging import get_logger

# ruff: noqa: E402
with workflows.workflow.unsafe.imports_passed_through():
    from githubkit.webhooks import parse_obj
    from pydantic import ValidationError

    from meow.worker.intent import detect_intent

logger = get_logger("worker")


class GithubEventInput(BaseModel):
    """Payload passed by the receiver to a ``GithubEventHandler`` execution.

    ``bot_login`` is injected by the receiver (which reads ``Settings()``
    freely — it's not inside a sandbox). The workflow never touches the
    environment directly.
    """

    event: str
    delivery: str
    bot_login: str | None
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

        try:
            event = parse_obj("issue_comment", input.payload)
        except ValidationError:
            logger.warning(
                "workflow.github_event.malformed_payload",
                extra={"delivery": input.delivery},
            )
            return None

        if not input.bot_login:
            logger.warning(
                "workflow.github_event.no_bot_login",
                extra={"delivery": input.delivery},
            )
            return None

        intent = detect_intent(event, input.bot_login)
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
