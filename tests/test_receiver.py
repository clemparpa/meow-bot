"""Integration tests for the FastAPI webhook receiver (S6)."""

from __future__ import annotations

import hashlib
import hmac
import importlib
import io
import json
import logging
from collections.abc import AsyncIterator, Iterator
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from meow.common.logging import _HANDLER_SENTINEL, JsonFormatter
from tests.fixtures.webhooks import issue_comment_body

WEBHOOK_SECRET = "s3cr3t-webhook-key"
BOT_LOGIN = "meow-bot[bot]"


def _sign(body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


@pytest.fixture(autouse=True)
def _receiver_env(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Provide the env vars Settings() requires and reload the app module.

    Reloading guarantees that ``settings`` and ``logger`` pick up the test
    environment instead of whatever the previous test (or process) left
    behind.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MEOW_DOMAIN", "meow.test")
    monkeypatch.setenv("GITHUB_APP_ID", "1")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("MISTRAL_API_KEY", "mistral-test")
    monkeypatch.setenv("DAYTONA_API_KEY", "daytona-test")
    monkeypatch.setenv("DEPLOYMENT_NAME", "meow-bot-test")
    # Set the bot login here (not inside individual tests) so that the
    # module-level ``Settings()`` in receiver.app — instantiated when the
    # `client` fixture reloads the module — picks it up.
    monkeypatch.setenv("MEOW_BOT_LOGIN", BOT_LOGIN)


@pytest.fixture
def log_buffer() -> Iterator[io.StringIO]:
    """Replace the receiver logger's handler with an in-memory buffer.

    Pytest's ``capsys``/``capfd`` race with the module-level handler that
    binds to ``sys.stdout`` at import time, so we control the sink directly
    instead.
    """
    buf = io.StringIO()
    logger = logging.getLogger("meow.receiver")
    original_handlers = logger.handlers[:]
    original_propagate = logger.propagate
    logger.handlers.clear()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter("receiver"))
    setattr(handler, _HANDLER_SENTINEL, True)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        yield buf
    finally:
        logger.handlers = original_handlers
        logger.propagate = original_propagate


EXECUTION_ID = "exec-fake-123"


@pytest.fixture
async def client(log_buffer: io.StringIO) -> AsyncIterator[AsyncClient]:
    from meow.receiver import app as app_module

    importlib.reload(app_module)
    # Replace the live Mistral workflows handle so no test ever hits
    # `api.mistral.ai`. Individual tests can introspect this mock via
    # `app_module._workflows_client.workflows.execute_workflow`.
    app_module._workflows_client.workflows = MagicMock()
    app_module._workflows_client.workflows.execute_workflow.return_value = MagicMock(
        execution_id=EXECUTION_ID, status="RUNNING"
    )
    transport = ASGITransport(app=app_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_healthz_ok(client: AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_webhook_missing_signature_returns_401(client: AsyncClient) -> None:
    response = await client.post(
        "/gh/webhook",
        content=b"{}",
        headers={"X-GitHub-Event": "issue_comment"},
    )
    assert response.status_code == 401


async def test_webhook_invalid_signature_returns_401(client: AsyncClient) -> None:
    response = await client.post(
        "/gh/webhook",
        content=b"{}",
        headers={
            "X-Hub-Signature-256": "sha256=" + "0" * 64,
            "X-GitHub-Event": "issue_comment",
        },
    )
    assert response.status_code == 401


async def test_webhook_unhandled_event_returns_skipped(client: AsyncClient) -> None:
    body = json.dumps({"zen": "Keep it logically awesome."}).encode("utf-8")
    response = await client.post(
        "/gh/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": _sign(body),
            "X-GitHub-Event": "ping",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"skipped": "event"}


async def test_webhook_issue_comment_returns_queued(client: AsyncClient) -> None:
    body = issue_comment_body(sender_login="alice")
    response = await client.post(
        "/gh/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": _sign(body),
            "X-GitHub-Event": "issue_comment",
            "X-GitHub-Delivery": "deadbeef-1234",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"queued": True, "execution_id": EXECUTION_ID}


async def test_webhook_self_event_skipped(client: AsyncClient) -> None:
    body = issue_comment_body(sender_login=BOT_LOGIN)
    response = await client.post(
        "/gh/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": _sign(body),
            "X-GitHub-Event": "issue_comment",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"skipped": "self"}


async def test_webhook_logs_accepted_event(log_buffer: io.StringIO, client: AsyncClient) -> None:
    body = issue_comment_body(sender_login="alice")
    response = await client.post(
        "/gh/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": _sign(body),
            "X-GitHub-Event": "issue_comment",
            "X-GitHub-Delivery": "abc-123",
        },
    )
    assert response.status_code == 200

    accepted_lines = [
        json.loads(line)
        for line in log_buffer.getvalue().splitlines()
        if '"event": "webhook.accepted"' in line
    ]
    assert accepted_lines, f"no webhook.accepted log line: {log_buffer.getvalue()!r}"
    record = accepted_lines[-1]
    assert record["svc"] == "receiver"
    assert record["level"] == "info"
    assert record["gh_event"] == "issue_comment"
    assert record["delivery"] == "abc-123"
    assert record["execution_id"] == EXECUTION_ID


async def test_webhook_malformed_payload_returns_400(client: AsyncClient) -> None:
    body = b'{"not":"valid"}'
    response = await client.post(
        "/gh/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": _sign(body),
            "X-GitHub-Event": "issue_comment",
        },
    )
    assert response.status_code == 400


async def test_webhook_starts_workflow_with_delivery_idempotency(client: AsyncClient) -> None:
    from meow.receiver import app as app_module

    body = issue_comment_body(sender_login="alice")
    response = await client.post(
        "/gh/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": _sign(body),
            "X-GitHub-Event": "issue_comment",
            "X-GitHub-Delivery": "delivery-xyz-999",
        },
    )
    assert response.status_code == 200

    execute = app_module._workflows_client.workflows.execute_workflow
    execute.assert_called_once()  # ty: ignore[unresolved-attribute]
    kwargs = execute.call_args.kwargs  # ty: ignore[unresolved-attribute]
    assert kwargs["workflow_identifier"] == "GithubEventHandler"
    assert kwargs["execution_id"] == "issue_comment-delivery-xyz-999"
    assert kwargs["deployment_name"] == "meow-bot-test"
    assert kwargs["input"]["event"] == "issue_comment"
    assert kwargs["input"]["delivery"] == "delivery-xyz-999"
    assert kwargs["input"]["payload"]["action"] == "created"
    assert kwargs["input"]["payload"]["sender"]["login"] == "alice"
