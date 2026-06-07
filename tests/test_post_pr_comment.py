"""Unit tests for the ``post_pr_comment`` activity.

The key regression guard: commenting on a *pull request* via the shared
issue-comments endpoint requires ``pull_requests:write`` (GitHub checks the
underlying resource type), so requesting only ``issues:write`` yields a 403.
We assert the activity mints a token scoped to both permissions.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

from meow.worker.activities import post_pr_comment as ppc_mod
from meow.worker.activities.post_pr_comment import post_pr_comment
from meow.worker.models import VibeResult


async def test_post_pr_comment_requests_pull_requests_write(monkeypatch) -> None:
    captured: dict[str, object] = {}

    @asynccontextmanager
    async def fake_auth(installation_id, *, permissions=None, repositories=None):
        captured["installation_id"] = installation_id
        captured["permissions"] = permissions
        captured["repositories"] = repositories

        async def async_create_comment(owner, repo, pr_number, *, body):
            captured["owner"] = owner
            captured["repo"] = repo
            captured["pr_number"] = pr_number
            captured["body"] = body
            return SimpleNamespace(
                parsed_data=SimpleNamespace(id=123, html_url="https://gh/c/123")
            )

        client = SimpleNamespace(
            rest=SimpleNamespace(
                issues=SimpleNamespace(async_create_comment=async_create_comment)
            )
        )
        yield SimpleNamespace(client=client)

    monkeypatch.setattr(ppc_mod, "github_installation_auth", fake_auth)

    result = VibeResult(body="LGTM", terminated_early=False, stop_reason=None)
    url = await post_pr_comment(42, "owner/repo", 7, result)

    assert url == "https://gh/c/123"
    assert captured["permissions"] == {"issues": "write", "pull_requests": "write"}
    assert captured["repositories"] == ["owner/repo"]
    assert captured["installation_id"] == 42
    assert captured["owner"] == "owner"
    assert captured["repo"] == "repo"
    assert captured["pr_number"] == 7
    assert "LGTM" in captured["body"]
