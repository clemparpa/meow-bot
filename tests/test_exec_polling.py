"""Unit tests for the non-blocking polling exec path (`exec_polling`).

These cover the behaviour that replaces the old blocking ``sandbox.exec``:
launch a background process, poll ``list_processes`` until it completes,
read stdout/stderr back from the redirect files, and surface a deadline
overrun as :class:`SandboxExecTimeout` after killing the process.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from meow.worker.sandbox.builder import (
    SandboxBuilder,
    SandboxExecTimeout,
    exec_polling,
)


def _proc(
    *,
    pid: str = "pid-xyz",
    status: str = "running",
    exit_code: int | None = None,
    completed_at: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=pid, status=status, exit_code=exit_code, completed_at=completed_at
    )


class _FakeFilesystem:
    def __init__(self, contents: dict[str, str]) -> None:
        self._contents = contents

    async def read_file(self, path: str, encoding: str = "utf-8") -> SimpleNamespace:
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
        statuses: list[list[SimpleNamespace]],
        contents: dict[str, str] | None = None,
    ) -> None:
        self._statuses = list(statuses)
        self.filesystem = _FakeFilesystem(contents or {})
        self.launched: list[tuple[str, str | None]] = []
        self.killed: list[str] = []
        self.pid = "pid-xyz"

    async def launch_process(
        self, cmd: str, cwd: str | None = None, env: dict | None = None
    ) -> str:
        self.launched.append((cmd, cwd))
        return self.pid

    async def list_processes(self) -> list[SimpleNamespace]:
        # Advance through the scripted sequence, then stick on the last entry.
        if len(self._statuses) > 1:
            return self._statuses.pop(0)
        return self._statuses[0]

    async def kill_process(self, process_id: str) -> None:
        self.killed.append(process_id)


async def test_exec_polling_returns_exit_code_and_output() -> None:
    sandbox = _FakeSandbox(
        statuses=[
            [_proc(status="running")],
            [_proc(status="completed", exit_code=0)],
        ],
        contents={"out": "review body", "err": ""},
    )

    exit_code, stdout, stderr = await exec_polling(
        sandbox, "vibe run", cwd="/work/repo", timeout=30
    )

    assert (exit_code, stdout, stderr) == (0, "review body", "")
    # Launched exactly once, in the requested cwd, with the command wrapped
    # in a shell `exec` redirect so output capture survives compound commands.
    assert len(sandbox.launched) == 1
    cmd, cwd = sandbox.launched[0]
    assert cwd == "/work/repo"
    assert cmd.startswith("exec >")
    assert "vibe run" in cmd
    assert not sandbox.killed


async def test_exec_polling_detects_completion_via_completed_at() -> None:
    sandbox = _FakeSandbox(
        statuses=[
            [_proc(status="running")],
            [_proc(status="running", exit_code=3, completed_at="2026-01-01T00:00:00Z")],
        ],
        contents={"out": "partial", "err": "trace"},
    )

    exit_code, stdout, stderr = await exec_polling(sandbox, "x", timeout=30)

    assert exit_code == 3
    assert stdout == "partial"
    assert stderr == "trace"


async def test_exec_polling_times_out_and_kills_process() -> None:
    sandbox = _FakeSandbox(statuses=[[_proc(status="running")]])

    with pytest.raises(SandboxExecTimeout) as excinfo:
        await exec_polling(sandbox, "sleep 999", timeout=0)

    assert excinfo.value.timeout == 0
    assert sandbox.killed == ["pid-xyz"]


async def test_run_raises_on_nonzero_exit() -> None:
    sandbox = _FakeSandbox(
        statuses=[[_proc(status="completed", exit_code=2)]],
        contents={"out": "", "err": "boom details"},
    )

    with pytest.raises(RuntimeError, match=r"clone failed \(exit=2\).*boom details"):
        await SandboxBuilder._run(sandbox, "git clone ...", timeout=30, fail_msg="clone failed")


async def test_run_raises_on_timeout() -> None:
    sandbox = _FakeSandbox(statuses=[[_proc(status="running")]])

    with pytest.raises(RuntimeError, match="prep failed .*timeout after 0s"):
        await SandboxBuilder._run(sandbox, "x", timeout=0, fail_msg="prep failed")

    assert sandbox.killed == ["pid-xyz"]
