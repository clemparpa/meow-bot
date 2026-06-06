"""Fixtures for receiver integration tests."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient, Response

from tests.conftest import TEST_WEBHOOK_SECRET


def _sign(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


WebhookPost = Callable[..., Awaitable[Response]]


@pytest.fixture
def dispatcher_spy() -> AsyncMock:
    return AsyncMock(return_value={"queued": True, "execution_id": "spy-exec"})


@pytest.fixture
async def client(dispatcher_spy: AsyncMock) -> AsyncIterator[AsyncClient]:
    # Lazy import: `tests/conftest.py` must have populated env vars before
    # `meow.receiver.app` (whose module-level `Settings()` would otherwise crash).
    from meow.receiver.app import app, get_workflow_dispatcher

    app.dependency_overrides[get_workflow_dispatcher] = lambda: dispatcher_spy
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_workflow_dispatcher, None)


@pytest.fixture
def webhook_post(client: AsyncClient) -> WebhookPost:
    """POST a webhook payload, auto-signing unless `signature_override` is set."""

    async def post(
        event: str | None,
        payload: dict[str, Any],
        *,
        signature_override: str | None = None,
        delivery: str = "test-delivery-1",
    ) -> Response:
        body = json.dumps(payload).encode("utf-8")
        signature = (
            signature_override
            if signature_override is not None
            else _sign(body, TEST_WEBHOOK_SECRET)
        )
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "X-Hub-Signature-256": signature,
            "X-GitHub-Delivery": delivery,
        }
        if event is not None:
            headers["X-GitHub-Event"] = event
        return await client.post("/gh/webhook", content=body, headers=headers)

    return post
