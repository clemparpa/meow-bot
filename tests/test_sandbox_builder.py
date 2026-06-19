"""Unit tests for the SandboxBuilder git-exclude decoupling.

``with_report`` was split out of ``with_memory`` so the report-ignore and the
PR scratchpad are independent concerns: a plain default-branch checkout
(feature scoping) can git-ignore the agent's report file without writing a
PR-scoped memory scratchpad. These tests pin that seam: the shared exclude
idiom, and that the report-only step touches the report but never writes a
memory file.
"""

from __future__ import annotations

from typing import cast

from koyeb import AsyncSandbox

from meow.worker.sandbox.builder import (
    MEMORY_FILE,
    REPORT_FILE,
    SandboxBuilder,
    feature_branch_name,
)
from tests.test_exec_polling import _FakeSandbox


def test_git_exclude_cmd_single_path_is_idempotent() -> None:
    cmd = SandboxBuilder._git_exclude_cmd(REPORT_FILE)
    assert cmd.count("\n") == 0  # one path → one line
    assert ".git/info/exclude" in cmd
    assert REPORT_FILE in cmd
    # `grep -qxF ... ||` guards against duplicate appends on re-run.
    assert cmd.startswith("grep -qxF ")
    assert "||" in cmd


def test_git_exclude_cmd_multiple_paths_one_line_each() -> None:
    cmd = SandboxBuilder._git_exclude_cmd(MEMORY_FILE, REPORT_FILE)
    lines = cmd.split("\n")
    assert len(lines) == 2
    assert MEMORY_FILE in lines[0]
    assert REPORT_FILE in lines[1]


async def test_with_report_excludes_report_without_memory() -> None:
    builder = SandboxBuilder().with_report()

    # Exactly one queued step, and it's the report one.
    assert [s.name for s in builder._steps] == ["report"]

    sandbox = _FakeSandbox(code_reads=["0"])
    await builder._steps[0].run(cast(AsyncSandbox, sandbox))

    assert len(sandbox.launched) == 1
    cmd, _cwd = sandbox.launched[0]
    # Git-ignores the report...
    assert REPORT_FILE in cmd
    assert ".git/info/exclude" in cmd
    # ...but writes no memory scratchpad (no heredoc, no memory filename).
    assert MEMORY_FILE not in cmd
    assert "MEOW_EOF" not in cmd


def test_feature_branch_name_is_deterministic_per_issue() -> None:
    assert feature_branch_name(42) == "meow/issue-42"
