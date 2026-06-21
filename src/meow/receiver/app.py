"""FastAPI webhook receiver for meow-bot.

Implements the v0.1.0 receiver described in ``spec.md`` §6 and
``stories/v0.1.0.md`` (S6):

- ``GET /healthz`` for liveness probes.
- ``POST /gh/webhook`` validates the HMAC-SHA256 signature, filters
  self-deliveries and unhandled events, then starts a Mistral Workflows
  execution (idempotent on ``X-GitHub-Delivery``) before returning
  ``{"queued": true, ...}``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from githubkit.webhooks import parse
from pydantic import ValidationError

from meow.common.config import Settings
from meow.common.github.webhook import InvalidSignature, verify_signature
from meow.common.logging import get_logger
from meow.common.webhooks_inputs.base_model import WebhookInput
from meow.receiver.client import trigger_workflow

# Side-effect import: every module under controllers/ registers its
# `@on_event`-decorated class in `_CONTROLLERS` at import time. Removing
# this line silently disables every route.
from meow.receiver.controllers import *  # noqa: F401,F403
from meow.receiver.utils import _CONTROLLERS, WebhookContext

settings = Settings()  # ty: ignore[missing-argument]
logger = get_logger("receiver")

app = FastAPI(title="meow-receiver", version="0.1.0")


WorkflowDispatcher = Callable[[str, WebhookInput, WebhookContext], Awaitable[dict[str, Any]]]


def get_workflow_dispatcher() -> WorkflowDispatcher:
    # Indirection so tests can swap `trigger_workflow` via
    # `app.dependency_overrides` without touching the Mistral client.
    return trigger_workflow


async def verified_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
    x_github_delivery: str | None = Header(default=None),
) -> tuple[bytes, str | None, str | None]:
    body = await request.body()
    try:
        verify_signature(x_hub_signature_256, body, settings.github_webhook_secret)
    except InvalidSignature:
        raise HTTPException(401, "invalid signature") from None
    return body, x_github_event, x_github_delivery


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/gh/webhook")
async def gh_webhook(
    auth: tuple[bytes, str | None, str | None] = Depends(verified_webhook),
    dispatcher: WorkflowDispatcher = Depends(get_workflow_dispatcher),  # noqa: B008
) -> dict[str, Any]:
    body, event, delivery = auth
    if not event:
        logger.info("webhook.skipped", extra={"reason": "no-event", "delivery": delivery})
        return {"skipped": "event"}

    dispatch = _CONTROLLERS.get(event)
    if dispatch is None:
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
        raise HTTPException(400, "malformed webhook payload") from None

    sender = getattr(parsed, "sender", {})
    sender_login = getattr(sender, "login", None)
    if sender_login == settings.bot_login:
        logger.info(
            "webhook.skipped",
            extra={"reason": "self", "delivery": delivery, "gh_event": event},
        )
        return {"skipped": "self"}

    event_dispatch = dispatch.get(type(parsed))
    if event_dispatch is None:
        logger.info(
            "webhook.skipped",
            extra={"reason": "action-not-handled", "delivery": delivery, "gh_event": event},
        )
        return {"skipped": "action"}

    ctx = WebhookContext(event_name=event, delivery=delivery)
    try:
        input_model = event_dispatch.factory(parsed, ctx)
    except ValueError as exc:
        # Factory contract violation (e.g. installation UNSET) — skip with 200
        # so GitHub doesn't retry a deterministic failure.
        logger.info(
            "webhook.skipped",
            extra={
                "reason": "input-build-failed",
                "error": str(exc),
                "delivery": delivery,
                "gh_event": event,
            },
        )
        return {"skipped": "input"}

    for method, predicate, workflow_id in event_dispatch.handlers:
        if predicate is not None and not predicate(input_model):
            continue

        logger.info(
            "webhook.dispatched",
            extra={
                "gh_event": event,
                "action": type(parsed).__name__,
                "handler": workflow_id or getattr(method, "__name__", "<unknown>"),
                "delivery": delivery,
            },
        )
        if workflow_id is not None:
            return await dispatcher(workflow_id, input_model, ctx)
        # method is non-None whenever workflow_id is None — guaranteed by on_event.
        assert method is not None
        return await method(input_model, ctx)

    logger.info(
        "webhook.skipped",
        extra={"reason": "no-intent", "delivery": delivery, "gh_event": event},
    )
    return {"skipped": "no-intent"}
