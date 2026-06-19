"""Unit tests for the ``commit_changeset`` activity.

The activity builds one commit through the Git Data API and create-or-force
updates the branch ref. We assert it mints a ``contents:write`` token, turns
changed files into tree entries (text inline in ``content``, deletions as
null-sha entries) without creating blobs, and falls back from a 422 create to a
forced ref update on re-run.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from githubkit.exception import RequestFailed

from meow.worker.activities import commit_changeset as cc_mod
from meow.worker.activities.commit_changeset import commit_changeset
from meow.worker.models import Changeset, FileChange

_CHANGESET = Changeset(
    files=[
        FileChange(path="src/app.py", content="edited"),
        FileChange(path="old.py", content=None),  # deletion
    ]
)


def _request_failed(status_code: int) -> RequestFailed:
    req = httpx.Request("POST", "https://api.github.com/repos/owner/repo/git/refs")
    raw_response = httpx.Response(status_code, request=req)
    response = SimpleNamespace(
        raw_request=req,
        raw_response=raw_response,
        status_code=status_code,
        _status_reason=str(status_code),
    )
    return RequestFailed(response)  # ty: ignore[invalid-argument-type]


class _FakeGit:
    """Records Git Data API calls; ``create_ref_exc`` simulates a 422 re-run."""

    def __init__(self, *, create_ref_exc: RequestFailed | None = None) -> None:
        self.calls: dict[str, Any] = {}
        self._create_ref_exc = create_ref_exc

    async def async_get_ref(self, owner, repo, ref):
        self.calls["get_ref"] = ref
        return SimpleNamespace(
            parsed_data=SimpleNamespace(object_=SimpleNamespace(sha="basecommit"))
        )

    async def async_get_commit(self, owner, repo, sha):
        return SimpleNamespace(parsed_data=SimpleNamespace(tree=SimpleNamespace(sha="basetree")))

    async def async_create_tree(self, owner, repo, *, base_tree, tree):
        self.calls["tree_base"] = base_tree
        self.calls["tree"] = tree
        return SimpleNamespace(parsed_data=SimpleNamespace(sha="newtree"))

    async def async_create_commit(self, owner, repo, *, message, tree, parents):
        self.calls["commit"] = {"message": message, "tree": tree, "parents": parents}
        return SimpleNamespace(parsed_data=SimpleNamespace(sha="newcommit"))

    async def async_create_ref(self, owner, repo, *, ref, sha):
        if self._create_ref_exc is not None:
            raise self._create_ref_exc
        self.calls["create_ref"] = {"ref": ref, "sha": sha}

    async def async_update_ref(self, owner, repo, ref, *, sha, force):
        self.calls["update_ref"] = {"ref": ref, "sha": sha, "force": force}


def _fake_auth(git: _FakeGit, captured: dict[str, Any]):
    @asynccontextmanager
    async def fake_auth(installation_id, *, permissions=None, repositories=None):
        captured["permissions"] = permissions
        captured["repositories"] = repositories
        yield SimpleNamespace(client=SimpleNamespace(rest=SimpleNamespace(git=git)))

    return fake_auth


async def test_commit_changeset_creates_commit_and_ref(monkeypatch) -> None:
    git = _FakeGit()
    captured: dict[str, Any] = {}
    monkeypatch.setattr(cc_mod, "github_installation_auth", _fake_auth(git, captured))

    sha = await commit_changeset(42, "owner/repo", "main", "meow/issue-7", "msg", _CHANGESET)

    assert sha == "newcommit"
    assert captured["permissions"] == {"contents": "write"}
    # No blobs are created — content goes inline in the tree entries.
    assert "blobs" not in git.calls
    # The add carries its text in `content`; the deletion is sha=None.
    entries = {e["path"]: e for e in git.calls["tree"]}
    assert entries["src/app.py"].get("content") == "edited"
    assert entries["src/app.py"].get("sha") is None
    assert entries["old.py"].get("sha") is None
    assert entries["old.py"].get("content") is None
    assert git.calls["tree_base"] == "basetree"
    assert git.calls["commit"]["parents"] == ["basecommit"]
    assert git.calls["create_ref"] == {"ref": "refs/heads/meow/issue-7", "sha": "newcommit"}


async def test_commit_changeset_force_updates_existing_ref(monkeypatch) -> None:
    git = _FakeGit(create_ref_exc=_request_failed(422))
    captured: dict[str, Any] = {}
    monkeypatch.setattr(cc_mod, "github_installation_auth", _fake_auth(git, captured))

    sha = await commit_changeset(42, "owner/repo", "main", "meow/issue-7", "msg", _CHANGESET)

    assert sha == "newcommit"
    assert git.calls["update_ref"] == {
        "ref": "heads/meow/issue-7",
        "sha": "newcommit",
        "force": True,
    }


async def test_commit_changeset_reraises_non_422(monkeypatch) -> None:
    git = _FakeGit(create_ref_exc=_request_failed(403))
    captured: dict[str, Any] = {}
    monkeypatch.setattr(cc_mod, "github_installation_auth", _fake_auth(git, captured))

    with pytest.raises(RequestFailed):
        await commit_changeset(42, "owner/repo", "main", "meow/issue-7", "msg", _CHANGESET)


async def test_commit_changeset_rejects_empty() -> None:
    with pytest.raises(ValueError, match="empty changeset"):
        await commit_changeset(42, "owner/repo", "main", "meow/issue-7", "msg", Changeset(files=[]))
