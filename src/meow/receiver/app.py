"""FastAPI webhook receiver for meow-bot.

Implements the minimal v0.0.x receiver described in `spec.md` §6 and
``stories/v0.0.x.md`` (S6):

- ``GET /healthz`` for liveness probes.
- ``POST /gh/webhook`` validates the HMAC-SHA256 signature, filters
  self-deliveries and unhandled events, then logs ``webhook.accepted``
  and returns ``{"queued": true}``.

No call to Mistral Workflows or Daytona is made at this stage — the
"queued" status is a stub that will be wired to the worker in v0.1.0.
"""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from meow.common.config import Settings
from meow.common.github.webhook import InvalidSignature, verify_signature
from meow.common.logging import get_logger

settings = Settings()  # ty: ignore[missing-argument]
logger = get_logger("receiver")

app = FastAPI(title="meow-receiver", version="0.0.1")

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

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid JSON body") from None

    sender_login = (payload.get("sender") or {}).get("login")
    bot = _bot_login()
    if bot and sender_login == bot:
        logger.info(
            "webhook.skipped",
            extra={"reason": "self", "delivery": delivery, "gh_event": event},
        )
        return {"skipped": "self"}

    if event not in _HANDLED_EVENTS:
        logger.info(
            "webhook.skipped",
            extra={"reason": "event-not-handled", "delivery": delivery, "gh_event": event},
        )
        return {"skipped": "event"}

    logger.info(
        "webhook.accepted",
        extra={"gh_event": event, "delivery": delivery},
    )
    return {"queued": True}
