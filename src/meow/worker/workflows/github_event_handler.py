"""Top-level GitHub event router workflow.

v0.1.0 phase B: no-op stub — receives the raw webhook payload from the
receiver, logs that it was picked up, and returns. Intent detection
(S7) and the activity chain (S8/S9/S10) wire in later in phase C.
"""

from __future__ import annotations

from typing import Any

import mistralai.workflows as workflows
from pydantic import BaseModel

from meow.common.logging import get_logger

logger = get_logger("worker")


class GithubEventInput(BaseModel):
    """Payload passed by the receiver to a ``GithubEventHandler`` execution."""

    event: str
    delivery: str
    payload: dict[str, Any]


@workflows.workflow.define(
    name="GithubEventHandler",
    workflow_display_name="GitHub Event Handler",
    workflow_description="Routes incoming GitHub webhooks to intent handlers.",
)
class GithubEventHandler:
    @workflows.workflow.entrypoint
    async def run(self, input: GithubEventInput) -> None:
        logger.info(
            "workflow.github_event.received",
            extra={"gh_event": input.event, "delivery": input.delivery},
        )
        return None
