"""Unit tests for the non-blocking polling exec path (`exec_polling`).

These cover the behaviour that replaces the old blocking ``sandbox.exec``:
launch a background process, poll a shell-written ``.code`` sentinel file
until it appears, read stdout/stderr back from the redirect files, and
surface a deadline overrun as :class:`SandboxExecTimeout` after killing the
process.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest
from koyeb import AsyncSandbox

from meow.worker.sandbox.builder import (
    SandboxBuilder,
    SandboxExecTimeout,
    exec_polling,
)


class _FakeFilesystem:
    def __init__(self, *, code_reads: list[str], contents: dict[str, str]) -> None:
        # Scripted sequence of `.code` reads — advance through them, then
        # stick on the last entry. An empty string models "not finished yet".
        self._code_reads = list(code_reads)
        self._contents = contents

    async def read_file(self, path: str, encoding: str = "utf-8") -> SimpleNamespace:
        if path.endswith(".code"):
            value = self._code_reads.pop(0) if len(self._code_reads) > 1 else self._code_reads[0]
            if value == "":
                # The sentinel file does not exist until the command exits.
                raise FileNotFoundError(path)
            return SimpleNamespace(content=value)
        if path.endswith(".out"):
            return SimpleNamespace(content=self._contents.get("out", ""))
        if path.endswith(".err"):
            return SimpleNamespace(content=self._contents.get("err", ""))
        raise FileNotFoundError(path)


class _FakeSandbox:
    """Minimal stand-in for koyeb ``AsyncSandbox`` covering the polling API."""

    def __init__(
        self,
        *,
        code_reads: list[str],
        contents: dict[str, str] | None = None,
    ) -> None:
        self.filesystem = _FakeFilesystem(code_reads=code_reads, contents=contents or {})
        self.launched: list[tuple[str, str | None]] = []
        self.killed: list[str] = []
        self.pid = "pid-xyz"

    async def launch_process(
        self, cmd: str, cwd: str | None = None, env: dict | None = None
    ) -> str:
        self.launched.append((cmd, cwd))
        return self.pid

    async def kill_process(self, process_id: str) -> None:
        self.killed.append(process_id)


async def test_exec_polling_returns_exit_code_and_output() -> None:
    sandbox = _FakeSandbox(
        code_reads=["", "0"],
        contents={"out": "review body", "err": ""},
    )

    exit_code, stdout, stderr = await exec_polling(
        cast(AsyncSandbox, sandbox), "vibe run", cwd="/work/repo", timeout=30
    )

    assert (exit_code, stdout, stderr) == (0, "review body", "")
    # Launched exactly once, in the requested cwd, with the command wrapped in
    # an EXIT trap (sentinel exit code) plus a shell `exec` redirect so output
    # capture survives compound commands.
    assert len(sandbox.launched) == 1
    cmd, cwd = sandbox.launched[0]
    assert cwd == "/work/repo"
    assert cmd.startswith("trap ")
    assert "exec >" in cmd
    assert "vibe run" in cmd
    assert not sandbox.killed


async def test_exec_polling_waits_for_sentinel_file() -> None:
    # Completion is driven by the shell-written `.code` sentinel, not Koyeb's
    # racy `list_processes` bookkeeping: until the file exists the command is
    # still running, then it carries the real exit code.
    sandbox = _FakeSandbox(
        code_reads=["", "3"],
        contents={"out": "partial", "err": "trace"},
    )

    exit_code, stdout, stderr = await exec_polling(cast(AsyncSandbox, sandbox), "x", timeout=30)

    assert exit_code == 3
    assert stdout == "partial"
    assert stderr == "trace"


async def test_exec_polling_times_out_and_kills_process() -> None:
    # Sentinel never appears → the deadline fires and the process is killed.
    sandbox = _FakeSandbox(code_reads=[""])

    with pytest.raises(SandboxExecTimeout) as excinfo:
        await exec_polling(cast(AsyncSandbox, sandbox), "sleep 999", timeout=0)

    assert excinfo.value.timeout == 0
    assert sandbox.killed == ["pid-xyz"]


async def test_run_raises_on_nonzero_exit() -> None:
    sandbox = _FakeSandbox(
        code_reads=["2"],
        contents={"out": "", "err": "boom details"},
    )

    with pytest.raises(RuntimeError, match=r"clone failed \(exit=2\).*boom details"):
        await SandboxBuilder._run(
            cast(AsyncSandbox, sandbox), "git clone ...", timeout=30, fail_msg="clone failed"
        )


async def test_run_raises_on_timeout() -> None:
    sandbox = _FakeSandbox(code_reads=[""])

    with pytest.raises(RuntimeError, match="prep failed .*timeout after 0s"):
        await SandboxBuilder._run(
            cast(AsyncSandbox, sandbox), "x", timeout=0, fail_msg="prep failed"
        )

    assert sandbox.killed == ["pid-xyz"]
