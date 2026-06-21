"""Unit tests for the implementation flow's read-only changeset extraction.

``run_feature_implement_vibe`` itself stands up a real Koyeb sandbox (covered
end-to-end elsewhere), but its substance — turning the agent's working-tree
edits into a :class:`Changeset` via read-only ``git status`` + file reads — lives
in the module-level :func:`_extract_changeset`, which we exercise against a fake
sandbox. No git writes happen here: the commit is a separate worker activity
(see ``test_commit_changeset``).

Extraction finds changes with a read-only ``git status`` (run through
``exec_polling``) and reads each file's text with ``filesystem.read_file`` in
plain UTF-8 — koyeb's ``encoding="base64"`` path is broken on non-ASCII content.
The fake serves the ``exec_polling`` sentinels for the status probe and the file
contents for the reads; a ``bytes`` file content models a binary the agent wrote
(which extraction drops via the strict UTF-8 decode).
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import cast

import pytest
from koyeb import AsyncSandbox
from pydantic import ValidationError

from meow.worker.activities import run_vibe as rv
from meow.worker.activities.run_vibe import _extract_changeset
from meow.worker.models import CloneSandboxSpec

_SENTINEL_RE = re.compile(r"(/tmp/meow-[0-9a-f]+\.(?:out|err|code))")


def _sentinel(line: str) -> str:
    match = _SENTINEL_RE.search(line)
    assert match is not None, f"no sentinel path in {line!r}"
    return match.group(1)


class _ChangesetSandbox:
    """Fake sandbox: ``git status`` via ``exec_polling``, file reads via ``read_file``.

    ``launch_process`` only ever gets the wrapped status script; we stash its
    stdout under the ``.out`` sentinel so the poll reads it back. ``files`` maps
    an absolute path to its content; ``bytes`` (which ``read_file`` only yields on
    a binary read) models a binary file, and a path absent from ``files`` models
    an unreadable one.
    """

    def __init__(self, *, status_out: str, files: dict[str, str | bytes]) -> None:
        self._status_out = status_out
        self._files = files
        self.commands: list[str] = []  # the real commands, in order
        self._out: dict[str, str] = {}
        self._code: dict[str, str] = {}
        self.filesystem = self

    async def launch_process(
        self, cmd: str, cwd: str | None = None, env: dict | None = None
    ) -> str:
        trap_line, exec_line, real = cmd.split("\n", 2)
        assert real.startswith("git status"), f"unexpected command: {real!r}"
        self.commands.append(real)
        self._out[_sentinel(exec_line)] = self._status_out
        self._code[_sentinel(trap_line)] = "0"  # the probe "completes" with exit 0
        return "pid"

    async def read_file(self, path: str, encoding: str = "utf-8") -> SimpleNamespace:
        if path.endswith(".code"):
            return SimpleNamespace(content=self._code.get(path, ""))
        if path.endswith(".out"):
            return SimpleNamespace(content=self._out.get(path, ""))
        if path.endswith(".err"):
            return SimpleNamespace(content="")
        if path in self._files:
            return SimpleNamespace(content=self._files[path])
        raise FileNotFoundError(path)

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
    # The only command is the read-only status probe; files are read directly.
    assert len(sandbox.commands) == 1
    assert "git status --porcelain=v1 -z --no-renames" in sandbox.commands[0]
    # `-uall` so files inside a brand-new directory are listed individually
    # (git would otherwise collapse them into a single `?? dir/` entry).
    assert "--untracked-files=all" in sandbox.commands[0]


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
    # Bytes that aren't valid UTF-8 hit the strict-decode in _read_text and raise
    # UnicodeDecodeError → the whole changeset is dropped (no partial PR), the
    # workflow posts a comment instead. (In prod koyeb returns an already-decoded
    # str on the utf-8 read; the bytes path is the only place we can still tell.)
    sandbox = _ChangesetSandbox(
        status_out="?? logo.png\x00",
        files={"/work/repo/logo.png": b"\x89PNG\r\n\xff\xfe"},
    )

    changeset = await _extract_changeset(cast(AsyncSandbox, sandbox))

    assert changeset.is_empty


async def test_extract_changeset_drops_when_file_unreadable() -> None:
    # The read failing (e.g. the executor refusing a binary file) must drop the
    # changeset, not crash the activity — the path is absent from `files`, so the
    # fake's read_file raises.
    sandbox = _ChangesetSandbox(status_out="?? mystery.dat\x00", files={})

    changeset = await _extract_changeset(cast(AsyncSandbox, sandbox))

    assert changeset.is_empty


def test_clone_sandbox_spec_rejects_bad_repo() -> None:
    with pytest.raises(ValidationError):
        CloneSandboxSpec(installation_id=1, repo_full_name="not-a-repo", ref="main")


def test_clone_sandbox_spec_is_frozen() -> None:
    spec = CloneSandboxSpec(installation_id=1, repo_full_name="owner/repo", ref="main")
    with pytest.raises(ValidationError):
        spec.ref = "other"  # type: ignore[misc]
