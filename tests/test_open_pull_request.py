"""Unit tests for the ``open_pull_request`` activity.

Two paths matter: the happy create (draft PR, scoped to ``pull_requests:write``,
body carries ``Closes #N``) and the re-run path where GitHub answers a duplicate
``create`` with a 422 — the activity then looks the PR up by head and updates it
instead of failing.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import cast

import httpx
import pytest
from githubkit.exception import RequestFailed

from meow.worker.activities import open_pull_request as opr_mod
from meow.worker.activities.open_pull_request import open_pull_request
from meow.worker.models import VibeResult

_RESULT = VibeResult(body="Implements dark mode.", terminated_early=False, stop_reason=None)


def _request_failed(status_code: int) -> RequestFailed:
    req = httpx.Request("POST", "https://api.github.com/repos/owner/repo/pulls")
    raw_response = httpx.Response(status_code, request=req)
    response = SimpleNamespace(
        raw_request=req,
        raw_response=raw_response,
        status_code=status_code,
        _status_reason=str(status_code),
    )
    return RequestFailed(response)  # ty: ignore[invalid-argument-type]


async def test_open_pull_request_creates_draft(monkeypatch) -> None:
    captured: dict[str, object] = {}

    @asynccontextmanager
    async def fake_auth(installation_id, *, permissions=None, repositories=None):
        captured["permissions"] = permissions
        captured["repositories"] = repositories

        async def async_create(owner, repo, *, title, head, base, body, draft):
            captured.update(
                owner=owner, repo=repo, title=title, head=head, base=base, body=body, draft=draft
            )
            return SimpleNamespace(
                parsed_data=SimpleNamespace(number=5, html_url="https://gh/pr/5")
            )

        client = SimpleNamespace(
            rest=SimpleNamespace(pulls=SimpleNamespace(async_create=async_create))
        )
        yield SimpleNamespace(client=client)

    monkeypatch.setattr(opr_mod, "github_installation_auth", fake_auth)

    url = await open_pull_request(
        42,
        "owner/repo",
        head_branch="meow/issue-7",
        base_branch="main",
        issue_number=7,
        title="Add dark mode",
        result=_RESULT,
    )

    assert url == "https://gh/pr/5"
    assert captured["permissions"] == {"pull_requests": "write"}
    assert captured["draft"] is True
    assert captured["head"] == "meow/issue-7"
    assert captured["base"] == "main"
    body = cast(str, captured["body"])
    assert "Closes #7" in body
    assert "Implements dark mode." in body


async def test_open_pull_request_updates_existing_on_conflict(monkeypatch) -> None:
    captured: dict[str, object] = {}

    @asynccontextmanager
    async def fake_auth(installation_id, *, permissions=None, repositories=None):
        async def async_create(owner, repo, *, title, head, base, body, draft):
            raise _request_failed(422)

        async def async_list(owner, repo, *, head, state):
            captured["list_head"] = head
            captured["list_state"] = state
            return SimpleNamespace(parsed_data=[SimpleNamespace(number=9)])

        async def async_update(owner, repo, pull_number, *, body):
            captured["update_number"] = pull_number
            captured["update_body"] = body
            return SimpleNamespace(parsed_data=SimpleNamespace(html_url="https://gh/pr/9"))

        client = SimpleNamespace(
            rest=SimpleNamespace(
                pulls=SimpleNamespace(
                    async_create=async_create,
                    async_list=async_list,
                    async_update=async_update,
                )
            )
        )
        yield SimpleNamespace(client=client)

    monkeypatch.setattr(opr_mod, "github_installation_auth", fake_auth)

    url = await open_pull_request(
        42,
        "owner/repo",
        head_branch="meow/issue-7",
        base_branch="main",
        issue_number=7,
        title="Add dark mode",
        result=_RESULT,
    )

    assert url == "https://gh/pr/9"
    assert captured["list_head"] == "owner:meow/issue-7"
    assert captured["list_state"] == "open"
    assert captured["update_number"] == 9


async def test_open_pull_request_reraises_non_422(monkeypatch) -> None:
    @asynccontextmanager
    async def fake_auth(installation_id, *, permissions=None, repositories=None):
        async def async_create(owner, repo, *, title, head, base, body, draft):
            raise _request_failed(403)

        client = SimpleNamespace(
            rest=SimpleNamespace(pulls=SimpleNamespace(async_create=async_create))
        )
        yield SimpleNamespace(client=client)

    monkeypatch.setattr(opr_mod, "github_installation_auth", fake_auth)

    with pytest.raises(RequestFailed):
        await open_pull_request(
            42,
            "owner/repo",
            head_branch="meow/issue-7",
            base_branch="main",
            issue_number=7,
            title="Add dark mode",
            result=_RESULT,
        )
