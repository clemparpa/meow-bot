"""Integration tests for the FastAPI webhook receiver (S6)."""

from __future__ import annotations

import hashlib
import hmac
import importlib
import io
import json
import logging
from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient

from meow.common.logging import _HANDLER_SENTINEL, JsonFormatter

WEBHOOK_SECRET = "s3cr3t-webhook-key"
BOT_LOGIN = "meow-bot[bot]"


def _sign(body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _simple_user(login: str, user_id: int = 1) -> dict:
    return {
        "login": login,
        "id": user_id,
        "node_id": "U_kgDOABCDEF",
        "avatar_url": "https://avatars.githubusercontent.com/u/1?v=4",
        "gravatar_id": "",
        "url": f"https://api.github.com/users/{login}",
        "html_url": f"https://github.com/{login}",
        "followers_url": f"https://api.github.com/users/{login}/followers",
        "following_url": f"https://api.github.com/users/{login}/following{{/other_user}}",
        "gists_url": f"https://api.github.com/users/{login}/gists{{/gist_id}}",
        "starred_url": f"https://api.github.com/users/{login}/starred{{/owner}}{{/repo}}",
        "subscriptions_url": f"https://api.github.com/users/{login}/subscriptions",
        "organizations_url": f"https://api.github.com/users/{login}/orgs",
        "repos_url": f"https://api.github.com/users/{login}/repos",
        "events_url": f"https://api.github.com/users/{login}/events{{/privacy}}",
        "received_events_url": f"https://api.github.com/users/{login}/received_events",
        "type": "User",
        "site_admin": False,
    }


def _reactions() -> dict:
    return {
        "+1": 0,
        "-1": 0,
        "confused": 0,
        "eyes": 0,
        "heart": 0,
        "hooray": 0,
        "laugh": 0,
        "rocket": 0,
        "total_count": 0,
        "url": "https://api.github.com/reactions",
    }


def _issue_comment_payload(sender_login: str = "alice", action: str = "created") -> bytes:
    """Return a JSON-encoded issue_comment webhook body that satisfies githubkit's schema."""
    sender = _simple_user(sender_login, user_id=42)
    owner = _simple_user("octocat", user_id=2)
    issue_user = {"id": 42, "login": sender_login}
    comment_user = {"id": 42, "login": sender_login}
    payload = {
        "action": action,
        "comment": {
            "author_association": "NONE",
            "body": "hello",
            "created_at": "2024-01-01T00:00:00Z",
            "html_url": "https://github.com/octocat/hello/issues/1#issuecomment-1",
            "id": 1,
            "issue_url": "https://api.github.com/repos/octocat/hello/issues/1",
            "node_id": "IC_kwDOABCD",
            "performed_via_github_app": None,
            "reactions": _reactions(),
            "updated_at": "2024-01-01T00:00:00Z",
            "url": "https://api.github.com/repos/octocat/hello/issues/comments/1",
            "user": comment_user,
        },
        "issue": {
            "active_lock_reason": None,
            "assignee": None,
            "assignees": [],
            "author_association": "NONE",
            "body": None,
            "closed_at": None,
            "comments": 0,
            "comments_url": "https://api.github.com/repos/octocat/hello/issues/1/comments",
            "created_at": "2024-01-01T00:00:00Z",
            "events_url": "https://api.github.com/repos/octocat/hello/issues/1/events",
            "html_url": "https://github.com/octocat/hello/issues/1",
            "id": 100,
            "labels": [],
            "labels_url": "https://api.github.com/repos/octocat/hello/issues/1/labels{/name}",
            "locked": False,
            "milestone": None,
            "node_id": "I_kwDOABCD",
            "number": 1,
            "reactions": _reactions(),
            "repository_url": "https://api.github.com/repos/octocat/hello",
            "state": "open",
            "title": "An issue",
            "updated_at": "2024-01-01T00:00:00Z",
            "url": "https://api.github.com/repos/octocat/hello/issues/1",
            "user": issue_user,
        },
        "repository": {
            "id": 10,
            "node_id": "R_kgDOABCD",
            "name": "hello",
            "full_name": "octocat/hello",
            "license": None,
            "forks": 0,
            "owner": owner,
            "private": False,
            "html_url": "https://github.com/octocat/hello",
            "description": None,
            "fork": False,
            "url": "https://api.github.com/repos/octocat/hello",
            "archive_url": "https://api.github.com/repos/octocat/hello/{archive_format}{/ref}",
            "assignees_url": "https://api.github.com/repos/octocat/hello/assignees{/user}",
            "blobs_url": "https://api.github.com/repos/octocat/hello/git/blobs{/sha}",
            "branches_url": "https://api.github.com/repos/octocat/hello/branches{/branch}",
            "collaborators_url": "https://api.github.com/repos/octocat/hello/collaborators{/collaborator}",
            "comments_url": "https://api.github.com/repos/octocat/hello/comments{/number}",
            "commits_url": "https://api.github.com/repos/octocat/hello/commits{/sha}",
            "compare_url": "https://api.github.com/repos/octocat/hello/compare/{base}...{head}",
            "contents_url": "https://api.github.com/repos/octocat/hello/contents/{+path}",
            "contributors_url": "https://api.github.com/repos/octocat/hello/contributors",
            "deployments_url": "https://api.github.com/repos/octocat/hello/deployments",
            "downloads_url": "https://api.github.com/repos/octocat/hello/downloads",
            "events_url": "https://api.github.com/repos/octocat/hello/events",
            "forks_url": "https://api.github.com/repos/octocat/hello/forks",
            "git_commits_url": "https://api.github.com/repos/octocat/hello/git/commits{/sha}",
            "git_refs_url": "https://api.github.com/repos/octocat/hello/git/refs{/sha}",
            "git_tags_url": "https://api.github.com/repos/octocat/hello/git/tags{/sha}",
            "git_url": "git://github.com/octocat/hello.git",
            "issue_comment_url": "https://api.github.com/repos/octocat/hello/issues/comments{/number}",
            "issue_events_url": "https://api.github.com/repos/octocat/hello/issues/events{/number}",
            "issues_url": "https://api.github.com/repos/octocat/hello/issues{/number}",
            "keys_url": "https://api.github.com/repos/octocat/hello/keys{/key_id}",
            "labels_url": "https://api.github.com/repos/octocat/hello/labels{/name}",
            "languages_url": "https://api.github.com/repos/octocat/hello/languages",
            "merges_url": "https://api.github.com/repos/octocat/hello/merges",
            "milestones_url": "https://api.github.com/repos/octocat/hello/milestones{/number}",
            "notifications_url": "https://api.github.com/repos/octocat/hello/notifications{?since,all,participating}",
            "pulls_url": "https://api.github.com/repos/octocat/hello/pulls{/number}",
            "releases_url": "https://api.github.com/repos/octocat/hello/releases{/id}",
            "ssh_url": "git@github.com:octocat/hello.git",
            "stargazers_url": "https://api.github.com/repos/octocat/hello/stargazers",
            "statuses_url": "https://api.github.com/repos/octocat/hello/statuses/{sha}",
            "subscribers_url": "https://api.github.com/repos/octocat/hello/subscribers",
            "subscription_url": "https://api.github.com/repos/octocat/hello/subscription",
            "tags_url": "https://api.github.com/repos/octocat/hello/tags",
            "teams_url": "https://api.github.com/repos/octocat/hello/teams",
            "trees_url": "https://api.github.com/repos/octocat/hello/git/trees{/sha}",
            "clone_url": "https://github.com/octocat/hello.git",
            "mirror_url": None,
            "hooks_url": "https://api.github.com/repos/octocat/hello/hooks",
            "svn_url": "https://github.com/octocat/hello",
            "homepage": None,
            "language": None,
            "forks_count": 0,
            "stargazers_count": 0,
            "watchers_count": 0,
            "size": 0,
            "default_branch": "main",
            "open_issues_count": 0,
            "has_issues": True,
            "has_projects": True,
            "has_wiki": True,
            "has_pages": False,
            "has_downloads": True,
            "archived": False,
            "disabled": False,
            "pushed_at": "2024-01-01T00:00:00Z",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "open_issues": 0,
            "watchers": 0,
        },
        "sender": sender,
    }
    return json.dumps(payload).encode("utf-8")


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
    monkeypatch.delenv("MEOW_BOT_LOGIN", raising=False)


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


@pytest.fixture
async def client(log_buffer: io.StringIO) -> AsyncIterator[AsyncClient]:
    from meow.receiver import app as app_module

    importlib.reload(app_module)
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
    body = _issue_comment_payload(sender_login="alice")
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
    assert response.json() == {"queued": True}


async def test_webhook_self_event_skipped(
    monkeypatch: pytest.MonkeyPatch, client: AsyncClient
) -> None:
    monkeypatch.setenv("MEOW_BOT_LOGIN", BOT_LOGIN)
    body = _issue_comment_payload(sender_login=BOT_LOGIN)
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
    body = _issue_comment_payload(sender_login="alice")
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
