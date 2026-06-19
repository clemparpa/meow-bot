"""Unit tests for the implementation flow's read-only changeset extraction.

``run_feature_implement_vibe`` itself stands up a real Koyeb sandbox (covered
end-to-end elsewhere), but its substance — turning the agent's working-tree
edits into a :class:`Changeset` via read-only ``git status`` + file reads — lives
in the module-level :func:`_extract_changeset`, which we exercise against a fake
sandbox. No git writes happen here: the commit is a separate worker activity
(see ``test_commit_changeset``).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest
from koyeb import AsyncSandbox
from pydantic import ValidationError

from meow.worker.activities import run_vibe as rv
from meow.worker.activities.run_vibe import _extract_changeset
from meow.worker.models import CloneSandboxSpec


class _ChangesetFS:
    """Fake filesystem: serves the polling sentinels + arbitrary repo files.

    File contents may be ``bytes`` to model a binary file the agent wrote — the
    activity reads via base64 (which yields bytes) and then decodes as UTF-8.
    """

    def __init__(self, *, status_out: str, files: dict[str, str | bytes]) -> None:
        self._status_out = status_out
        self._files = files

    async def read_file(self, path: str, encoding: str = "utf-8") -> SimpleNamespace:
        if path.endswith(".code"):
            return SimpleNamespace(content="0")  # command always "done", exit 0
        if path.endswith(".out"):
            return SimpleNamespace(content=self._status_out)
        if path.endswith(".err"):
            return SimpleNamespace(content="")
        if path in self._files:
            return SimpleNamespace(content=self._files[path])
        raise FileNotFoundError(path)


class _ChangesetSandbox:
    def __init__(self, *, status_out: str, files: dict[str, str | bytes]) -> None:
        self.filesystem = _ChangesetFS(status_out=status_out, files=files)
        self.launched: list[tuple[str, str | None]] = []

    async def launch_process(
        self, cmd: str, cwd: str | None = None, env: dict | None = None
    ) -> str:
        self.launched.append((cmd, cwd))
        return "pid"

    async def kill_process(self, process_id: str) -> None:  # pragma: no cover - never killed
        pass


async def test_extract_changeset_reads_adds_and_flags_deletes() -> None:
    sandbox = _ChangesetSandbox(
        status_out=" M src/app.py\x00?? new.py\x00 D old.py\x00",
        files={"/work/repo/src/app.py": "edited", "/work/repo/new.py": "brand new"},
    )

    changeset = await _extract_changeset(cast(AsyncSandbox, sandbox))

    # Content is the file's plain UTF-8 text (fed inline to the Git Data API).
    by_path = {f.path: f.content for f in changeset.files}
    assert by_path == {
        "src/app.py": "edited",
        "new.py": "brand new",
        "old.py": None,  # deletion
    }
    # The only command run is the read-only status probe.
    assert len(sandbox.launched) == 1
    cmd = sandbox.launched[0][0]
    assert "git status --porcelain=v1 -z --no-renames" in cmd
    # `-uall` so files inside a brand-new directory are listed individually
    # (git would otherwise collapse them into a single `?? dir/` entry).
    assert "--untracked-files=all" in cmd


async def test_extract_changeset_lists_files_in_new_directories() -> None:
    # A whole new directory: git with -uall reports each file, not `?? pkg/`.
    sandbox = _ChangesetSandbox(
        status_out="?? pkg/__init__.py\x00?? pkg/core.py\x00",
        files={"/work/repo/pkg/__init__.py": "", "/work/repo/pkg/core.py": "x = 1"},
    )

    changeset = await _extract_changeset(cast(AsyncSandbox, sandbox))

    by_path = {f.path: f.content for f in changeset.files}
    assert by_path == {"pkg/__init__.py": "", "pkg/core.py": "x = 1"}


async def test_extract_changeset_empty_when_clean() -> None:
    sandbox = _ChangesetSandbox(status_out="", files={})
    changeset = await _extract_changeset(cast(AsyncSandbox, sandbox))
    assert changeset.is_empty


async def test_extract_changeset_drops_oversize_diff(monkeypatch) -> None:
    monkeypatch.setattr(rv, "_MAX_CHANGESET_BYTES", 10)
    sandbox = _ChangesetSandbox(
        status_out="?? big.bin\x00",
        files={"/work/repo/big.bin": "x" * 50},
    )

    changeset = await _extract_changeset(cast(AsyncSandbox, sandbox))

    # Over the cap → dropped so the workflow posts a comment instead of a PR.
    assert changeset.is_empty


async def test_extract_changeset_drops_on_binary() -> None:
    # A file whose bytes aren't valid UTF-8 can't be committed inline → the
    # whole changeset is dropped (no partial PR), the workflow posts a comment.
    sandbox = _ChangesetSandbox(
        status_out="?? logo.png\x00",
        files={"/work/repo/logo.png": b"\x89PNG\r\n\xff\xfe\x00"},
    )

    changeset = await _extract_changeset(cast(AsyncSandbox, sandbox))

    assert changeset.is_empty


def test_clone_sandbox_spec_rejects_bad_repo() -> None:
    with pytest.raises(ValidationError):
        CloneSandboxSpec(installation_id=1, repo_full_name="not-a-repo", ref="main")


def test_clone_sandbox_spec_is_frozen() -> None:
    spec = CloneSandboxSpec(installation_id=1, repo_full_name="owner/repo", ref="main")
    with pytest.raises(ValidationError):
        spec.ref = "other"  # type: ignore[misc]
