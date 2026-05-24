"""FastAPI webhook receiver for meow-bot.

Implements the v0.1.0 receiver described in ``spec.md`` §6 and
``stories/v0.1.0.md`` (S6):

- ``GET /healthz`` for liveness probes.
- ``POST /gh/webhook`` validates the HMAC-SHA256 signature, filters
  self-deliveries and unhandled events, then starts a Mistral Workflows
  execution of ``GithubEventHandler`` (idempotent on
  ``X-GitHub-Delivery``) before returning ``{"queued": true, ...}``.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from githubkit.webhooks import parse
from mistralai.client import Mistral
from pydantic import ValidationError

from meow.common.config import Settings
from meow.common.github.webhook import InvalidSignature, verify_signature
from meow.common.logging import get_logger

settings = Settings()  # ty: ignore[missing-argument]
logger = get_logger("receiver")

# Module-level client: keeps the HTTP session warm between requests and
# avoids re-validating the API key on every webhook. Errors from
# `execute_workflow` (e.g. 401) surface at first webhook, not at boot.
_workflows_client: Mistral = Mistral(api_key=settings.mistral_api_key)

app = FastAPI(title="meow-receiver", version="0.1.0")

_HANDLED_EVENTS: frozenset[str] = frozenset({"issue_comment"})


def _bot_login() -> str | None:
    """Return the configured bot login, or ``None`` when unknown.

    Stub for v0.0.x — reads ``MEOW_BOT_LOGIN`` from the environment so
    the self-event filter can be exercised in tests. In v0.1.0 this will
    be replaced by a call to ``GET /app`` against the GitHub API.
    """
    value = os.environ.get("MEOW_BOT_LOGIN")
    return value or None


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/gh/webhook")
async def gh_webhook(request: Request) -> dict[str, Any]:
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")

    try:
        verify_signature(signature, body, settings.github_webhook_secret)
    except InvalidSignature:
        raise HTTPException(status_code=401, detail="invalid signature") from None

    event = request.headers.get("X-GitHub-Event")
    delivery = request.headers.get("X-GitHub-Delivery")

    if not event:
        logger.info("webhook.skipped", extra={"reason": "no-event", "delivery": delivery})
        return {"skipped": "event"}

    if event not in _HANDLED_EVENTS:
        logger.info(
            "webhook.skipped",
            extra={"reason": "event-not-handled", "delivery": delivery, "gh_event": event},
        )
        return {"skipped": "event"}

    try:
        parsed = parse(event, body)
    except ValidationError:
        logger.info(
            "webhook.malformed_payload",
            extra={"delivery": delivery, "gh_event": event},
        )
        raise HTTPException(status_code=400, detail="malformed webhook payload") from None

    sender_login = parsed.sender.login if parsed.sender else None
    bot = _bot_login()
    if bot and sender_login == bot:
        logger.info(
            "webhook.skipped",
            extra={"reason": "self", "delivery": delivery, "gh_event": event},
        )
        return {"skipped": "self"}

    execution = _workflows_client.workflows.execute_workflow(
        workflow_identifier="GithubEventHandler",
        execution_id=f"{event}-{delivery}",
        deployment_name=settings.deployment_name,
        input={
            "event": event,
            "delivery": delivery,
            "payload": parsed.model_dump(mode="json"),
        },
    )

    logger.info(
        "webhook.accepted",
        extra={
            "gh_event": event,
            "delivery": delivery,
            "execution_id": execution.execution_id,
        },
    )
    return {"queued": True, "execution_id": execution.execution_id}
